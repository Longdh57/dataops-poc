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
REGION="${3:-asia-southeast1}"
# Dataset analytics KHONG nam trong tfvars: gia tri lay tu default cua
# module data (bien analytics_dataset_id). Doi thi phai doi ca hai noi.
ANALYTICS="${4:-dataops_analytics}"
cd "$(dirname "$0")/../infra" || exit 1

echo "Project: $PROJECT · dataset: $DATASET / $ANALYTICS · region: $REGION"
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

# Dataset analytics cung BAT BUOC phai import, cung ly do voi Export Job:
# no da ton tai that tu P7, tao lai la loi 409 va apply dung giua chung.
echo
echo "--- dataset BigQuery ${ANALYTICS}"
terraform import "module.data.google_bigquery_dataset.analytics" \
  "projects/${PROJECT}/datasets/${ANALYTICS}" 2>&1 | tail -2

# --- Export Job va cac binding di kem, tao tay bang gcloud khi P5 chua apply ---
#
# Job BAT BUOC phai import: tao lai mot job da ton tai la loi 409, apply
# se dung giua chung. Ba binding IAM thi khong bat buoc — google_*_iam_member
# la loai khong doc quyen (non-authoritative), them mot member da co san
# chi la thao tac rong. Import van hon: de state noi dung su that.

API_SA="dataops-api@${PROJECT}.iam.gserviceaccount.com"

echo
echo "--- Cloud Run Job dataops-export"
terraform import "module.runtime.google_cloud_run_v2_job.export" \
  "projects/${PROJECT}/locations/${REGION}/jobs/dataops-export" 2>&1 | tail -2

echo
echo "--- quyen API chay Export Job kem overrides"
terraform import "module.runtime.google_cloud_run_v2_job_iam_member.api_invoke_export" \
  "projects/${PROJECT}/locations/${REGION}/jobs/dataops-export roles/run.jobsExecutorWithOverrides serviceAccount:${API_SA}" 2>&1 | tail -2

echo
echo "--- quyen API tu ky URL (IAM SignBlob)"
terraform import "module.runtime.google_service_account_iam_member.api_self_sign" \
  "projects/${PROJECT}/serviceAccounts/${API_SA} roles/iam.serviceAccountTokenCreator serviceAccount:${API_SA}" 2>&1 | tail -2

echo
echo "--- quyen API doc bucket staging"
terraform import "module.storage.google_storage_bucket_iam_member.readers[\"${API_SA}\"]" \
  "b/${PROJECT}-staging roles/storage.objectViewer serviceAccount:${API_SA}" 2>&1 | tail -2

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
