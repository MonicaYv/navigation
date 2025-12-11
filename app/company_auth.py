from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import jwt, JWTError
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.models import User, CompanySubscription, Company
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from app.database import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/token")

router = APIRouter()

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_company_user_and_subscription(
    token: str = Depends(oauth2_scheme),
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
):
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

    return {"user": user, "company": company, "subscription": subscription}
