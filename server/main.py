from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from server.config import get_settings
from server.routes import ingest
from server.worker import make_enqueue


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    app.state.enqueue = make_enqueue(pool)
    yield
    await pool.aclose()


app = FastAPI(title="AgentDiff Hosted", lifespan=lifespan)
app.state.enqueue = None
app.include_router(ingest.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
