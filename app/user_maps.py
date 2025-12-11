import re
import httpx
from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from app.models import User
from app.auth import verify_auth
from app.database import weather_cache, pois
from app.config import WEATHER_API_KEY, TILESERVER_URL, WEATHER_SERVICE_URL
from app.schemas import NearbyPOIRequest, PlaceDetailsRequest, NearbySearchAdvancedRequest
import logging
logger = logging.getLogger(__name__)

router = APIRouter()

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
    tile_url = f"{TILESERVER_URL}/styles/{base}/256/{z}/{x}/{y}.png"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(tile_url)
            response.raise_for_status()
            return StreamingResponse(response.iter_bytes(), media_type=response.headers['Content-Type'])
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch tile: {e.response.status_code} {e.response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Could not connect to map tile server: {e}")
    
@router.get("/api/vector-tiles/{z}/{x}/{y}.pbf")
async def get_vector_tile(z: int, x: int, y: int, user: User = Depends(verify_auth)):
    tile_url = f"{TILESERVER_URL}/data/openmaptiles/{z}/{x}/{y}.pbf"
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
    try:
        query = {
            "geometry": {
                "$nearSphere": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [payload.lon, payload.lat]
                    },
                    "$maxDistance": int(payload.distance)
                }
            }
        }

        if payload.amenity:
            query["properties.amenity"] = {
                "$regex": rf"(^|;){re.escape(payload.amenity)}(;|$)",
                "$options": "i"
            }
            
        cursor = pois.find(query).limit(int(payload.limit))
        
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
            
        return JSONResponse(content={
            "status": True,
            "count": len(results),
            "results": results,
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed")
    
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

        if payload.keyword:
            query["$or"] = [
                {"properties.name": {"$regex": payload.keyword, "$options": "i"}},
                {"properties.description": {"$regex": payload.keyword, "$options": "i"}},
                {"properties.brand": {"$regex": payload.keyword, "$options": "i"}}
            ]

        cursor = pois.find(query).limit(payload.limit)

        if payload.sort_by == "name":
            cursor = cursor.sort("properties.name", 1)
        elif payload.sort_by == "brand":
            cursor = cursor.sort("properties.brand", 1)

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
    
@router.get("/api/weather")
async def get_weather(lat: float = Query(...), lon: float = Query(...), user: User = Depends(verify_auth)):
    try:
        grid_lat = round(lat / 0.18) * 0.18
        grid_lon = round(lon / 0.18) * 0.18

        cache = await weather_cache.find_one({
            "grid_lat": grid_lat,
            "grid_lon": grid_lon
        })

        now = datetime.now()

        if cache and (now - cache["timestamp"]).total_seconds() < 3600:
            logger.info(f"✅ Weather cache hit for {grid_lat},{grid_lon}")
            cache["_id"] = str(cache["_id"])
            return JSONResponse(content={
                "status": True,
                "source": "cache",
                "result": cache["data"]
            })
        url = (
            f"{WEATHER_SERVICE_URL}/{lat},{lon}?unitGroup=metric&include=current&key={WEATHER_API_KEY}&contentType=json"
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        await weather_cache.update_one(
            {"grid_lat": grid_lat, "grid_lon": grid_lon},
            {
                "$set": {
                    "lat": lat,
                    "lon": lon,
                    "grid_lat": grid_lat,
                    "grid_lon": grid_lon,
                    "timestamp": now,
                    "data": data
                }
            },
            upsert=True
        )

        return JSONResponse(content={
            "status": True,
            "source": "api",
            "result": data
        })

    except httpx.HTTPStatusError as e:
        logger.error(f"Weather API error: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail="Weather API error")
    except httpx.RequestError as e:
        logger.error(f"Weather API connection failed: {e}")
        raise HTTPException(status_code=500, detail="Weather API connection failed")
    except Exception as e:
        logger.exception("Unexpected error in weather endpoint")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
