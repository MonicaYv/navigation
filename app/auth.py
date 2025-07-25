from fastapi import APIRouter, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
import asyncio
from jose import jwt
from datetime import datetime, timedelta
import os

from app.models import User
from app.schemas import UserLogin, OTPVerify, UserCreate, UserOut, UserRegisterWithOTP  # <-- add UserRegisterWithOTP if defined
from app.otp_utils import generate_otp_secret, generate_otp, verify_otp
from app.email_utils import send_email
from app.database import SessionLocal
from app.config import AUTHORIZATION_KEY, SECRET_KEY, ALGORITHM  # Import from your config module

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

router = APIRouter()

async def get_db():
    async with SessionLocal() as session:
        yield session

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def check_authorization_key(authorization_key: str = Header(...)):
    if authorization_key != AUTHORIZATION_KEY:
        raise HTTPException(status_code=401, detail="Invalid authorization key")
    return authorization_key

@router.post("/api/send-otp")
async def send_otp(user: UserCreate, _auth=Depends(check_authorization_key)):
    otp_secret = generate_otp_secret()
    otp = generate_otp(otp_secret)
    await send_email(user.email, "Your OTP Code", f"Your OTP is: {otp}")
    print(f"Generated otp_token: {otp_secret}")
    print(f"Sent OTP: {otp}")

    return {"otp_token": otp_secret}

@router.post("/api/register", response_model=UserOut)
async def register(
    data: UserRegisterWithOTP,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(check_authorization_key)
):
    print(f"Received otp_token: {data.otp_token}")
    print(f"Received OTP: {data.otp}")
    print(f"OTP verify result: {verify_otp(data.otp_token, data.otp)}")
    q = await db.execute(select(User).where(User.email == data.email))
    user_in_db = q.scalar_one_or_none()
    if user_in_db:
        raise HTTPException(status_code=401, detail="Email already registered")
    if not verify_otp(data.otp_token, data.otp):
        raise HTTPException(status_code=401, detail="Invalid OTP")
    new_user = User(
        name=data.name,
        email=data.email,
        otp_secret=data.otp_token,  # save for future login if needed
        is_active=True
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.post("/api/login/request-otp")
async def login_request_otp(
    data: UserLogin, 
    db: AsyncSession = Depends(get_db),
    _auth=Depends(check_authorization_key)
):
    q = await db.execute(select(User).where(User.email == data.email))
    user = q.scalar_one_or_none()
    if not user or not user.otp_secret:
        return {'status': False, "msg": "User not found"}
    otp = generate_otp(user.otp_secret)
    asyncio.create_task(send_email(user.email, "Your OTP Code", f"Your OTP is: {otp}"))
    return {"status": True, "msg": "OTP sent to email"}

@router.post("/api/login/verify")
async def login_verify_otp(
    data: OTPVerify, 
    db: AsyncSession = Depends(get_db),
    _auth=Depends(check_authorization_key)
):
    q = await db.execute(select(User).where(User.email == data.email))
    user = q.scalar_one_or_none()
    if not user or not user.otp_secret:
        return {'status': False, "msg": "User not found or OTP not set."}
    if not verify_otp(user.otp_secret, data.otp):
        return {'status': False, "msg": "Invalid OTP"}
    token = create_access_token({"sub": user.email})
    return {"status": True, "access_token": token, "token_type": "bearer"}
