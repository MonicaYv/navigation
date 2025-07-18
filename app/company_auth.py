from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
import asyncio
from jose import jwt
from datetime import datetime, timedelta
import os

from app.models import User
from app.schemas import UserLogin, OTPVerify, UserCreate, UserOut
from app.otp_utils import generate_otp_secret, generate_otp, verify_otp
from app.email_utils import send_email
from app.database import SessionLocal

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()

async def get_db():
    async with SessionLocal() as session:
        yield session

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_company_user_and_subscription(
    token: str = Depends(oauth2_scheme),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
    # 1. Validate JWT
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid JWT or credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    q = await db.execute(select(User).where(User.email == email))
    user = q.scalar_one_or_none()
    if not user:
        raise credentials_exception

    # 2. Validate API Key
    sub_q = await db.execute(
        select(CompanySubscription).where(
            CompanySubscription.api_key == x_api_key,
            CompanySubscription.status == "active"
        )
    )
    subscription = sub_q.scalar_one_or_none()
    if not subscription:
        raise HTTPException(status_code=403, detail="Invalid or expired API key")

    comp_q = await db.execute(
        select(Company).where(Company.id == subscription.company_id)
    )
    company = comp_q.scalar_one_or_none()
    p

    return {"user": user, "company": company, "subscription": subscription}
