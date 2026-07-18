FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# The curated real-data episodes (SKAB) the replay engine + seed read at runtime
# from /app/data/episodes — without these the real-data pump is silently absent.
COPY data ./data
EXPOSE 8000
# Bind to Render's provided $PORT (falls back to 8000 for local `docker run`).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
