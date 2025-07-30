import aiosmtplib
from email.message import EmailMessage

SMTP_HOST = "mail.sizaf.com"
SMTP_PORT = 465
SMTP_USERNAME = "dotsdesktop@sizaf.com"
SMTP_PASSWORD = "eri$45;e]H0K"
SMTP_FROM = "dotsdesktop@sizaf.com"

async def send_email(recipient: str, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    print("Connecting to mail.sizaf.com:465 with SSL")
    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            use_tls=True,
        )
        print("Email sent!")
    except Exception as e:
        print("EMAIL SEND ERROR:", e)
        raise

