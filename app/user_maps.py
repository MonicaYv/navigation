from fastapi import APIRouter,Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from app.models import User, NavigationLog
from app.schemas import RouteRequest, RouteResponse
from app.config import SECRET_KEY, ALGORITHM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.security import OAuth2PasswordBearer
from app.database import SessionLocal
from app.auth import check_authorization_key
from app.navigation_log import save_navigation_log
from app import models, schemas
from datetime import datetime 
import logging
import httpx
import asyncio
logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

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

@router.post("/api/get-route", response_model=RouteResponse)
async def get_routes(route_request: RouteRequest, user: User = Depends(verify_auth), db: AsyncSession = Depends(get_db)):
    if len(route_request.locations) < 2:
        await save_navigation_log(
            db=db,
            user_id=user.id,
            start_place="",
            destination="",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            directions=[],
            status=False,
            message="At least 2 locations required",
            error="Insufficient locations"
        )
        return RouteResponse(
            status=False,
            msg="At least 2 locations required for routing",
            error="Insufficient locations"
        )
    external_payload = {
        "locations": [
            {"lat": loc.lat, "lon": loc.lon} 
            for loc in route_request.locations
        ],
        "costing": route_request.costing,
        "alternatives": True,
        "directions_options": {
            "units": "kilometers",
            "language": "en-US"
        },
        "alternatives": {
            "target_count": 3
        }
    }
    start_loc = route_request.locations[0]
    end_loc = route_request.locations[-1]
    start_time = datetime.utcnow()
    try:
        # Make HTTP request to external routing service
        # Using httpx for async HTTP requests
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://192.168.1.110:3095/route",
                json=external_payload,
                headers={"Content-Type": "application/json"}
            )
            end_time = datetime.utcnow()
            # Check if the response is successful
            if response.status_code == 200:
                route_data = response.json()
                maneuvers = route_data.get("trip", {}).get("legs", [])[0].get("maneuvers", [])
                await save_navigation_log(
                db=db,
                user_id=user.id,
                start_place=f"{start_loc.lat},{start_loc.lon}",
                destination=f"{end_loc.lat},{end_loc.lon}",
                start_time=start_time,
                end_time=end_time,
                directions=maneuvers,
                status=True,
                message="Route calculated successfully"
                )
                return RouteResponse(
                    status=True,
                    msg="Route calculated successfully",
                    data=route_data
                )
            else:
                await save_navigation_log(
                db=db,
                user_id=user.id,
                start_place=f"{start_loc.lat},{start_loc.lon}",
                destination=f"{end_loc.lat},{end_loc.lon}",
                start_time=start_time,
                end_time=datetime.utcnow(),
                directions=[],
                status=False,
                message="Failed to calculate route",
                error=f"Status code {response.status_code}"
                )
                return RouteResponse(
                    status=False,
                    msg="Failed to calculate route",
                    error=f"External service returned status {response.status_code}"
                )
                
    except httpx.TimeoutException:
        return RouteResponse(
            status=False,
            msg="Request timeout",
            error="Routing service took too long to respond"
        )
        
    except httpx.ConnectError:
        return RouteResponse(
            status=False,
            msg="Service unavailable",
            error="Could not connect to routing service"
        )
        
    except Exception as e:
        await save_navigation_log(
            db=db,
            user_id=user.id,
            start_place=f"{start_loc.lat},{start_loc.lon}",
            destination=f"{end_loc.lat},{end_loc.lon}",
            start_time=start_time,
            end_time=datetime.utcnow(),
            directions=[],
            status=False,
            message="Internal server error",
            error=str(e)
        )
        return RouteResponse(
            status=False,
            msg="Internal server error",
            error="An unexpected error occurred"
        )

