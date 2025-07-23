from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_active: bool
    class Config:
        orm_mode = True

class UserLogin(BaseModel):
    email: EmailStr

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str

class UserRegisterWithOTP(BaseModel):
    name: str
    email: EmailStr
    otp: str
    otp_token: str  


# Company
class CompanyCreate(BaseModel):
    name: str
    contact_email: EmailStr
    country: Optional[str] = None

class CompanyOut(CompanyCreate):
    id: int
    is_active: bool
    created_at: datetime
    class Config:
        orm_mode = True

# Plan
class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price_monthly: float
    price_annual: Optional[float] = None
    api_hit_limit: Optional[int] = None
    concurrent_connections: Optional[int] = None
    per_api_hit_price: Optional[float] = None

class PlanOut(PlanCreate):
    id: int
    is_active: bool
    created_at: datetime
    class Config:
        orm_mode = True

# Subscription
class CompanySubscriptionCreate(BaseModel):
    company_id: int
    plan_id: int
    start_date: datetime
    end_date: datetime
    auto_renew: Optional[bool] = True

class CompanySubscriptionOut(BaseModel):
    id: int
    company_id: int
    plan_id: int
    api_key: str
    start_date: datetime
    end_date: datetime
    status: str
    payment_provider: Optional[str]
    payment_ref: Optional[str]
    auto_renew: Optional[bool]
    created_at: datetime
    class Config:
        orm_mode = True

# API Usage
class APIUsageCreate(BaseModel):
    company_id: int
    subscription_id: int
    endpoint: str
    status_code: Optional[int]
    response_time_ms: Optional[int]

class APIUsageOut(APIUsageCreate):
    id: int
    timestamp: datetime
    class Config:
        orm_mode = True

# Invoice
class InvoiceCreate(BaseModel):
    company_id: int
    subscription_id: int
    amount: float
    currency: Optional[str] = 'INR'
    payment_provider: Optional[str]
    payment_status: Optional[str]
    payment_ref: Optional[str]
    due_date: Optional[datetime]
    paid_date: Optional[datetime]

class InvoiceOut(InvoiceCreate):
    id: int
    issue_date: datetime
    class Config:
        orm_mode = True

# Allowed Domain
class AllowedDomainCreate(BaseModel):
    company_id: int
    domain_name: str
    api_key: str

class AllowedDomainOut(AllowedDomainCreate):
    id: int
    is_active: bool
    created_at: datetime
    class Config:
        orm_mode = True
