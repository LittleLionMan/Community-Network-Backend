from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import structlog
from contextlib import asynccontextmanager

from app.config import settings
from app.api import auth, users#, events, services, discussions, governance

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger = structlog.get_logger()
    logger.info("Community Platform API starting up")

    yield  # App läuft

    # Shutdown
    logger.info("Community Platform API shutting down")

# FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# API Routes
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
#app.include_router(events.router, prefix="/api/events", tags=["events"])
#app.include_router(services.router, prefix="/api/services", tags=["services"])
#app.include_router(discussions.router, prefix="/api/discussions", tags=["discussions"])
#app.include_router(governance.router, prefix="/api/governance", tags=["governance"])

# Health check
@app.get("/health")
async def health_check(request: Request):
    return {"status": "healthy", "version": settings.VERSION}
