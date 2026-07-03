import logging
import uuid
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from server.config import get_settings
from server.routes import ingest, reads
from server.worker import make_enqueue

logger = logging.getLogger("agentdiff.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    app.state.enqueue = make_enqueue(pool)
    # Expose the same arq pool for rate-limiting (ArqRedis IS a redis client).
    app.state.redis_pool = pool
    yield
    await pool.aclose()


app = FastAPI(title="AgentDiff Hosted", lifespan=lifespan)
app.state.enqueue = None
app.state.redis_pool = None


# ── Body-size cap ────────────────────────────────────────────────────────────

class BodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds max_body_bytes with 413."""

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > get_settings().max_body_bytes:
                    return Response(
                        content="Request body too large",
                        status_code=413,
                        media_type="text/plain",
                    )
            except ValueError:
                pass
        return await call_next(request)


# ── Request-ID middleware ────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request-id to every request and response; log one line per request."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "request_id": request_id,
            },
        )
        return response


# Register middleware (outermost last — Starlette wraps in reverse order).
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(BodySizeMiddleware)

app.include_router(ingest.router)
app.include_router(reads.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