@router.get("/api/map-tiles/{z}/{x}/{y}.png")
async def get_map_tile(z: int, x: int, y: int, style: str = "day", user: User = Depends(verify_auth)):
    if style == "day":
        tile_url = f"http://192.168.1.110:4090/styles/test-style/256/{z}/{x}/{y}.png"
    elif style == "night":
        tile_url = f"http://192.168.1.110:4090/styles/maptiler-basic/256/{z}/{x}/{y}.png"
    else:
        raise HTTPException(status_code=400, detail="Invalid style parameter. Use 'day' or 'night'.")
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(tile_url)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            return StreamingResponse(response.iter_bytes(), media_type=response.headers['Content-Type'])
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch tile: {e.response.status_code} {e.response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Could not connect to map tile server: {e}")
    
@router.put("/api/navigation/history")
async def save_navigation_history(payload: schemas.NavigationLogHistoryCreate, db: AsyncSession = Depends(get_db),  user: User = Depends(verify_auth)):
    # Calculate trip duration
    if payload.start_time and payload.end_time:
        trip_duration = payload.end_time - payload.start_time
    else:
        trip_duration = None

    nav_log = models.NavigationLogHistory(
        user_id=user.id,
        navigation_log_id=payload.navigation_log_id,
        start_place=payload.start_place,
        destination=payload.destination,
        start_lat=payload.start_lat,
        start_lng=payload.start_lng,
        end_lat=payload.end_lat,
        end_lng=payload.end_lng,
        start_time=payload.start_time,
        end_time=payload.end_time,
        trip_duration=trip_duration,
        # directions=payload.directions,
        status=payload.status,
        message=payload.message
    )

    db.add(nav_log)
    await db.commit()
    await db.refresh(nav_log)

    # Save turn logs if any
    if payload.turn_logs:
        for log in payload.turn_logs:
            turn = models.TurnLog(
                navigation_id=nav_log.id,
                instruction=log.instruction,
                latitude=log.latitude,
                longitude=log.longitude,
                timestamp=log.timestamp
            )
            db.add(turn)
        await db.commit()

    return {"message": "Navigation log saved successfully", "id": nav_log.id}

@router.get("/api/search")
async def nominatim_search(
    q: str = Query(..., min_length=2),
    user: User = Depends(verify_auth),
    limit: int = Query(10, ge=1, le=50),
):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "http://localhost:8088/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": limit,
                    "addressdetails": 1
                },
                headers={"User-Agent": "medocr-search"}  # REQUIRED for Nominatim
            )

            response.raise_for_status()
            data = response.json()
            return {
                "status": True,
                "msg": "Search successful",
                "count": len(data),
                "results": data
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"Nominatim HTTP error: {e.response.text}")
        raise HTTPException(status_code=502, detail="Nominatim responded with an error")

    except httpx.RequestError as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not connect to Nominatim")

    except Exception as e:
        logger.exception("Unexpected error")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/api/photon-search")
async def photon_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    user = Depends(verify_auth)
):
    url = "http://localhost:2322/api"
    params = {"q": q, "limit": limit}
    headers = {"User-Agent": "medocr-photon"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {
                "status": True,
                "count": len(data.get("features", [])),
                "results": data.get("features", [])
            }
        except httpx.HTTPStatusError:
            raise HTTPException(502, "Photon search failed")
        except httpx.RequestError:
            raise HTTPException(500, "Could not connect to Photon")

@router.get("/api/unified-search")
async def unified_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user = Depends(verify_auth),
):
    photon_url = "http://localhost:2322/api"
    nominatim_reverse = "http://localhost:8088/reverse"
    ua_photon = {"User-Agent": "medocr-photon"}
    ua_nominatim = {"User-Agent": "medocr-search"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1) Fetch limit+offset results from Photon
        fetch_count = limit + offset
        try:
            response = await client.get(
                photon_url,
                params={"q": q, "limit": fetch_count},
                headers=ua_photon
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Photon [{e.response.status_code}]: {e.response.text}")
            raise HTTPException(502, "Photon search failed")
        except httpx.RequestError as e:
            logger.error(f"Photon request error: {e}")
            raise HTTPException(502, "Could not connect to Photon")

        all_features = response.json().get("features", [])
        logger.info(f"Photon returned {len(all_features)} raw features")

        # 2) Client-side pagination: slice out the page
        page = all_features[offset : offset + limit]
        logger.info(f"Sliced to {len(page)} features (offset={offset}, limit={limit})")

        # 3) Parallel reverse-geocode each feature
        async def fetch_address(feat):
            lon, lat = feat["geometry"]["coordinates"]
            try:
                r = await client.get(
                    nominatim_reverse,
                    params={"lon": lon, "lat": lat, "format": "json", "addressdetails": 1},
                    headers=ua_nominatim
                )
                r.raise_for_status()
                return r.json().get("address", {})
            except httpx.HTTPStatusError:
                logger.warning(f"Nominatim HTTP error for {lat},{lon}")
            except httpx.RequestError:
                logger.warning(f"Nominatim request error for {lat},{lon}")
            return {}

        addresses = await asyncio.gather(
            *[fetch_address(f) for f in page],
            return_exceptions=False
        )

        # 4) Merge geometry, properties, and structured address
        combined = []
        for feat, addr in zip(page, addresses):
            combined.append({
                "type": feat.get("type"),
                "geometry": feat.get("geometry"),
                "properties": feat.get("properties"),
                "address": addr
            })

        logger.info(f"Returning {len(combined)} combined results")

        return {
            "status": True,
            "count": len(combined),
            "results": combined
        }