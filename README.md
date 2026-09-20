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

## Du lieu (P2)

Nguon: `bigquery-public-data.usa_names.usa_1910_current` — ten khai sinh
o Hoa Ky theo bang, gioi tinh, nam. Du lieu that do Cuc An sinh Xa hoi My
cong bo, khong phai so tu sinh.

### Xem tren BigQuery

```bash
bq query --use_legacy_sql=false --location=asia-southeast1 \
 'SELECT run_id, COUNT(*) FROM `dataops-poc-2026.dataops_src.fact_names` GROUP BY run_id'
```

Hoac Console: BigQuery -> dataops-poc-2026 -> dataops_src -> fact_names

| | |
|---|---|
| Bang fact | `dataops-poc-2026.dataops_src.fact_names` |
| Partition | `DATE(loaded_at)` — moi lan nap mot partition |
| Cluster | `state, gender, year` |
| Cot | run_id, loaded_at, year, state, gender, name, number, market_share, prev_number, prev_year |

`market_share` = ty trong cua mot ten trong tong so tre cung (nam, bang,
gioi tinh). Cong lai dung bang 1.0 o ca 1.224 nhom — day la co so cho
luat QC `market_share_sum`.

### Xem tren Postgres

Cloud SQL chi co private IP nen khong noi truc tiep tu may ca nhan duoc.
Xem qua giao dien hoac API:

- Giao dien: https://dataops-dev.3ddesigns.xyz
- `GET /api/schema` — toan bo bang kem so dong va dung luong
- `GET /api/facts?state=CA&year=2021&gender=F` — du lieu that
- `GET /api/version` — do tuoi ban sao

Duoi local thi noi thang duoc:

```bash
docker exec dashboard-bigquery-db-1 psql -U dataops -d dataops -c '\d fact_current'
```

### Sync Job

```
07:29:05  team Data INSERT vao BigQuery
07:29:24  Scheduler kich hoat, job phat hien thay doi   (+19s)
07:29:56  Postgres phan anh xong                        (+51s tong)
```

Phat hien thay doi bang `__TABLES__` — truy van metadata, **quet 0 byte**,
nen poll moi 60 giay ca ngay khong ton dong nao.

Nap: EXPORT DATA -> parquet tren GCS -> COPY vao `fact_staging` ->
doi ten trong mot transaction. Da kiem chung 1.062 request doc dong thoi
trong luc doi ten: **0 that bai**.

Migration chay bang Cloud Run Job vi Cloud SQL chi co private IP:

```bash
gcloud run jobs execute dataops-migrate --region=asia-southeast1
```

### Bai hoc ve hieu nang

Lan dau sync mat **229s** — vuot tieu chi 2 phut. Do log thi 199s trong
so do la dung index, khong phai COPY. Nguyen nhan: `db-f1-micro` chi co
~0,6GB RAM nen `maintenance_work_mem` mac dinh rat nho, sap xep khi build
index tran ra dia PD_HDD.

Hai lenh `SET` trong Sync Job dua xuong **33,2s** — nhanh hon 7 lan,
khong doi phan cung, khong ton them tien:

```sql
SET maintenance_work_mem = '160MB';
SET synchronous_commit = off;
```

`synchronous_commit = off` an toan o day vi bang staging la du lieu dung
mot lan — hong thi sync lai tu BigQuery.

## Phan quyen & cong phat hanh (P3)

### Nguyen tac khong duoc pha

Pham vi du lieu LUON lay tu database theo email, KHONG BAO GIO lay tu
tham so client. Client gui `?state=CA` chi la mot y kien; dieu kien that
la GIAO giua tham so do va pham vi duoc gan trong `app_role`.

Kiem chung tren ha tang that:

| Nguoi dung | Pham vi | Goi gi | Nhan duoc |
|---|---|---|---|
| analyst.tx | TX | `/api/facts` | chi TX |
| analyst.tx | TX | `/api/facts?state=CA` | **0 dong** |
| analyst.ca | CA | `/api/facts` | chi CA |
| sale | CA+TX | `/api/exceptions` | 95 = 44 CA + 51 TX |

Tra ve rong chu khong phai 403, de khong ro ri thong tin bang nao ton tai.

### Khoa lac quan

Moi dong co `version`. Sua voi `expected_version` cu thi nhan 409 kem diff:

```json
{
  "loi": "co nguoi khac vua sua dong nay",
  "expected_version": 0, "current_version": 1,
  "gia_tri_goc": 127, "gia_tri_hien_tai": 777, "gia_tri_ban_muon_ghi": 111
}
```

