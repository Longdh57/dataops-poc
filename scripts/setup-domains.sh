#!/usr/bin/env bash
# Tao domain mapping cho web + api, in ra ban ghi DNS can them o Cloudflare,
# roi doi Google cap chung chi.
#
# Chay SAU khi da verify domain o Search Console.
set -euo pipefail

PROJECT=dataops-poc-2026
REGION=asia-southeast1
WEB_DOMAIN=dataops-dev.3ddesigns.xyz
API_DOMAIN=api-dataops-dev.3ddesigns.xyz

echo "==> Kiem tra domain da verify chua"
if ! gcloud domains list-user-verified --project="$PROJECT" 2>/dev/null | grep -q 3ddesigns.xyz; then
  echo "CHUA VERIFY. Chay truoc:  gcloud domains verify 3ddesigns.xyz"
  exit 1
fi
echo "    OK"

map() {
  local svc=$1 domain=$2
  echo
  echo "==> Mapping $domain -> $svc"
  gcloud beta run domain-mappings create \
    --service="$svc" --domain="$domain" \
    --region="$REGION" --project="$PROJECT" 2>&1 | sed 's/^/    /' || true
}

map dataops-web "$WEB_DOMAIN"
map dataops-api "$API_DOMAIN"

echo
echo "================ BAN GHI CAN THEM O CLOUDFLARE ================"
for d in "$WEB_DOMAIN" "$API_DOMAIN"; do
  echo
  echo "--- $d ---"
  gcloud beta run domain-mappings describe --domain="$d" \
    --region="$REGION" --project="$PROJECT" \
    --format='table(status.resourceRecords[].name,status.resourceRecords[].type,status.resourceRecords[].rrdata)' 2>/dev/null \
    | sed 's/^/    /'
done
echo
echo "QUAN TRONG: Proxy status phai la 'DNS only' (may xam), KHONG bat proxy."
echo
echo "Theo doi trang thai chung chi:"
echo "  bash scripts/check-domains.sh"
