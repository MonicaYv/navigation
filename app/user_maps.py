from fastapi import APIRouter,Depends, HTTPException
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from app.models import User
from app.schemas import RouteRequest, RouteResponse
from app.config import SECRET_KEY, ALGORITHM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.security import OAuth2PasswordBearer
from app.database import SessionLocal
from app.auth import check_authorization_key
import logging
import httpx
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
async def get_routes(route_request: RouteRequest, user: User = Depends(verify_auth)):
    if len(route_request.locations) < 2:
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
    try:
        # Make HTTP request to external routing service
        # Using httpx for async HTTP requests
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://192.168.1.110:3095/route",
                json=external_payload,
                headers={"Content-Type": "application/json"}
            )
            # Check if the response is successful
            if response.status_code == 200:
                route_data = response.json()
                return RouteResponse(
                    status=True,
                    msg="Route calculated successfully",
                    data=route_data
                )
            else:
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
        return RouteResponse(
            status=False,
            msg="Internal server error",
            error="An unexpected error occurred"
        )

@router.get("/api/map-tiles/{z}/{x}/{y}.png")
async def get_map_tile(z: int, x: int, y: int, style: str = "day", user: User = Depends(verify_auth)):
    if style == "day":
        tile_url = f"http://192.168.1.110:3090/styles/test-style/512/{z}/{x}/{y}.png"
    elif style == "night":
        tile_url = f"http://192.168.1.110:3090/styles/maptiler-basic/512/{z}/{x}/{y}.png"
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