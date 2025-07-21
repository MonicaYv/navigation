import os
from dotenv import load_dotenv

load_dotenv()
AUTHORIZATION_KEY = os.getenv("AUTHORIZATION_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
MONGO_URL = os.getenv("MONGO_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
SMTP_USERNAME = os.getenv("EMAIL_HOST_USER")
SMTP_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
SMTP_FROM = os.getenv("DEFAULT_FROM_EMAIL")
SMTP_HOST = os.getenv("EMAIL_HOST")
SMTP_PORT = int(os.getenv("EMAIL_PORT", 587))
SMTP_TLS = os.getenv("MAIL_TLS") == "True"
