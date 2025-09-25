from motor.motor_asyncio import AsyncIOMotorClient
from .config import MONGO_URL

mongo_client = AsyncIOMotorClient(MONGO_URL)
mongo_db = mongo_client['FinalPOIs']
weather_db = mongo_client['Weather_Data']
