# Mot image cho ca Sync Job lan Export Job; chon bang tham so khi chay.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sync ./sync
COPY export ./export

# Mac dinh chay sync; Export Job ghi de bang args.
CMD ["python", "sync/main.py"]
