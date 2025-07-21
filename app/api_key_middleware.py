from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import SessionLocal
from app.models import CompanySubscription, APIUsage, Plan
from datetime import datetime
from sqlalchemy import func, and_

import time

class APIKeyTrackingAndRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only track API requests to /api/ (customize as needed)
        if request.url.path.startswith("/api/"):
            # 1. Get API key from header
            api_key = request.headers.get("x-api-key")
            if not api_key:
                raise HTTPException(status_code=401, detail="API key required")

            async with SessionLocal() as db:
                # 2. Validate subscription and plan
                result = await db.execute(
                    select(CompanySubscription).where(
                        CompanySubscription.api_key == api_key,
                        CompanySubscription.status == "active"
                    )
                )
                subscription = result.scalar_one_or_none()
                if not subscription:
                    raise HTTPException(status_code=401, detail="Invalid or expired API key")

                # 3. Get plan
                plan = await db.get(Plan, subscription.plan_id)

                # 4. Rate limit: API hit limit per month
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

                # 5. Rate limit: Concurrent connections (rough version)
                # You could track with Redis for true concurrency, or approximate with APIUsage "last few seconds".
                # Here, let's assume at most N requests per second for demo:
                if plan.concurrent_connections:
                    since = datetime.utcnow() - timedelta(seconds=1)
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

                # 6. Process the request & measure response time
                start_time = time.monotonic()
                response = await call_next(request)
                end_time = time.monotonic()
                response_time_ms = int((end_time - start_time) * 1000)

                # 7. Track API usage (do not block main thread for DB, but ensure no leaks)
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
            # Non-API endpoints, proceed as normal
            response = await call_next(request)
            return response
