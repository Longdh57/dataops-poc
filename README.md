# Data Operations WebApp

Ung dung noi bo cho doi nghien cuu du lieu. BigQuery la nguon su that,
Cloud SQL la noi ghi va chiu trach nhiem. Xem `implement-plan.html` cho
ban thiet ke day du.

## Cau truc

| Thu muc | Noi dung |
|---|---|
| `apps/web` | Next.js 16 + TypeScript — giao dien, AG Grid + TanStack Query |
| `apps/api` | FastAPI — phuc vu du lieu, phan quyen |
| `jobs/sync` | BigQuery -> Cloud SQL, chay moi 60s (P2) |
| `jobs/export` | Sinh Excel/CSV tu ban da ky, qua GCS + signed URL |
| `jobs/seed` | Nguoi dung thu nghiem + bang fact demo tren BigQuery |
| `docs` | Runbook van hanh, kich ban demo |
| `infra` | Terraform, state tren GCS |
| `rules` | Bo luat QC khai bao bang YAML |

## Chay local

```bash
docker compose up --build
```

http://localhost:3000 — dashboard, luoi du lieu, hop thu ngoai le.
Doi package.json thi phai dung `docker compose up -d --build --renew-anon-volumes web`,
vi node_modules nam trong anonymous volume.

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
cd apps/api && pytest tests -q     # 25 test
```

## Giao dien (P4)

Nam man hinh, mot thanh loc dung chung, moi thu doc tu API qua mot cong
duy nhat.

| Trang | Lam gi |
|---|---|
| `/` | Dashboard: o chi so, chenh lech so voi ban da ky, ngoai le theo luat va theo khu vuc, trang thai cong |
| `/data` | Luoi 1,2 trieu dong bang AG Grid, cuon lien tuc |
| `/exceptions` | Hop thu ngoai le + panel dieu tra ben phai |
| `/versions` | Ban da ky: ai ky, luc nao, da gui cho khach nao |
| `/requests` | Sale xin file, theo doi trang thai, tai ve khi xong |

### Trinh duyet khong goi thang API

`dataops-api` khong public: chi service account cua web goi duoc bang OIDC
token. Trinh duyet khong co token do, nen moi request di qua route handler
`apps/web/app/api/gw/[...path]/route.ts` — Next.js lay token tu metadata
server roi goi tiep. Co IAP thi chuyen tiep nguyen assertion cua Google;
chua co thi lay danh tinh tu cookie `dataops_as` (duong nay chi mo khi
`REQUIRE_IAP=false`).

### Luoi du lieu: vi sao Client-Side Row Model

API phan trang theo keyset (cursor), khong theo offset — nen khong nhay
den "dong thu 50.000" duoc, ma Infinite Row Model cua AG Grid lai can
dung dieu do. Cach hop voi keyset la noi tiep cac slice 500 dong vao mot
mang trong bo nho va de AG Grid ao hoa phan hien thi. Cuon gan cuoi thi
`onBodyScrollEnd` tu goi slice sau.

Cai gia phai noi ro voi nguoi dung, va giao dien co ghi: **bam tieu de cot
chi sap xep trong so dong da tai**. Muon sap xep toan bo thi doi o "Sap
xep toan bo" — cai do chay o server va nap lai tu dau.

### Khoa lac quan nhin tu giao dien

Panel dieu tra gui kem `expected_version`. Nhan 409 thi KHONG ghi de, ma
hien ba con so — so goc, so tren may chu, so ban muon ghi — cung hai lua
chon: *Tai lai dong* hoac *Ghi de co chu dich*. Ghi de la gui lai voi
`expected_version` moi, tuc la nguoi dung chu dong chap nhan de len ban
cua dong nghiep.

### Hai nut de bam nham

| Nut | Lam gi | Mat bao lau |
|---|---|---|
| **Lam moi bang** | goi lai API, doc ban sao Postgres | vai chuc ms |
| **Nap lai tu nguon** | chay han Sync Job: doc lai BigQuery, staging, doi ten | 30–60s |

Nut thu hai mau do, chi team lead tro len thay, va co mot buoc hoi lai.

### Banner do tuoi

Poll `/api/version` moi 30 giay. Thay `run_id` khac cai dang hien thi thi
hien banner kem nut *Tai lai* — **khong tu lam moi**, vi nguoi dung co the
dang go do dang trong panel dieu tra.

### Endpoint P4 them vao

| Method | Duong dan | Y nghia |
|---|---|---|
| GET | `/api/summary` | toan bo so lieu dashboard trong mot lan goi |
| GET | `/api/options` | gia tri cho thanh loc — cung ap pham vi |
| GET | `/api/exceptions/{id}` | chi tiet cho panel dieu tra, kem `expected_version` |
| GET | `/api/versions` | ban da ky + da gui cho ai |
| POST | `/api/versions/{id}/sent` | ghi nhan da gui cho khach |
| GET | `/api/exports` | job cua chinh minh |
| GET | `/api/exports/{id}/download` | signed URL 15 phut, chan khi cong khoa |
| POST | `/api/rebuild` | kich hoat Sync Job (team_lead tro len) |

### Kich ban da chay tron

Chay tren docker compose local, du lieu that 1.222.947 dong:

1. Dashboard bao 21 ngoai le nghiem trong, cong **KHOA**
2. Mo mot ngoai le -> panel hien so cua lan nap canh ban da ky
3. Sua so -> trong luc do nguoi khac ghi de o duoi database -> **409** kem
   diff, so cua minh khong bi ghi
4. Bam *Ghi de co chu dich* -> ghi thanh cong, `fact_override` len ban 2,
   ngoai le chuyen `applied`, audit log ghi ca truoc lan sau
5. Xu ly not 20 ngoai le con lai -> cong chuyen sang **SAN SANG**
6. Team Lead ky "Ban thang 9 2026 - dot 1" -> vao `signed_version`
7. Doi danh tinh sang sale -> xin file -> job vao hang doi `pending`

Buoc cuoi (file tai ve duoc) can Export Job chay that — do la P5.

### Con thieu so voi plan

- Bo loc "cong ty" trong plan anh xa sang "ten" o bo du lieu nay
  (`usa_names` khong co chieu cong ty).
- Export Job chua dung lich chay, nen job dung o `pending`. Giao dien da
  xu ly du bon trang thai `pending / running / done / error`.

## Hoan thien & ban giao (P5)

### File gui khach xuat tu dau

Cau hoi nghe don gian nhung la cho de sai nhat. Truoc P5, Export Job query
`WHERE run_id IS NOT NULL` — tuc la lay TAT CA lan nap co trong BigQuery.
Do chung tren du lieu that:

| | So dong |
|---|---|
| File xuat ra | 1.318.023 |
| Ban da ky | 1.222.947 |
| Thua | **95.076** |

95 nghin dong do chua qua rule engine, chua qua cong phat hanh, khong nam
trong ban Team Lead da ky.

Goc re: `run_id` la HAI thu khac nhau.

| Cot | Vi du | Ai dat |
|---|---|---|
| `sync_state.last_run_id`, `signed_version.run_id` | `run-20260920T070541` | Sync Job, moi luot dong bo |
| `fact_names.run_id` tren BigQuery | `run-2026-09-20-001` | team Data, moi lan nap du lieu |

Loc BigQuery bang nhan cua Sync Job thi tra ve 0 dong — nen code cu danh
lay tat. P5 noi hai khong gian nay lai:

1. Sync Job ghi `sync_state.source_run_ids` — nhung lan nap dang co trong
   ban sao. Doc tu Postgres sau khi swap nen ton 0 dong chi phi query.
2. Ky phat hanh dong bang danh sach do vao `signed_version.source_run_ids`.
3. Export Job loc `WHERE run_id IN UNNEST(@runs)`.

Ban ky tu truoc P5 khong co danh sach nay se bi Export Job tu choi, kem
thong bao noi ro phai ky lai — thay vi lang le xuat sai.

### Ba rang buoc con lai cua Export Job

- **Pham vi**: sale pham vi CA+TX xin file thi nhan dung 170.682 dong cua
  CA va TX. Pham vi duoc chot luc XIN FILE, khong phai luc job chay — doi
  pham vi cua ho hom sau khong lam doi file da phat.
- **Thi phan tinh lai**: sua mot o thi thi phan ca nhom doi. Khong tinh lai
  thi khach cong cot do se khong ra 100%. Chi tinh lai cho nhom co override;
  nhom khong ai dong toi giu nguyen so cua nguon.
- **Gioi han Excel**: 1.048.576 dong mot sheet. Vuot thi tach sheet va ghi
  canh bao vao `export_job.warning`, KHONG lang le cat bot dong.

### Kich hoat job

`POST /api/exports` goi thang Cloud Run Job kem `EXPORT_JOB_ID`, khong dung
Scheduler poll. Poll moi 1-2 phut se bat nguoi dung cho vo co du hang doi
rong.

Goi that bai — chay local, job chua deploy, thieu quyen — thi yeu cau VAN
nam trong hang doi va API noi ro ly do. Trang thai te nhat la da ghi vao
database ma nguoi dung tuong la chua.

### Bo luat: them `scope` va kiem tra cau hinh

Luat gio co nam phan: `id`, `severity`, `scope` (tuy chon), `message`, `sql`.
Job tu choi chay neu file sai cau truc va bao **het loi mot luot** — file
nay bi sua boi nguoi khong doc code, bao tung loi mot thi ho phai doan.

### Giam sat

| Canh bao | Bat cai gi |
|---|---|
| Sync Job im lang qua 30 phut | Ban sao cu dan ma khong ai biet |
| Cloud Run Job that bai | Job co chay, co bao loi, nhung khong ai doc log |
| Web khong phan hoi | Uptime check tu ba chau luc |

Dashboard `Dataops — do tre dong bo va suc khoe job`: khoang trong tren
bieu do "lan sync thanh cong" chinh la do tre dong bo.

### Terraform hoa toan bo

| Truoc P5 | Sau P5 |
|---|---|
| 3 service account tao bang gcloud | `module.iam` quan ly, co import script |
| Dataset BigQuery tao tay | `module.data` |
| Khong co Export Job, Seed Job | Ca hai trong `module.runtime` |
| `secretAccessor` cap o ca project lan secret | Terraform chi cap o cap secret |

Du an dang chay phai import mot lan truoc khi apply:

```bash
./scripts/import-existing.sh dataops-poc-2026
cd infra && terraform apply
```

Import khong dong toi tai nguyen that — no chi ghi vao state rang tai
nguyen do tu nay thuoc ve Terraform.

### CI/CD: hai buoc bi thieu

Pipeline cu build API va Web, roi deploy. Thieu hai thu khien deploy xong
la hong:

- **Migration khong chay.** Code moi gap schema cu la 500 ngay tren man
  hinh nguoi dung. Gio `deploy-staging` cap nhat image cho job
  `dataops-migrate` roi chay `alembic upgrade head` va **doi xong** truoc
  khi deploy API. Thu tu nay an toan vi migration chi them cot — code cu
  van chay duoc voi schema moi.
- **Image cua job khong duoc cap nhat.** Sync, QC, Export, Seed khong phai
  service nen khong co "deploy". Thieu buoc `gcloud run jobs update` thi
  chung chay code cu mai ma khong ai thay gi bat thuong. Image `jobs` gio
  cung duoc build trong CI.

### Tai lieu

- [docs/runbook.md](docs/runbook.md) — lam moi khac nap lai ra sao, sync
  loi thi lam gi, quay lai phien ban truoc, them nguoi dung, dung lai tu
  project trong
- [docs/demo.md](docs/demo.md) — kich ban trinh bay 5 phut

### Test

```bash
cd apps/api && pytest tests -q   # 28 test: phan quyen, khoa lac quan, cong, export
pytest jobs/tests -q             # 12 test: logic export va bo luat, khong can BigQuery
```

`jobs/tests` chay duoc ma khong can cloud: phan de sai nhat cua Export Job
la ap override, tinh lai thi phan va cat sheet — ca ba deu la ham thuan.

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

### ⚠️ VAN CHUA DONG — web dang mo public

`infra/terraform.tfvars` dang dat `public_access = true`. Bat cu ai co link
deu xem duoc https://dataops-dev.3ddesigns.xyz — KHONG can dang nhap.

Ly do: IAP chua bat duoc (project khong thuoc Organization), ma khong co
IAP thi trinh duyet khong co cach nao dang nhap, moi request deu 403.
Mo tam de xem va demo.

Ly do mo tam da het hieu luc tu P2: trang khong con la ba dong trang thai
nua ma la 1,2 trieu dong du lieu that, kem danh tinh gia lap qua
`X-Dev-User`. Day la mon no nang nhat con lai cua ca du an.

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

- ~~Service account tao bang gcloud~~ — P5 da khai bao trong `module.iam`.
  Con lai mot lan `./scripts/import-existing.sh` truoc khi apply.
- `secretmanager.secretAccessor` van con o CA HAI noi: cap project (tu P0)
  va cap secret (P1). Terraform chi cap o cap secret; go cai cap project
  la lenh `gcloud` co trong runbook, muc "Go quyen thua".
- Pipeline: job `deploy-staging` va `deploy-prod` deploy vao CUNG service,
  cung domain. `gcloud run deploy` cho revision moi 100% traffic ngay, nen
  buoc duyet tay o `deploy-prod` khong con y nghia — code da live tu truoc.
  Sua bang `--no-traffic --tag=staging` khi can tach that.
