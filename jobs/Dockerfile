# Build tu GOC repo (khong phai tu jobs/) — giu nguyen lenh build cu.
# Tu P10 QC Runner doc bo luat tu Postgres (bang qc_rule), khong kem rules/ nua.
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

CMD ["python", "sync/main.py"]
