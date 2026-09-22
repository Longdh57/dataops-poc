# Build tu GOC repo (khong phai tu apps/api/) vi can ca thu muc rules/:
#   docker build -f apps/api/Dockerfile -t <image> .
# Man hinh "Bo luat" doc file luat tu trong image nay — xem app/rules.py.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini .
# Chi de DOC va hien len man hinh. Cho chay luat la image jobs/.
COPY rules ./rules

# Cloud Run cap PORT qua bien moi truong; mac dinh 8080
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
