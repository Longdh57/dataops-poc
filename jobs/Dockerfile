# Build tu GOC repo (khong phai tu jobs/) vi can ca thu muc rules/.
#   gcloud builds submit --config=jobs/cloudbuild.yaml .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY jobs/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jobs/sync ./sync
COPY jobs/export ./export
COPY jobs/qc ./qc
COPY jobs/seed ./seed
COPY rules ./rules

CMD ["python", "sync/main.py"]
