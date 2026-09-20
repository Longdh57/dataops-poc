#!/usr/bin/env bash
# Dua nhung thu tao tay bang gcloud vao duoi quyen quan ly cua Terraform.
#
# Chay MOT LAN cho du an dang chay. Project trong khong can chay — terraform
# apply tu tao moi thu.
#
# Import khong dong toi tai nguyen that: no chi ghi vao state rang
# "tai nguyen nay thuoc ve khoi Terraform nay". Import trung thi lenh bao
# loi "Resource already managed" va bo qua duoc.

set -uo pipefail

PROJECT="${1:-dataops-poc-2026}"
DATASET="${2:-dataops_src}"
cd "$(dirname "$0")/../infra" || exit 1

echo "Project: $PROJECT · dataset: $DATASET"
echo

for key in api web jobs; do
  sa="dataops-${key}@${PROJECT}.iam.gserviceaccount.com"
  echo "--- service account $sa"
  terraform import "module.iam.google_service_account.runtime[\"${key}\"]" \
    "projects/${PROJECT}/serviceAccounts/${sa}" 2>&1 | tail -2
done

echo
for key in api jobs; do
  sa="dataops-${key}@${PROJECT}.iam.gserviceaccount.com"
  for role in roles/bigquery.dataViewer roles/bigquery.jobUser roles/cloudsql.client; do
    echo "--- $key $role"
    terraform import "module.iam.google_project_iam_member.runtime[\"${key}:${role}\"]" \
      "${PROJECT} ${role} serviceAccount:${sa}" 2>&1 | tail -2
  done
done

echo
echo "--- dataset BigQuery ${DATASET}"
terraform import "module.data.google_bigquery_dataset.src" \
  "projects/${PROJECT}/datasets/${DATASET}" 2>&1 | tail -2

cat <<'NOTE'

Xong phan import. Hai viec con lai phai lam bang tay vi chung XOA quyen:

1. Go secretmanager.secretAccessor o cap project. Quyen nay dang duoc cap
   o CA HAI noi — cap project (tu P0, tao tay) va dung tren mot secret
   (module database). Giu ca hai khien cau hoi "ai doc duoc bi mat nao"
   tra ve cau tra loi sai.

   gcloud projects remove-iam-policy-binding PROJECT \
     --member=serviceAccount:dataops-api@PROJECT.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor
   gcloud projects remove-iam-policy-binding PROJECT \
     --member=serviceAccount:dataops-jobs@PROJECT.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor

   Kiem lai truoc khi go: Cloud Run phai van doc duoc secret nho binding
   o cap secret. Xem runbook, muc "Go quyen thua".

2. Sau khi import xong, co the xoa ba dong api/web/jobs_service_account
   trong terraform.tfvars — Terraform tu dung tai khoan no quan ly.
   Giu lai cung khong sao: gia tri y het nhau.
NOTE
