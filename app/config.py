import os
from dotenv import load_dotenv

load_dotenv()
AUTHORIZATION_KEY = os.getenv("AUTHORIZATION_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
MONGO_URL = os.getenv("MONGO_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
MAIL_USERNAME = os.getenv("EMAIL_HOST_USER")
MAIL_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
MAIL_FROM = os.getenv("DEFAULT_FROM_EMAIL")
MAIL_SERVER = os.getenv("EMAIL_HOST")
MAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
MAIL_TLS = os.getenv("MAIL_TLS") == "True"