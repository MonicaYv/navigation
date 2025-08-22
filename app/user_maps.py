import httpx
from jose import jwt, JWTError
from fastapi import APIRouter,Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from app.models import User
from app.auth import check_authorization_key
from app.config import SECRET_KEY, ALGORITHM
from app.database import SessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
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
        