Gia tri KHONG bi ghi de — nguoi dung tu quyet dinh tai lai hay ghi de co
chu dich.

### Cong phat hanh

Con ngoai le `critical` dang mo thi khong ai ky va khong ai tai file duoc:

| Thao tac | Ket qua |
|---|---|
| Team Lead ky khi cong khoa | 409 + so ngoai le con lai |
| Analyst thu ky | 403 — sai vai tro |
| Tai file khi cong khoa | 409 |

### Endpoint

| Method | Duong dan | Y nghia |
|---|---|---|
| GET | `/api/me` | danh tinh, vai tro, pham vi |
| GET | `/api/facts` | loc, sap xep (allowlist), phan trang keyset, merge override |
| GET | `/api/exceptions` | hop thu ngoai le trong pham vi |
| PATCH | `/api/exceptions/{id}` | apply / park / send_back — mot transaction |
| GET | `/api/gate` | trang thai cong phat hanh |
| POST | `/api/release` | ky ban so lieu (team_lead) |
| POST | `/api/exports` | 202 + job_id |

### Bo luat QC

`rules/rules.yaml` — them luat moi chi can them mot muc, khong sua code.
Nguong dat tu profile du lieu that:

| Luat | Muc | Bat duoc |
|---|---|---|
| thi_phan_khong_tron_100 | critical | 0 — kiem tra toan ven |
| duoi_nguong_kiem_duyet | critical | 0 — SSA khong cong bo duoi 5 |
| tang_dot_bien | critical | 23 |
| ten_pho_bien_bien_mat | critical | 1 |
| bien_dong_bat_thuong | warning | 405 |

```bash
gcloud run jobs execute dataops-qc --region=asia-southeast1
```

### Danh tinh khi chua co IAP

IAP chua bat duoc nen `REQUIRE_IAP=false`, danh tinh lay tu header
`X-Dev-User`. Giao dien co bo chon danh tinh de thay phan quyen hoat dong:

https://dataops-dev.3ddesigns.xyz/?as=analyst.tx@dataops.test

Bat IAP len thi `REQUIRE_IAP` tu chuyen sang true (buoc theo `iap_enabled`
trong Terraform), danh tinh den tu JWT Google ky va khong gia duoc.
Ma verify IAP JWT da viet san trong `app/auth.py` — kiem ca chu ky,
issuer lan audience, va KHONG tin header `x-goog-authenticated-user-email`
vi header do gia duoc neu goi thang vao URL run.app.

### Test

```bash
cd apps/api && pytest tests -q     # 14 test
```

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

### ⚠️ PHAI DONG TRUOC P2 — web dang mo public

`infra/terraform.tfvars` dang dat `public_access = true`. Bat cu ai co link
deu xem duoc https://dataops-dev.3ddesigns.xyz — KHONG can dang nhap.

Ly do: IAP chua bat duoc (project khong thuoc Organization), ma khong co
IAP thi trinh duyet khong co cach nao dang nhap, moi request deu 403.
Mo tam de xem va demo.

Chap nhan duoc BAY GIO vi trang chi co ba dong trang thai, khong co du
lieu. P2 la luc du lieu that tu BigQuery do vao Postgres — truoc do PHAI:

```bash
# trong infra/terraform.tfvars: public_access = false
cd infra && terraform apply
```

Kiem chung da dong:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://dataops-dev.3ddesigns.xyz
# phai tra ve 403
```

Chi WEB duoc mo. API van dong kin, chi `dataops-web` goi duoc bang OIDC token.

Cach go tan goc: dang ky Cloud Identity Free cho `3ddesigns.xyz` -> project
co Organization -> IAP tu cap OAuth client -> bo duoc `public_access` han.

### Cac mon khac

- `dataops-api`, `dataops-jobs`, `dataops-web` service account dang tao
  bang gcloud, chua nam trong Terraform. P5 ("Terraform hoa toan bo") phai
  `terraform import` chung vao.
- Quyen `secretmanager.secretAccessor` cua `dataops-api` dang co o CA HAI
  noi: cap project (tu P0) va cap secret (P1). Nen go cai cap project.
- Pipeline: job `deploy-staging` va `deploy-prod` deploy vao CUNG service,
  cung domain. `gcloud run deploy` cho revision moi 100% traffic ngay, nen
  buoc duyet tay o `deploy-prod` khong con y nghia — code da live tu truoc.
  Sua bang `--no-traffic --tag=staging` khi can tach that.
