from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import structlog
from contextlib import asynccontextmanager

from app.config import settings
from app.api import auth, users, event_categories, events, services, discussions, comments, polls

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = structlog.get_logger()
    logger.info("Community Platform API starting up")

    yield

    logger.info("Community Platform API shutting down")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(event_categories.router, prefix="/api/event-categories", tags=["event-categories"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(discussions.router, prefix="/api/discussions", tags=["discussions"])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"])
app.include_router(polls.router, prefix="/api/polls", tags=["polls"])

@app.get("/health")
async def health_check(request: Request):
    return {"status": "healthy", "version": settings.VERSION}
