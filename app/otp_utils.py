import pyotp

def generate_otp_secret():
    return pyotp.random_base32()

def generate_otp(secret: str) -> str:
    return pyotp.TOTP(secret).now()

def verify_otp(secret: str, otp: str) -> bool:
    return pyotp.TOTP(secret).verify(otp,valid_window=2)
