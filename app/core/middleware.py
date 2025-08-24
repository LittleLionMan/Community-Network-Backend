from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import time
import logging

limiter = Limiter(key_func=get_remote_address)

def setup_middleware(app: FastAPI):

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8080"],  # Frontend URLs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) #type: ignore
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()

        logging.info(f"{request.method} {request.url}")

        response = await call_next(request)

        process_time = time.time() - start_time
        logging.info(f"Response: {response.status_code} - {process_time:.3f}s")

        return response
