import re
from duckdb import cursor
import httpx
from bson import ObjectId
from jose import jwt, JWTError
from numpy import place
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from app.models import User
from app.auth import check_authorization_key
from app.schemas import NearbyPOIRequest, PlaceDetailsRequest, NearbySearchAdvancedRequest
from app.config import SECRET_KEY, ALGORITHM
from app.database import SessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import logging
logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

client = AsyncIOMotorClient("mongodb://192.168.1.110:28017")
db = client["FinalPOIs"]
pois = db["OSM"]

async def get_db():
    async with SessionLocal() as session:
        yield session
        
async def verify_auth(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(check_authorization_key)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    q = await db.execute(select(User).where(User.email == email))
    user = q.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@router.get("/api/user")
async def user_details(user: User = Depends(verify_auth)):
    return {"status": True, "msg": "Authenticated", "user": {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_active": user.is_active
    }}

@router.get("/api/map-tiles/{z}/{x}/{y}.png")
async def get_map_tile(z: int, x: int, y: int, style: str = "day", no_poi: bool = Query(False), user: User = Depends(verify_auth)):
    if style == "day":
        base = "light-mode-nopoi" if no_poi else "light-mode"
    elif style == "night":
        base = "dark-mode-nopoi" if no_poi else "dark-mode"
    else:
        raise HTTPException(status_code=400, detail="Invalid style parameter. Use 'day' or 'night'.")
    tile_url = f"http://192.168.1.110:4090/styles/{base}/256/{z}/{x}/{y}.png"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(tile_url)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            return StreamingResponse(response.iter_bytes(), media_type=response.headers['Content-Type'])
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch tile: {e.response.status_code} {e.response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Could not connect to map tile server: {e}")
    
@router.get("/api/vector-tiles/{z}/{x}/{y}.pbf")
async def get_vector_tile(z: int, x: int, y: int, user: User = Depends(verify_auth)):
    tile_url = f"http://192.168.1.110:4090/data/openmaptiles/{z}/{x}/{y}.pbf"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(tile_url)
            response.raise_for_status()
            return StreamingResponse(
                response.iter_bytes(),
                media_type="application/x-protobuf"
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Failed to fetch vector tile: {e.response.status_code} {e.response.text}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not connect to vector tile server: {e}"
        )
        
        
@router.post("/api/nearby-places")
async def get_nearby_poi(payload: NearbyPOIRequest):
    """Get nearby points of interest (POI) based on location and distance from user."""
    try:
        query = {
            "geometry": {
                "$near": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [payload.lon, payload.lat]
                    },
                    "$maxDistance": payload.distance
                }
            }
        }

        if payload.amenity:
            query["properties.amenity"] = {
                "$regex": rf"(^|;){re.escape(payload.amenity)}(;|$)",
                "$options": "i"
            }

        cursor = pois.find(query).limit(payload.limit)
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)

        return JSONResponse(content={
            "status": True,
            "count": len(results),
            "results": results
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

@router.post("/places/details")
async def place_details(payload: PlaceDetailsRequest):
    """Retrieve detailed metadata for a place by ID."""
    try:
        place = await pois.find_one({"_id": ObjectId(payload.place_id)})
        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        place["_id"] = str(place["_id"])
        properties = place.get("properties", {})
        lat = place["geometry"]["coordinates"][1]
        long = place["geometry"]["coordinates"][0]
        properties["location"] = {"type": "Point", "coordinates": [long, lat]}

        return JSONResponse(content={"status": True, "result": properties})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/nearby-places-advanced")
async def get_nearby_poi_advanced(payload: NearbySearchAdvancedRequest):
    """Advanced nearby POI search with multiple filters and sorting."""
    try:
        query = {
            "geometry": {
                "$near": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [payload.lon, payload.lat]
                    },
                    "$maxDistance": payload.distance
                }
            }
        }

        # Amenity filter (supports ';' separated amenities)
        if payload.amenity:
            query["properties.amenity"] = {
                "$regex": rf"(^|;){re.escape(payload.amenity)}(;|$)",
                "$options": "i"
            }

        # Keyword in name or description
        if payload.keyword:
            query["$or"] = [
                {"properties.name": {"$regex": payload.keyword, "$options": "i"}},
                {"properties.description": {"$regex": payload.keyword, "$options": "i"}},
                {"properties.brand": {"$regex": payload.keyword, "$options": "i"}}
            ]

        cursor = pois.find(query).limit(payload.limit)

        # Sorting logic
        if payload.sort_by == "name":
            cursor = cursor.sort("properties.name", 1)
        elif payload.sort_by == "brand":
            cursor = cursor.sort("properties.brand", 1)
        # Default: distance is auto-sorted by $near

        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)

        return JSONResponse(content={
            "status": True,
            "count": len(results),
            "results": results
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")