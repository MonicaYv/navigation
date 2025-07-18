import aiosmtplib
from email.message import EmailMessage
from app.config import SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM

async def send_email(recipient: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    await aiosmtplib.send(
        msg,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USERNAME,
        password=SMTP_PASSWORD,
        start_tls=True,
    )
