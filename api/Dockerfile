FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrations ./migrations
# Run as a normal user, not root: a bug in the app then cannot write to the image or touch the system.
RUN useradd --system --uid 10001 --no-create-home app
USER app
# Apply migrations, then serve. `exec` makes uvicorn the main process, so a stop signal reaches it and it can close
# its database connections politely. Port 8000 is NOT published to the host (see deploy/compose.yaml).
CMD ["sh", "-c", "python -m app.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
