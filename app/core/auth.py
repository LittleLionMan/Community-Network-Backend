import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, status
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Email settings
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def create_access_token(data: Dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token() -> str:
    return generate_token(64)

def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload
    except JWTError:
        return None

def send_email(to_email: str, subject: str, body: str, is_html: bool = False):
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"SMTP_USER: {SMTP_USER}")
        print(f"SMTP_PASSWORD: {SMTP_PASSWORD}")
        print("FROM_EMAIL:", repr(FROM_EMAIL))
        print(f"Email would be sent to {to_email}: {subject}")
        print(f"Body: {body}")
        return  # Skip actual sending in development

    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html' if is_html else 'plain'))

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        text = msg.as_string()
        server.sendmail(FROM_EMAIL, to_email, text)
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

def generate_verification_email(email: str, token: str, base_url: str = "http://localhost:8000") -> str:
    verification_url = f"{base_url}/auth/verify-email?token={token}"
    return f"""
    <html>
    <body>
        <h2>E-Mail-Adresse bestätigen</h2>
        <p>Bitte klicken Sie auf den unten stehenden Link, um Ihre E-Mail-Adresse zu bestätigen:</p>
        <p><a href="{verification_url}">E-Mail bestätigen</a></p>
        <p>Falls der Link nicht funktioniert, kopieren Sie diese URL und fügen Sie sie in Ihren Browser ein:</p>
        <p>{verification_url}</p>
        <p>Dieser Link läuft in 24 Stunden ab.</p>
    </body>
    </html>
    """

def generate_password_reset_email(email: str, token: str, base_url: str = "http://localhost:8000") -> str:
    reset_url = f"{base_url}/auth/reset-password?token={token}"
    return f"""
    <html>
    <body>
        <h2>Passwort zurücksetzen</h2>
        <p>Sie haben eine Passwort-Zurücksetzung angefordert. Klicken Sie auf den unten stehenden Link, um ein neues Passwort zu erstellen:</p>
        <p><a href="{reset_url}">Passwort zurücksetzen</a></p>
        <p>Falls der Link nicht funktioniert, kopieren Sie diese URL und fügen Sie sie in Ihren Browser ein:</p>
        <p>{reset_url}</p>
        <p>Dieser Link läuft in 1 Stunde ab.</p>
        <p>Falls Sie diese Zurücksetzung nicht angefordert haben, können Sie diese E-Mail ignorieren.</p>
    </body>
    </html>
    """
