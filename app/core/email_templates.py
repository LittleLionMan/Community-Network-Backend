import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def generate_verification_email(token: str) -> str:
    """Email-Template für Email-Verifizierung bei Registrierung"""
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
    """Email-Template für Passwort-Zurücksetzen"""
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
    """Email-Template für neue Nachrichten-Benachrichtigung"""
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


def generate_newsletter_email(
    recipient_name: str,
    admin_message: str,
) -> str:
    """Email-Template für Newsletter-Versand durch Admins"""
    settings_url = f"{FRONTEND_URL}/profile?tab=settings"

    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Community Newsletter</title>
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
                border-bottom: 3px solid #6366f1;
                padding-bottom: 16px;
            }}
            .header h1 {{
                color: #1f2937;
                font-size: 28px;
                margin: 0;
                font-weight: 700;
            }}
            .greeting {{
                font-size: 18px;
                color: #1f2937;
                margin-bottom: 24px;
            }}
            .content {{
                background-color: #f9fafb;
                border-radius: 6px;
                padding: 24px;
                margin: 24px 0;
                border-left: 4px solid #6366f1;
            }}
            .content p {{
                margin: 12px 0;
                white-space: pre-wrap;
            }}
            .footer {{
                margin-top: 32px;
                padding-top: 24px;
                border-top: 1px solid #e5e7eb;
                font-size: 13px;
                color: #6b7280;
            }}
            .footer a {{
                color: #6366f1;
                text-decoration: none;
                font-weight: 500;
            }}
            .disclaimer {{
                background-color: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 12px;
                margin: 16px 0;
                font-size: 13px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📰 Community Newsletter</h1>
            </div>

            <div class="greeting">
                Hallo {recipient_name},
            </div>

            <div class="content">
                {admin_message}
            </div>

            <div class="disclaimer">
                <strong>ℹ️ Newsletter-Einstellungen:</strong><br>
                Du erhältst diese E-Mail, weil du Newsletter-Benachrichtigungen aktiviert hast.
                Falls du keine Newsletter mehr erhalten möchtest, kannst du diese jederzeit in deinen
                <a href="{settings_url}">Profil-Einstellungen</a> deaktivieren.
            </div>

            <div class="footer">
                <p>
                    Mit freundlichen Grüßen,<br>
                    Dein Community-Team
                </p>
                <p style="margin-top: 16px;">
                    <a href="{FRONTEND_URL}">Zur Community</a> |
                    <a href="{settings_url}">Einstellungen</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
