import aiosmtplib
from email.message import EmailMessage
from .config import SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS

async def send_email(recipient: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    print(f"Connecting to {SMTP_HOST}:{SMTP_PORT} with SSL")
    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            use_tls=SMTP_TLS,
        )
        print("Email sent!")
    except Exception as e:
        print("EMAIL SEND ERROR:", e)
        raise

