# 🏘️ Community Network Backend

Eine moderne Community-Plattform API, die lokale Gemeinschaften dabei unterstützt, Events zu organisieren, Services auszutauschen und in Diskussionen zu treten.

## ✨ Features

### 👥 **User Management**
- Benutzerregistrierung und -authentifizierung
- Email-Verifizierung
- Passwort-Reset Funktionalität
- Privacy-Einstellungen für Profile

### 📅 **Events**
- Event-Erstellung mit Kategorien
- Teilnehmer-Management mit Kapazitätsgrenzen
- Automatische Anwesenheitsverfolgung
- Event-Kommentarsystem

### 🤝 **Service Exchange**
- Services anbieten oder suchen
- Intelligente Service-Empfehlungen
- Kommentar- und Bewertungssystem

### 💬 **Community Forum**
- Diskussionsthreads erstellen
- Verschachtelte Kommentare
- Content-Moderation
- Admin-Tools

### 🗳️ **Voting System**
- Thread-bezogene Umfragen
- Admin-Umfragen für Platform-Entscheidungen
- Echtzeit-Ergebnisse
- WebSocket-Updates

### 🛡️ **Sicherheit & Moderation**
- JWT-basierte Authentifizierung
- Rate Limiting
- Automatische Content-Moderation
- Admin-Dashboard

## 🚀 Quick Start

### Voraussetzungen
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### 1. Installation

```bash
# Repository klonen
git clone https://github.com/your-username/community-network-backend
cd community-network-backend

# Virtual Environment erstellen
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements/dev.txt
```

### 2. Umgebungsvariablen

```bash
# .env Datei erstellen (basierend auf .env.example)
cp .env.example .env

# Wichtige Einstellungen anpassen:
SECRET_KEY="your-super-secret-key-here"
DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/community_db"
REDIS_URL="redis://localhost:6379/0"
DEBUG=true
```

### 3. Datenbank Setup

```bash
# PostgreSQL und Redis starten (mit Docker)
docker-compose up -d db redis

# Datenbank-Migrationen ausführen
alembic upgrade head
```

### 4. Server starten

```bash
# Development Server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Oder mit Docker
docker-compose up
```

🎉 **API läuft jetzt auf:** `http://localhost:8000`

## 📖 API Dokumentation

### Interaktive Docs
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Hauptendpunkte

| Bereich | Endpoint | Beschreibung |
|---------|----------|--------------|
| **Auth** | `POST /api/auth/register` | Benutzer registrieren |
| | `POST /api/auth/login` | Anmelden |
| | `GET /api/auth/me` | Aktueller Benutzer |
| **Events** | `GET /api/events/` | Events auflisten |
| | `POST /api/events/` | Event erstellen |
| | `POST /api/events/{id}/join` | Event beitreten |
| **Services** | `GET /api/services/` | Services durchsuchen |
| | `POST /api/services/` | Service anbieten |
| | `GET /api/services/recommendations` | Empfehlungen |
| **Forum** | `GET /api/discussions/` | Diskussionen |
| | `POST /api/discussions/` | Thread erstellen |
| | `POST /api/discussions/{id}/posts` | Antworten |
| **Polls** | `GET /api/polls/` | Umfragen |
| | `POST /api/polls/` | Umfrage erstellen |
| | `POST /api/polls/{id}/vote` | Abstimmen |

### Authentifizierung

```bash
# 1. Registrierung
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "johndoe",
    "email": "john@example.com",
    "password": "SecurePass123!"
  }'

# 2. Anmeldung
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "password": "SecurePass123!"
  }'

# 3. Authentifizierte Requests
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  "http://localhost:8000/api/events/"
```

## 🧪 Testing

```bash
# Alle Tests ausführen
python run_tests.py

# Spezifische Tests
python run_tests.py auth      # Authentifizierung
python run_tests.py events    # Event-System
python run_tests.py comments  # Kommentar-System

# Mit Coverage
pytest --cov=app --cov-report=html
```

## 🗄️ Datenbank

### Migrationen

