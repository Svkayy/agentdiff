from fastapi import FastAPI

from server.routes import ingest

app = FastAPI(title="AgentDiff Hosted")
app.state.enqueue = None
app.include_router(ingest.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
