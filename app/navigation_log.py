from sqlalchemy.ext.asyncio import AsyncSession
from app.models import NavigationLog
from datetime import datetime, timedelta

async def save_navigation_log(
    db: AsyncSession,
    user_id: int,
    start_place: str,
    destination: str,
    start_time: datetime,
    end_time: datetime,
    directions: list,
    status: bool,
    message: str,
    error: str = None
):
    duration = end_time - start_time
    log = NavigationLog(
        user_id=user_id,
        start_place=start_place,
        destination=destination,
        start_time=start_time,
        end_time=end_time,
        time_taken=duration,
        directions=directions,
        status=status,
        message=message,
        error=error
    )
    db.add(log)
    await db.commit()
