import asyncio
from jose import jwt, JWTError
from datetime import datetime, timedelta
from app.models import User
from app.schemas import UserLogin, OTPVerify, UserCreate, UserOut, UserRegisterWithOTP
from app.otp_utils import generate_otp_secret, generate_otp, verify_otp
from app.email_utils import send_email
from app.database import get_db
from app.config import AUTHORIZATION_KEY, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from fastapi import APIRouter, Header, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def check_authorization_key(authorization_key: str = Header(...)):
    if authorization_key != AUTHORIZATION_KEY:
        raise HTTPException(status_code=401, detail="Invalid authorization key")
    return authorization_key

async def verify_auth(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db), auth=Depends(check_authorization_key)):
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
        otp_secret=data.otp_token,
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
    print(f"Sent OTP: {otp}")
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
