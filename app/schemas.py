from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

class UserCreate(BaseModel):
    name: str
    email: EmailStr

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_active: bool
    class Config:
        from_attributes = True

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
        from_attributes = True

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
        from_attributes = True

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
        from_attributes = True

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
        from_attributes = True

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
        from_attributes = True

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
        from_attributes = True

# Maps 

class LocationPoint(BaseModel):
    lat: float
    lon: float
    
class RouteRequest(BaseModel):
    locations: List[LocationPoint]
    costing: str = "auto"  # Default to "auto"
    # Add other optional parameters as needed
    units: Optional[str] = "kilometers"
    language: Optional[str] = "en-US"
    
class RouteResponse(BaseModel):
    status: bool
    msg: str
    data: Optional[dict] = None
    error: Optional[str] = None
    
class NavigationStatus(str, Enum):
    completed = "completed"
    half_completed = "half_completed"
    disconnected = "disconnected"
    cancelled = "cancelled"

class TurnLogCreate(BaseModel):
    instruction: str
    latitude: float
    longitude: float
    timestamp: datetime

class NavigationLogHistoryCreate(BaseModel):
    navigation_log_id: int | None = None
    start_place: str
    destination: str
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    start_time: datetime
    end_time: datetime
    status: NavigationStatus
    message: str
    turn_logs: List[TurnLogCreate] = []
    
# Geofence

class GeofenceCreate(BaseModel):
    name: str
    coordinates: List[List[float]]

class GeofenceOut(BaseModel):
    id: int
    name: str
    geom: str
    created_at: datetime  

    class Config:
        from_attributes = True
