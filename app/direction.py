import httpx
from datetime import datetime 
from jose import jwt, JWTError
from fastapi import APIRouter,Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from app.auth import check_authorization_key
from app.models import User, TurnLog, NavigationLogHistory
from app.schemas import RouteRequest, RouteResponse, MatrixRequest, SnapRequest, LocationPoint, MatrixBasicRequest, NavigationLogHistoryCreate, OptimizedRouteRequest
from app.config import SECRET_KEY, ALGORITHM, VALHALLA_BASE_URL, MAX_DISTANCE_KM
from app.database import SessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from geopy.distance import geodesic
from math import radians, sin, cos, sqrt, atan2
import logging
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

async def call_valhalla(endpoint: str, payload: dict, timeout: float = 30.0):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{VALHALLA_BASE_URL}/{endpoint}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return True, response.json()
    except httpx.TimeoutException:
        return False, {"error": "Request timeout"}
    except httpx.ConnectError:
        return False, {"error": "Routing service unavailable"}
    except Exception as e:
        return False, {"error": str(e)}
    
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

def validate_distance_limit(locations):
    min_lat = min(loc.lat for loc in locations)
    max_lat = max(loc.lat for loc in locations)
    min_lon = min(loc.lon for loc in locations)
    max_lon = max(loc.lon for loc in locations)

    farthest_distance = haversine(min_lat, min_lon, max_lat, max_lon)
    return farthest_distance <= MAX_DISTANCE_KM

@router.post("/api/distance-matrix-basic", response_model=RouteResponse)
async def distance_matrix_basic(request: MatrixBasicRequest, user: User = Depends(verify_auth), db: AsyncSession = Depends(get_db)):
    """The distance-matrix-basic calculates distances and times from a single origin to multiple destinations.
    Its response has a single array of results, essentially a one-to-many mapping."""
    if len(request.locations) < 2:
        return RouteResponse(status=False, msg="At least 2 locations required", error="Invalid input")
    
    if not validate_distance_limit(request.locations):
        return RouteResponse(
            status=False,
            msg="Locations too far apart",
            error=f"Locations exceed the {MAX_DISTANCE_KM} km limit"
        )
        
    payload = {
        "sources": [{"lat": request.locations[0].lat, "lon": request.locations[0].lon}],
        "targets": [{"lat": loc.lat, "lon": loc.lon} for loc in request.locations[1:]],
        "costing": request.mode
    }
    
    success, data = await call_valhalla("sources_to_targets", payload)
    if success:
        return RouteResponse(status=True, msg="Matrix calculated", data=data)
    return RouteResponse(status=False, msg="Failed to calculate matrix", error=data.get("error"))

@router.post("/api/distance-matrix", response_model=RouteResponse)
async def distance_matrix(request: MatrixRequest, user: User = Depends(verify_auth)):
    """Calculate a full many-to-many distance matrix."""
    if len(request.sources) + len(request.targets) < 2:
        return RouteResponse(status=False, msg="At least 2 locations required", error="Invalid input")
    all_locations = request.sources + request.targets
    if not validate_distance_limit(all_locations):
        return RouteResponse(
            status=False,
            msg="Locations too far apart",
            error=f"Locations exceed the {MAX_DISTANCE_KM} km limit"
        )

    payload = {
        "sources": [{"lat": src.lat, "lon": src.lon} for src in request.sources],
        "targets": [{"lat": tgt.lat, "lon": tgt.lon} for tgt in request.targets],
        "costing": request.mode,
        "id": "full-matrix"
    }

    success, data = await call_valhalla("sources_to_targets", payload)
    if success:
        return RouteResponse(status=True, msg="Full matrix calculated", data=data)
    return RouteResponse(status=False, msg="Failed to calculate matrix", error=data.get("error"))

@router.post("/api/get-route-basic", response_model=RouteResponse)
async def directions_basic(request: RouteRequest, user: User = Depends(verify_auth)):
    """This API is for lightweight route calculation when you only need basic path information like
    total distance and duration, but no turn-by-turn instructions."""
    if len(request.locations) < 2:
        return RouteResponse(status=False, msg="At least 2 locations required", error="Invalid input")

    payload = {
        "locations": [{"lat": loc.lat, "lon": loc.lon} for loc in request.locations],
        "costing": request.mode,
        "directions_options": {"units": "kilometers", "language": "en-US"}
    }

    success, data = await call_valhalla("route", payload)
    if success:
        # Filter unnecessary fields for a lightweight response
        for leg in data.get("trip", {}).get("legs", []):
            leg.pop("maneuvers", None)
        return RouteResponse(status=True, msg="Basic route calculated", data=data)
    return RouteResponse(status=False, msg="Failed to calculate route", error=data.get("error"))

