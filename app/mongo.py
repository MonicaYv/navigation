import motor.motor_asyncio
from .config import MONGO_URL

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
mongo_db = mongo_client['Navigation']
