#!/usr/bin/env bash
# Xem Google da cap chung chi cho domain mapping chua.
set -uo pipefail

PROJECT=dataops-poc-2026
REGION=asia-southeast1

for d in dataops-dev.3ddesigns.xyz api-dataops-dev.3ddesigns.xyz; do
  echo "--- $d ---"
  echo "    CNAME    : $(dig +short "$d" CNAME 2>/dev/null | head -1)"
  gcloud beta run domain-mappings describe --domain="$d" --region="$REGION" \
    --project="$PROJECT" --format=json 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: print('    (chua co mapping)'); sys.exit()
for c in d.get('status',{}).get('conditions',[]):
    if c.get('type') in ('CertificateProvisioned','DomainRoutable','Ready'):
        print(f\"    {c['type']:23}: {c.get('status')} {c.get('reason','')}\".rstrip())
"
  echo "    HTTPS    : $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$d" 2>/dev/null)"
done
