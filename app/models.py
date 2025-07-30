from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Numeric, Text, TIMESTAMP, Interval, Enum, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)         # <--- Add this line
    email = Column(String(255), unique=True, nullable=False)
    otp_secret = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=False)
    country = Column(String(64))
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    subscriptions = relationship("CompanySubscription", back_populates="company")
    invoices = relationship("Invoice", back_populates="company")
    usages = relationship("APIUsage", back_populates="company")

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price_monthly = Column(Numeric(10, 2), nullable=False)
    price_annual = Column(Numeric(10, 2))
    api_hit_limit = Column(Integer)
    concurrent_connections = Column(Integer)
    per_api_hit_price = Column(Numeric(10, 4))
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    subscriptions = relationship("CompanySubscription", back_populates="plan")

class CompanySubscription(Base):
    __tablename__ = "company_subscriptions"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete="CASCADE"))
    plan_id = Column(Integer, ForeignKey('plans.id'))
    api_key = Column(String(128), unique=True, nullable=False)
    start_date = Column(TIMESTAMP, nullable=False)
    end_date = Column(TIMESTAMP, nullable=False)
    status = Column(String(32), default='active')
    payment_provider = Column(String(32))
    payment_ref = Column(String(255))
    auto_renew = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    company = relationship("Company", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    usages = relationship("APIUsage", back_populates="subscription")
    invoices = relationship("Invoice", back_populates="subscription")

class APIUsage(Base):
    __tablename__ = "api_usages"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete="CASCADE"))
    subscription_id = Column(Integer, ForeignKey('company_subscriptions.id', ondelete="CASCADE"))
    endpoint = Column(String(255))
    timestamp = Column(TIMESTAMP, server_default=func.now())
    status_code = Column(Integer)
    response_time_ms = Column(Integer)

    company = relationship("Company", back_populates="usages")
    subscription = relationship("CompanySubscription", back_populates="usages")

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete="CASCADE"))
    subscription_id = Column(Integer, ForeignKey('company_subscriptions.id', ondelete="CASCADE"))
    amount = Column(Numeric(10,2), nullable=False)
    currency = Column(String(8), default='INR')
    payment_provider = Column(String(32))
    payment_status = Column(String(32))
    payment_ref = Column(String(255))
    issue_date = Column(TIMESTAMP, server_default=func.now())
    due_date = Column(TIMESTAMP)
    paid_date = Column(TIMESTAMP)

    company = relationship("Company", back_populates="invoices")
    subscription = relationship("CompanySubscription", back_populates="invoices")

class AllowedDomain(Base):
    __tablename__ = "allowed_domains"
    id = Column(Integer, primary_key=True)
    domain_name = Column(String(255), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"))
    api_key = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

class NavigationLog(Base):
    __tablename__ = "navigation_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    start_place = Column(String(255))
    destination = Column(String(255))
    start_time = Column(TIMESTAMP)
    end_time = Column(TIMESTAMP)
    time_taken = Column(Interval)
    directions = Column(JSONB)  # PostgreSQL JSONB to store maneuvers
    status = Column(Boolean, default=False)
    message = Column(String(255))
    error = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

class NavigationStatus(str, enum.Enum):
    completed = "completed"
    half_completed = "half_completed"
    disconnected = "disconnected"
    cancelled = "cancelled"

class NavigationLogHistory(Base):
    __tablename__ = "navigation_log_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    navigation_log_id = Column(Integer, ForeignKey("navigation_logs.id", ondelete="SET NULL"))
    start_place = Column(String(255))
    destination = Column(String(255))
    start_lat = Column(Float)
    start_lng = Column(Float)
    end_lat = Column(Float)
    end_lng = Column(Float)
    start_time = Column(TIMESTAMP)
    end_time = Column(TIMESTAMP)
    trip_duration = Column(Interval)
    date = Column(TIMESTAMP, server_default=func.now())
    status = Column(Enum(NavigationStatus))
    message = Column(String(255))

    turn_logs = relationship("TurnLog", back_populates="navigation_log", cascade="all, delete")

class TurnLog(Base):
    __tablename__ = "turn_logs"
    id = Column(Integer, primary_key=True)
    navigation_id = Column(Integer, ForeignKey("navigation_log_history.id", ondelete="CASCADE"))
    instruction = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    timestamp = Column(TIMESTAMP)

    navigation_log = relationship("NavigationLogHistory", back_populates="turn_logs")

