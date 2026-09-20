# Data Operations WebApp

Ung dung noi bo cho doi nghien cuu du lieu. BigQuery la nguon su that,
Cloud SQL la noi ghi va chiu trach nhiem. Xem `implement-plan.html` cho
ban thiet ke day du.

## Cau truc

| Thu muc | Noi dung |
|---|---|
| `apps/web` | Next.js 16 + TypeScript — giao dien |
| `apps/api` | FastAPI — phuc vu du lieu, phan quyen |
| `jobs/sync` | BigQuery -> Cloud SQL, chay moi 60s (P2) |
| `jobs/export` | Sinh Excel/CSV qua GCS + signed URL (P6) |
| `infra` | Terraform, state tren GCS |
| `rules` | Bo luat QC khai bao bang YAML |

## Chay local

```bash
docker compose up --build
```

http://localhost:3000 — ba dong phai xanh het.

## Ha tang da dung (P1)

| Hang muc | Gia tri |
|---|---|
| Project | `dataops-poc-2026` · number `503189459024` |
| Region | `asia-southeast1` |
| VPC | `dataops-vpc` · subnet `10.10.0.0/24` |
| Cloud SQL | `dataops-pg-42c6` · POSTGRES_17 · db-f1-micro · **chi private IP** `10.70.0.3` |
| Cloud Run | `dataops-web`, `dataops-api` — scale-to-zero, Direct VPC egress |
| Registry | `asia-southeast1-docker.pkg.dev/dataops-poc-2026/dataops` |
| Secret | `dataops-database-url` — gan vao Cloud Run luc chay |
| TF state | `gs://dataops-poc-2026-tfstate/poc` |

Hai service KHONG public: khong co binding `allUsers`, request khong
xac thuc tra 403. Truy cap de kiem tra:

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" https://dataops-web-503189459024.asia-southeast1.run.app
```

## Hai viec con lai cua P1 — can lam bang browser

Ca hai deu vuong cung mot goc: **project khong thuoc Organization nao**
(tai khoan gmail ca nhan).

### 1. Bat IAP

IAP tren Cloud Run can OAuth client. API `gcloud iap oauth-brands` tra ve
`Project must belong to an organization`, va API do da bi Google dong vinh
vien tu 19/03/2026. Phai tao tay:

1. Console -> APIs & Services -> OAuth consent screen -> chon **External**
2. Tao OAuth 2.0 Client ID (Web application), redirect URI:
   `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect`
3. Console -> Security -> Identity-Aware Proxy -> bat cho tung Cloud Run service
4. Sau do trong `infra/terraform.tfvars` dat `iap_enabled = true` roi apply

Cach sach hon: dang ky **Cloud Identity Free** cho `3ddesigns.xyz`. Project
se co Organization, IAP tu cap OAuth client, va tao duoc Google Group that
de quan ly nguoi dung nhu plan mo ta.

### 2. Domain mapping

`gcloud domains list-user-verified` dang trong. Phai verify quyen so huu
`3ddesigns.xyz` truoc:

```bash
gcloud domains verify 3ddesigns.xyz
```

Lenh nay mo Search Console. Verify xong:

```bash
gcloud beta run domain-mappings create --service=dataops-web --domain=dataops-dev.3ddesigns.xyz --region=asia-southeast1
gcloud beta run domain-mappings create --service=dataops-api --domain=api-dataops-dev.3ddesigns.xyz --region=asia-southeast1
```

Ban ghi CNAME o Cloudflare phai de **DNS only**, khong bat proxy — bat
proxy thi Google khong cap duoc chung chi.

### 3. CI/CD

`.github/workflows/deploy.yml` da san sang. De bat:

1. Dat `github_repo = "owner/repo"` trong `infra/terraform.tfvars`, apply
2. Lay output `workload_identity_provider` va `deployer_email`
3. GitHub -> Settings -> Secrets and variables -> Actions -> Variables:
   `GCP_PROJECT_ID`, `GCP_REGION`, `WIF_PROVIDER`, `DEPLOYER_SA`
4. Settings -> Environments -> tao `production`, dat required reviewer
   de co buoc duyet tay

## Terraform

```bash
cd infra && terraform init && terraform plan
```

Bien quan trong trong `terraform.tfvars`:

| Bien | Y nghia |
|---|---|
| `iap_enabled` | `false` cho toi khi co OAuth client |
| `github_repo` | de trong thi bo qua toan bo CI/CD |
| `iap_members` | ai duoc mo ung dung |

## Con no ky thuat

- `dataops-api`, `dataops-jobs`, `dataops-web` service account dang tao
  bang gcloud, chua nam trong Terraform. P5 ("Terraform hoa toan bo") phai
  `terraform import` chung vao.
- Quyen `secretmanager.secretAccessor` cua `dataops-api` dang co o CA HAI
  noi: cap project (tu P0) va cap secret (P1). Nen go cai cap project.
