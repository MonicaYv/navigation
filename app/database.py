from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL, MONGO_URL
from motor.motor_asyncio import AsyncIOMotorClient


SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

mongo_client = AsyncIOMotorClient(MONGO_URL)
mongo_db = mongo_client['FinalPOIs']
weather_db = mongo_client['Weather_Data']

weather_cache = weather_db['cache']
pois = mongo_db["OSM"]

async def get_db():
    async with SessionLocal() as session:
        yield session