```bash
# Neue Migration erstellen
alembic revision --autogenerate -m "Description"

# Migrationen anwenden
alembic upgrade head

# Migration rückgängig machen
alembic downgrade -1
```

### Haupttabellen
- `users` - Benutzerprofile und Auth
- `events` + `event_participations` - Event-System
- `services` - Service-Exchange
- `forum_threads` + `forum_posts` - Diskussionen
- `polls` + `votes` - Abstimmungssystem
- `comments` - Universelles Kommentar-System

## 🔧 Konfiguration

### Wichtige Einstellungen

```python
# app/config.py
class Settings:
    # Basis-Konfiguration
    APP_NAME: str = "Community Platform API"
    DEBUG: bool = False
    SECRET_KEY: str  # Erforderlich!

    # Datenbank
    DATABASE_URL: str  # PostgreSQL URL
    REDIS_URL: str = "redis://localhost:6379/0"

    # Sicherheit
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    RATE_LIMIT_PER_MINUTE: int = 60

    # Content Moderation
    CONTENT_MODERATION_ENABLED: bool = True
    MODERATION_THRESHOLD: float = 0.7

    # Business Rules
    EVENT_AUTO_ATTENDANCE_ENABLED: bool = True
    SERVICE_MATCHING_ENABLED: bool = True
```

### Produktions-Setup

```bash
# requirements/prod.txt verwenden
pip install -r requirements/prod.txt

# Umgebungsvariablen für Produktion
DEBUG=false
SECRET_KEY="complex-production-secret"
DATABASE_URL="postgresql+asyncpg://user:pass@prod-db/db"

# Mit Gunicorn starten
gunicorn app.main:app -k uvicorn.workers.UvicornWorker
```

## 🏗️ Architektur

```
app/
├── api/              # API Endpoints
│   ├── auth.py       # Authentifizierung
│   ├── events.py     # Event-Management
│   ├── services.py   # Service-Exchange
│   └── ...
├── core/             # Core Funktionalität
│   ├── auth.py       # JWT & Passwort-Handling
│   ├── dependencies.py # FastAPI Dependencies
│   └── middleware.py # CORS, Rate Limiting
├── models/           # SQLAlchemy Models
├── schemas/          # Pydantic Models
├── services/         # Business Logic
│   ├── auth.py       # Auth Service
│   ├── event_service.py # Event Business Logic
│   ├── moderation_service.py # Content Moderation
│   └── ...
└── tests/            # Test Suite
```

## 🤝 Contributing

1. Fork das Repository
2. Feature Branch erstellen (`git checkout -b feature/amazing-feature`)
3. Changes committen (`git commit -m 'Add amazing feature'`)
4. Branch pushen (`git push origin feature/amazing-feature`)
5. Pull Request erstellen

### Code Style

```bash
# Code formatieren
black app/
isort app/

# Linting
flake8 app/
mypy app/
```

## 📊 Monitoring & Admin

### Health Checks
- `GET /health` - System Status
- `GET /api/stats` - Öffentliche Platform-Statistiken

### Admin Dashboard
- `GET /api/admin/dashboard` - Admin Übersicht
- `POST /api/admin/tasks/process-events` - Event-Verarbeitung
- `GET /api/comments/admin/moderation-queue` - Moderation Queue

## 🚀 Deployment

### Docker
```bash
# Vollständige Stack
docker-compose up -d

# Nur API
docker build -t community-api .
docker run -p 8000:8000 community-api
```

### Environment Variables
```bash
# Essentiell für Produktion
SECRET_KEY=          # JWT Secret
DATABASE_URL=        # PostgreSQL Connection
REDIS_URL=          # Redis Connection
SMTP_HOST=          # Email Service
SMTP_USER=          # Email Credentials
SMTP_PASSWORD=      # Email Password
```

## 📝 Lizenz

Dieses Projekt steht unter der MIT Lizenz - siehe [LICENSE](LICENSE) für Details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/your-username/community-network-backend/issues)
- **Dokumentation**: [API Docs](http://localhost:8000/docs)
- **Email**: support@your-platform.com

---

**Built with ❤️ für lokale Communities**
