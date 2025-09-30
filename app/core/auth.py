import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import JWTError, jwt
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

# URL Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def create_access_token(data: dict[str, object]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token() -> str:
    return generate_token(64)

def verify_token(token: str, token_type: str = "access") -> dict[str, object] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload
    except JWTError:
        return None

def send_email(to_email: str, subject: str, body: str, is_html: bool = False):
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"📧 [DEV MODE] Email would be sent to {to_email}")
        print(f"📧 [DEV MODE] Subject: {subject}")
        print(f"📧 [DEV MODE] SMTP Config: HOST={SMTP_HOST}, PORT={SMTP_PORT}, USER={SMTP_USER}")
        print(f"📧 [DEV MODE] Body preview: {body[:200]}...")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html' if is_html else 'plain'))

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        _ = server.starttls()
        _ = server.login(SMTP_USER, SMTP_PASSWORD)
        text = msg.as_string()
        _ = server.sendmail(FROM_EMAIL, to_email, text)
        _ = server.quit()

    except Exception as e:
        print(f"📧 Failed to send email to {to_email}: {e}")

def generate_verification_email(token: str) -> str:
    verification_url = f"{BACKEND_URL}/api/auth/verify-email?token={token}"

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>E-Mail-Adresse bestätigen</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #374151;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f9fafb;
            }}
            .container {{
                background-color: white;
                border-radius: 8px;
                padding: 32px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }}
            .button {{
                display: inline-block;
                background-color: #6366f1;
                color: white;
                text-decoration: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: 500;
                margin: 16px 0;
            }}
            .url-fallback {{
                background-color: #f3f4f6;
                padding: 12px;
                border-radius: 4px;
                font-family: monospace;
                word-break: break-all;
                margin: 16px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>E-Mail-Adresse bestätigen</h2>
            <p>Bitte klicken Sie auf den unten stehenden Button, um Ihre E-Mail-Adresse zu bestätigen:</p>

            <a href="{verification_url}" class="button">E-Mail bestätigen</a>

            <p>Falls der Button nicht funktioniert, kopieren Sie diese URL und fügen Sie sie in Ihren Browser ein:</p>
            <div class="url-fallback">{verification_url}</div>

            <p><small>Dieser Link läuft in 24 Stunden ab.</small></p>
        </div>
    </body>
    </html>
    """

def generate_password_reset_email(token: str) -> str:
    reset_url = f"{BACKEND_URL}/api/auth/reset-password?token={token}"

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Passwort zurücksetzen</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #374151;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f9fafb;
            }}
            .container {{
                background-color: white;
                border-radius: 8px;
                padding: 32px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }}
            .button {{
                display: inline-block;
                background-color: #dc2626;
                color: white;
                text-decoration: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: 500;
                margin: 16px 0;
            }}
            .url-fallback {{
                background-color: #f3f4f6;
                padding: 12px;
                border-radius: 4px;
                font-family: monospace;
                word-break: break-all;
                margin: 16px 0;
            }}
            .warning {{
                background-color: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 12px;
                margin: 16px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Passwort zurücksetzen</h2>
            <p>Sie haben eine Passwort-Zurücksetzung angefordert. Klicken Sie auf den unten stehenden Button, um ein neues Passwort zu erstellen:</p>

            <a href="{reset_url}" class="button">Passwort zurücksetzen</a>

            <p>Falls der Button nicht funktioniert, kopieren Sie diese URL und fügen Sie sie in Ihren Browser ein:</p>
            <div class="url-fallback">{reset_url}</div>

            <div class="warning">
                <strong>⚠️ Sicherheitshinweis:</strong><br>
                Falls Sie diese Zurücksetzung nicht angefordert haben, können Sie diese E-Mail ignorieren.
                Ihr Passwort bleibt unverändert.
            </div>

            <p><small>Dieser Link läuft in 1 Stunde ab.</small></p>
        </div>
    </body>
    </html>
    """

def generate_new_message_notification_email(
    recipient_name: str,
    sender_name: str,
    message_preview: str,
) -> str:
    app_url = FRONTEND_URL

    if len(message_preview) > 120:
        message_preview = message_preview[:120] + "..."

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Neue Nachricht erhalten</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #374151;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f9fafb;
            }}
            .container {{
                background-color: white;
                border-radius: 8px;
                padding: 32px;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 32px;
            }}
            .header h1 {{
                color: #1f2937;
                font-size: 24px;
                margin: 0;
                font-weight: 600;
            }}
            .message-box {{
                background-color: #f3f4f6;
                border-left: 4px solid #6366f1;
                padding: 16px;
                margin: 24px 0;
                border-radius: 4px;
            }}
            .sender {{
                font-weight: 600;
                color: #6366f1;
                margin-bottom: 8px;
            }}
            .message-content {{
                color: #4b5563;
                font-style: italic;
                line-height: 1.5;
            }}
            .cta-button {{
                display: inline-block;
                background-color: #6366f1;
                color: white;
                text-decoration: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: 500;
                margin: 24px 0;
                text-align: center;
            }}
            .cta-button:hover {{
                background-color: #5048e5;
            }}
            .footer {{
                margin-top: 32px;
                padding-top: 24px;
                border-top: 1px solid #e5e7eb;
                font-size: 14px;
                color: #6b7280;
                text-align: center;
            }}
            .footer a {{
                color: #6366f1;
                text-decoration: none;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>💬 Neue Nachricht erhalten</h1>
            </div>

            <p>Hallo {recipient_name},</p>

            <p>du hast eine neue Nachricht von <strong>{sender_name}</strong> erhalten:</p>

            <div class="message-box">
                <div class="sender">Von: {sender_name}</div>
                <div class="message-content">"{message_preview}"</div>
            </div>

            <div style="text-align: center;">
                <a href="{app_url}" class="cta-button">
                    Zur App anmelden
                </a>
            </div>

            <p>Melde dich in der App an, um die vollständige Nachricht zu lesen und zu antworten.</p>

            <div class="footer">
                <p>
                    Du erhältst diese E-Mail, weil du Benachrichtigungen für neue Nachrichten aktiviert hast.<br>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
