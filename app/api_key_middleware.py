import time
from datetime import datetime
from datetime import timedelta
from sqlalchemy import func, and_
from sqlalchemy.future import select
from app.database import SessionLocal
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.models import CompanySubscription, APIUsage, Plan

class APIKeyTrackingAndRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            api_key = request.headers.get("x-api-key")
            if not api_key:
                raise HTTPException(status_code=401, detail="API key required")

            async with SessionLocal() as db:
                result = await db.execute(
                    select(CompanySubscription).where(
                        CompanySubscription.api_key == api_key,
                        CompanySubscription.status == "active"
                    )
                )
                subscription = result.scalar_one_or_none()
                if not subscription:
                    raise HTTPException(status_code=401, detail="Invalid or expired API key")

                plan = await db.get(Plan, subscription.plan_id)

                if plan.api_hit_limit:
                    now = datetime.utcnow()
                    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    count_q = await db.execute(
                        select(func.count()).where(
                            and_(
                                APIUsage.company_id == subscription.company_id,
                                APIUsage.subscription_id == subscription.id,
                                APIUsage.timestamp >= start_month
                            )
                        )
                    )
                    hit_count = count_q.scalar()
                    if hit_count >= plan.api_hit_limit:
                        raise HTTPException(status_code=429, detail="API monthly hit limit exceeded")
                    
                if plan.concurrent_connections:
                    since = datetime.now() - timedelta(seconds=1)
                    count_q = await db.execute(
                        select(func.count()).where(
                            and_(
                                APIUsage.company_id == subscription.company_id,
                                APIUsage.subscription_id == subscription.id,
                                APIUsage.timestamp >= since
                            )
                        )
                    )
                    active_count = count_q.scalar()
                    if active_count >= plan.concurrent_connections:
                        raise HTTPException(status_code=429, detail="API concurrent connection limit exceeded")

                start_time = time.monotonic()
                response = await call_next(request)
                end_time = time.monotonic()
                response_time_ms = int((end_time - start_time) * 1000)

                usage = APIUsage(
                    company_id=subscription.company_id,
                    subscription_id=subscription.id,
                    endpoint=request.url.path,
                    status_code=response.status_code,
                    response_time_ms=response_time_ms,
                )
                db.add(usage)
                await db.commit()

                return response
        else:
            response = await call_next(request)
            return response
