from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import SessionLocal
from app.models import CompanySubscription, AllowedDomain, Company

async def get_db():
    async with SessionLocal() as session:
        yield session

# Company API key auth, optionally validate domain
async def get_current_company_by_apikey(
    x_api_key: str = Header(..., alias="X-API-Key"),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
) -> Company:
    # Validate api_key in active subscription
    q = await db.execute(
        select(CompanySubscription).where(
            CompanySubscription.api_key == x_api_key,
            CompanySubscription.status == "active"
        )
    )
    subscription = q.scalar_one_or_none()
    if not subscription:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    # Optionally check domain (use AllowedDomain)
    if request:
        domain = request.headers.get("host")
        d_q = await db.execute(
            select(AllowedDomain).where(
                AllowedDomain.api_key == x_api_key,
                AllowedDomain.domain_name == domain,
                AllowedDomain.is_active == True
            )
        )
        domain_obj = d_q.scalar_one_or_none()
        if not domain_obj:
            raise HTTPException(status_code=403, detail="Domain not allowed")
    # Return company object
    c_q = await db.execute(
        select(Company).where(Company.id == subscription.company_id)
    )
    company = c_q.scalar_one_or_none()
    return company
from fastapi import Depends, HTTPException, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError, jwt
from app.config import SECRET_KEY
from app.database import SessionLocal
from app.models import User, Company, CompanySubscription

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/token")  # Your token endpoint

async def get_db():
    async with SessionLocal() as session:
        yield session

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

    # 3. Optional: Check the user is part of the company
    comp_q = await db.execute(
        select(Company).where(Company.id == subscription.company_id)
    )
    company = comp_q.scalar_one_or_none()
    # Here you may want to link users to company via a foreign key or association table for multi-user companies!
    # Otherwise, skip this step

    return {"user": user, "company": company, "subscription": subscription}
