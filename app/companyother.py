from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import User, CompanySubscription, AllowedDomain, Company
from app.config import SECRET_KEY
from app.database import get_db
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, Header, Request, status

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/token")

async def get_current_company_by_apikey(
    x_api_key: str = Header(..., alias="X-API-Key"),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
) -> Company:
    q = await db.execute(
        select(CompanySubscription).where(
            CompanySubscription.api_key == x_api_key,
            CompanySubscription.status == "active"
        )
    )
    subscription = q.scalar_one_or_none()
    if not subscription:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
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
    c_q = await db.execute(
        select(Company).where(Company.id == subscription.company_id)
    )
    company = c_q.scalar_one_or_none()
    return company

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
