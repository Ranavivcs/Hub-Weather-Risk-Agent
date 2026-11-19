# Stage 1: build the React chat UI.
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python API that also serves the built UI.
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
# Bake the public data into the image at build time, so the running service never depends on
# Open-Meteo/FEMA being up. Conversations written at runtime are lost on redeploy (acceptable for a demo).
RUN python -m app.ingest
COPY --from=ui /ui/dist frontend/dist
EXPOSE 8000
# --proxy-headers: behind Render's proxy, take the client IP from X-Forwarded-For (used by the rate limit).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
