FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY server ./server
COPY collector ./collector
COPY alembic.ini ./
RUN pip install --no-cache-dir -e ".[server]"
CMD ["sh", "-c", "alembic upgrade head && uvicorn server.main:app --host 0.0.0.0 --port 8000"]
