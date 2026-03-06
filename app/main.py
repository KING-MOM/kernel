import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.logging_config import setup_logging
from app.api.routes import router
from app.api.routes_read import read_router
from app.api.dependencies import get_db
from app.db.database import Base, engine

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    Base.metadata.create_all(bind=engine)
    logger.info("Kernel API v%s started", get_settings().version)
    yield
    logger.info("Kernel API shutting down")


app = FastAPI(title="Kernel API", version=get_settings().version, lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    settings = get_settings()
    return {"status": "ok", "version": settings.version}


app.include_router(router)
app.include_router(read_router)