@router.post("/api/get-route", response_model=RouteResponse)
async def directions_navigation(request: RouteRequest, user: User = Depends(verify_auth), db: AsyncSession = Depends(get_db)):
    """This API is for full-featured navigation, providing:
    Detailed turn-by-turn instructions (maneuvers).
    Summaries of each route leg.
    Support for alternative routes for flexibility."""
    if len(request.locations) < 2:
        return RouteResponse(status=False, msg="At least 2 locations required", error="Invalid input")

    payload = {
        "locations": [{"lat": loc.lat, "lon": loc.lon} for loc in request.locations],
        "costing": request.mode,
        "directions_options": {
            "units": "kilometers",
            "language": "en-US",
            "narrative": True
        },
        "alternatives": {"target_count": 3}
    }
    start_loc = request.locations[0]
    end_loc = request.locations[-1]
    start_time = datetime.now()
    success, data = await call_valhalla("route", payload)
    end_time = datetime.now()
    if success:
        # maneuvers = data.get("trip", {}).get("legs", [])[0].get("maneuvers", [])
        # await save_navigation_log(
        #     db=db,
        #     user_id=user.id,
        #     start_place=f"{start_loc.lat},{start_loc.lon}",
        #     destination=f"{end_loc.lat},{end_loc.lon}",
        #     start_time=start_time,
        #     end_time=end_time,
        #     directions=maneuvers,
        #     status=True,
        #     message="Route calculated successfully"
        # )
        return RouteResponse(status=True, msg="Navigation route calculated", data=data)
    return RouteResponse(status=False, msg="Failed to calculate navigation route", error=data.get("error"))

@router.post("/api/snap-to-road", response_model=RouteResponse)
async def snap_to_road(request: SnapRequest, user: User = Depends(verify_auth)):
    if not request.trace:
        return RouteResponse(status=False, msg="No trace data provided", error="Invalid input")

    for i in range(len(request.trace) - 1):
        dist = geodesic(
            (request.trace[i].lat, request.trace[i].lon),
            (request.trace[i + 1].lat, request.trace[i + 1].lon)
        ).meters
        if dist > 2000:
            return RouteResponse(
                status=False,
                msg="Trace points too far apart",
                error=f"Gap of {dist:.2f} meters between point {i} and {i+1}"
            )
            
    payload = {
        "shape": [{"lat": p.lat, "lon": p.lon} for p in request.trace],
        "costing": request.mode,
        "shape_match": request.shape_match
    }

    success, data = await call_valhalla("trace_attributes", payload)
    if success:
        return RouteResponse(status=True, msg="Trace snapped successfully", data=data)
    return RouteResponse(status=False, msg="Failed to snap trace", error=data.get("error"))

@router.post("/api/get-elevation", response_model=RouteResponse)
async def get_elevation(request: LocationPoint, user: User = Depends(verify_auth)):
    payload = {
        "shape": [
            {"lat": request.lat, "lon": request.lon}
        ]
    }

    success, data = await call_valhalla("height", payload)
    if success:
        return RouteResponse(
            status=True,
            msg="Elevation retrieved successfully",
            data={
                "location": {"lat": request.lat, "lon": request.lon},
                "elevation": data.get("height", [])[0] if data.get("height") else None
            }
        )
    return RouteResponse(
        status=False,
        msg="Failed to get elevation",
        error=data.get("error", "Unknown error occurred")
    )
    
@router.put("/api/navigation/history")
async def save_navigation_history(
    payload: NavigationLogHistoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_auth)
    ):
    # Calculate trip duration
    if payload.start_time and payload.end_time:
        trip_duration = payload.end_time - payload.start_time
    else:
        trip_duration = None

    nav_log = NavigationLogHistory(
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
            turn = TurnLog(
                navigation_id=nav_log.id,
                instruction=log.instruction,
                latitude=log.latitude,
                longitude=log.longitude,
                timestamp=log.timestamp
            )
            db.add(turn)
        await db.commit()

    return {"message": "Navigation log saved successfully", "id": nav_log.id}

@router.post("/api/optimized-route")
async def get_optimized_route(request: OptimizedRouteRequest, user: User = Depends(verify_auth)):
    payload = {
        "locations": [{"lat": loc.lat, "lon": loc.lon} for loc in request.locations],
        "costing": request.costing,
        "units": request.units
    }
    if not validate_distance_limit(request.locations):
        return RouteResponse(
            status=False,
            msg="Locations too far apart",
            error=f"Locations exceed the {MAX_DISTANCE_KM} km limit"
        )

    success, data = await call_valhalla("optimized_route", payload)
    if success:
        return RouteResponse(
            status=True,
            msg="Optimized route retrieved successfully",
            data=data
        )
    return RouteResponse(
        status=False,
        msg="Failed to get optimized route",
        error=data.get("error", "Unknown error occurred")
    )