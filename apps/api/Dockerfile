# Build tu GOC repo (khong phai tu apps/api/) vi can ca thu muc rules/:
#   docker build -f apps/api/Dockerfile -t <image> .
# Tu P10 bo luat song trong Postgres; rules/ chi con la SEED cho migration p10.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini .
# Seed cho migration p10 (alembic chay trong image nay). Khong nam tren duong request.
COPY rules ./rules

# Cloud Run cap PORT qua bien moi truong; mac dinh 8080
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
