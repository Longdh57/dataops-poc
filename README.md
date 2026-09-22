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

http://localhost:3000 — dashboard, luoi du lieu, vi pham QC, ticket.
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

## Du lieu (P2, doi nguon o P8)

Nguon: [FDIC Summary of Deposits](https://banks.data.fdic.gov/bankfind-suite/SOD)
(`api.fdic.gov/banks/sod`) — deposit cua tung to chuc ngan hang FDIC bao
hiem, khao sat hang nam vao 30/6. Du lieu that, cong khai, khong can API
key. Truoc P8 dung `bigquery-public-data.usa_names` (ten khai sinh o My)
lam du lieu mau vi cung dang `year, state, <2 truc khac>, so do` — xem
[docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md) cho boi canh
doi dataset.

**Khac voi nguon cu**: FDIC KHONG co san tren `bigquery-public-data` (chi
co snapshot to chuc/chi nhanh, khong co lich su theo nam), nen
`jobs/seed/main.py` tu goi API roi nap vao BigQuery — xem muc
[Seed Job](#seed-job-p8) o duoi.

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
| Cluster | `state, institution_id, year` |
| Cot | run_id, loaded_at, year, state, institution_id, institution, deposit, deposit_share, prev_deposit, prev_year |

`institution_id` (CERT cua FDIC) la khoa THAT cua mot to chuc —
`institution` (ten hien thi) khong dung lam khoa duoc vi FDIC ghi ten
khong nhat quan cach viet hoa/thuong giua cac nam (vi du "Keybank" nam
2022 vs "KeyBank" tu 2023, cung mot CERT).

`deposit_share` = ty trong deposit cua mot to chuc trong tong deposit cua
ca bang, nam do. Cong lai dung bang 1.0 o moi nhom `(year, state)` — day
la co so cho luat QC `thi_phan_khong_tron_100`.

### Xem tren Postgres

Cloud SQL chi co private IP nen khong noi truc tiep tu may ca nhan duoc.
Xem qua giao dien hoac API:

- Giao dien: https://dataops-dev.3ddesigns.xyz
- `GET /api/schema` — toan bo bang kem so dong va dung luong
- `GET /api/facts?state=CA&year=2026` — du lieu that
- `GET /api/version` — do tuoi ban sao

Duoi local thi noi thang duoc:

```bash
docker exec dashboard-bigquery-db-1 psql -U dataops -d dataops -c '\d fact_current'
```

### Seed Job (P8)

`jobs/seed/main.py` (chi chay tay, `SEED_BIGQUERY=1`, xem docstring "day la
buoc dung moi truong demo, khong phai duong chay hang ngay"):

1. Goi `api.fdic.gov/banks/sod` phan trang (`limit=10000` + `offset`), lay
   `SEED_YEAR_COUNT` nam gan nhat (mac dinh 5) tinh tu nam moi nhat FDIC co
   — khong hard-code nam cu the.
2. Nap (LOAD) du lieu tho muc CHI NHANH vao bang tam
   `dataops_src.sod_raw_stage` tren BigQuery.
3. Mot cau SQL gop tu chi nhanh len to chuc (`GROUP BY year, state,
   institution_id`), tinh `deposit_share` va `prev_deposit`/`prev_year`
   bang window function — cung mot ky thuat `LAG(...) OVER (...)` nhu
   truoc, chi doi truc partition.

```bash
GCP_PROJECT_ID=dataops-poc-2026 SEED_BIGQUERY=1 SEED_YEAR_COUNT=5 \
  python jobs/seed/main.py
```

Da chay that: 5 nam (2022–2026) → 385.625 dong chi nhanh → gop con
**31.502 dong** to chuc.

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

Cac con so duoi day do luc con dung `usa_names` (~1,2 trieu dong) — dataset
FDIC hien tai gon hon (31,5 nghin dong) nen sync nhanh hon nhieu, nhung bai
hoc ve `maintenance_work_mem` van dung, chi la khong con la nut that.

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
| sale | CA+TX | `/api/exceptions` | 84 = 37 CA + 47 TX |

Tra ve rong chu khong phai 403, de khong ro ri thong tin bang nao ton tai.

### ~~Khoa lac quan~~ — go o P6

P3 co khoa lac quan tren `fact_override`: hai phien sua cung mot o thi phien
sau nhan 409 kem diff. P6 bo han viec sua so, nen khong con hai phien nao
tranh nhau mot o de ma khoa.

Cho tranh chap chuyen sang bang `ticket`, va duoc giai bang mot rang buoc
o tang database thay vi mot cot `version`: partial unique index
`uq_ticket_open_key` chi cho DUNG MOT ticket dang song tren moi o. Nguoi thu
hai nhan 409 kem id cua ticket da co — khong co cach nao de hai dieu kien
nghiem thu mau thuan cung ton tai.

### Cong phat hanh

Tu P6, vi pham luat KHONG con khoa cong — xem muc [Quy trinh chat luong
(P6)](#quy-trinh-chat-luong-p6). Chi hai thu khoa cung:

| Thao tac | Ket qua |
|---|---|
| Ky khi con ticket dang chan | 409 + danh sach ticket |
| Ky khi QC chua kiem lan nap hien tai | 409 — danh sach vi pham dang hien la cua lan truoc |
| Ky khi con no ma khong co phieu duyet | 422 |
| Analyst thu ky | 403 — sai vai tro |
| Tai file khi con ticket chan | 409 |

### Endpoint

| Method | Duong dan | Y nghia |
|---|---|---|
| GET | `/api/me` | danh tinh, vai tro, pham vi |
| GET | `/api/facts` | loc, sap xep (allowlist), phan trang keyset; so LUON la so nguon |
| GET | `/api/exceptions` | vi pham cua lan nap hien tai, trong pham vi |
| POST | `/api/tickets` | bao loi cho team Data — bat buoc co `expected_value` |
| GET | `/api/tickets` | ticket trong pham vi |
| PATCH | `/api/tickets/{id}` | mark_fixed / set_blocking / cancel. KHONG co close |
| GET | `/api/gate` | mon no + hai thu khoa cung |
| POST | `/api/release` | ky ban so lieu (team_lead), kem phieu duyet |
| POST | `/api/exports` | 202 + job_id |

### Bo luat QC

`rules/rules.yaml` — them luat moi chi can them mot muc, khong sua code.
Nguong dat tu profile du lieu that:

| Luat | Muc | Bat duoc (chay that tren 5 nam FDIC, 31.502 dong) |
|---|---|---|
| thi_phan_khong_tron_100 | critical | 0 — kiem tra TONG ca nhom (year,state) ≈ 1.0 |
| deposit_share_sai_cong_thuc | critical | 0 — kiem TUNG dong: `deposit_share` phai khop `deposit / tong deposit ca bang`, chi ra dung o nao sai (khac voi luat tren, chi biet ca nhom lech) |
| deposit_am_hoac_khong | critical | 509 — deposit <= 0 |
| tang_dot_bien | critical | 29 — deposit tang >15 lan so nam truoc |
| to_chuc_bien_mat_roi_quay_lai | critical | 0 |
| bien_dong_bat_thuong | warning | 96 |

Tu P6, `severity` chi con de xep thu tu doc va de loc — no khong quyet dinh
duoc gi nua. Chi ticket moi chan phat hanh.

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
| `/` | Dashboard: o chi so, chenh lech so voi ban da ky, vi pham theo luat va theo khu vuc, trang thai cong |
| `/data` | Luoi 1,2 trieu dong bang AG Grid, cuon lien tuc |
| `/exceptions` | Vi pham cua lan nap hien tai + panel dieu tra ben phai |
| `/tickets` | Ticket gui team Data — P6 |
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

### Panel dieu tra nhin tu giao dien

Tu P6 panel chi de DOC va de quyet dinh. No dat ban da ky gan nhat canh lan
nap hien tai — cau hoi that su la "so nay co that su doi khong", chu khong
phai "sua thanh bao nhieu". O nhap duy nhat con lai la *So dung phai la*, va
no khong ghi vao du lieu: no thanh dieu kien nghiem thu cua mot ticket.

O nao da co ticket thi panel hien nguyen trang thai ticket do thay cho form,
kem hai viec lam duoc: *Nguon da sua — nho QC xac minh*, va *Bao nham — huy
ticket*. Khong co nut dong.

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
| GET | `/api/exceptions/{id}` | chi tiet cho panel dieu tra, kem ticket cua o do |
| GET | `/api/versions` | ban da ky + da gui cho ai |
| POST | `/api/versions/{id}/sent` | ghi nhan da gui cho khach |
| GET | `/api/exports` | job cua chinh minh |
| GET | `/api/exports/{id}/download` | signed URL 15 phut, chan khi con ticket chan |
| POST | `/api/rebuild` | kich hoat Sync Job (team_lead tro len) |

### Kich ban da chay tron

Chay tren docker compose local, du lieu that 1.222.947 dong:

1. Dashboard bao 382 vi pham (21 nghiem trong), cong **cho ky kem phieu duyet**
2. Mo mot vi pham -> panel hien so cua lan nap canh ban da ky
3. Mo ticket voi `expected_value` -> cong chuyen **KHOA**, badge tab do
4. Bam *Da sua nguon* -> ticket sang `awaiting_verify`, van chan
5. Chay lai QC khi nguon chua doi that -> ticket **bat nguoc ve `open`** kem
   so doc duoc
6. Go chan ticket (team lead, co ly do) -> ky kem phieu duyet -> `signed_version`
   ghi van tay, so vi pham theo luat, version luat, ticket chua dong
7. Doi danh tinh sang sale -> xin file -> job vao hang doi `pending`

Buoc 1–6 la kich ban P6, da chay tron tren docker compose local. Buoc cuoi
(file tai ve duoc) can Export Job chay that.

### Con thieu so voi plan

- ~~Bo loc "cong ty" trong plan anh xa sang "ten" o bo du lieu nay~~ — het
  con no tu P8: dataset FDIC co dung chieu to chuc (`institution`), bo loc
  o giao dien la tim theo ten to chuc that.
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
- **Thi phan giu nguyen cua nguon**: tu P6 khong ai sua so nua, nen khong
  con phai tinh lai thi phan — con so cua BigQuery da dung san. Day la mot
  nhanh code phuc tap bien mat theo bang `fact_override`.
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
- [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md) — quy trinh
  chat luong: loi di vao tu dau, ai duyet, ban ky ghi gi, va bon quyet dinh
  phat sinh luc cai dat. DOC TRUOC khi sua QC, ticket hay cho ky.

### Test

```bash
cd apps/api && pytest tests -q   # 41 test: phan quyen, ticket, cong, phieu duyet, export, AI Agent
pytest jobs/tests -q             # 18 test: logic export, bo luat, mirror len BigQuery — khong can cloud
```

`jobs/tests` chay duoc ma khong can cloud: phan de sai nhat cua Export Job la
dau ban ky, cat sheet va dinh dang dong — deu la ham thuan.

Hai test dang gia nhat, vi chung giu dung cai de mat nhat khi sua code sau nay:

- `test_nguoi_khong_dong_duoc_ticket` — khong co duong nao dong ticket bang tay.
- `test_facts_tra_ve_so_cua_nguon_chu_khong_sua` — khong co duong nao lam so
  doc ra khac so trong `fact_current`.

## Quy trinh chat luong (P6)

Quy trinh day du o [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md).
Ba thay doi lon so voi P3–P5:

**1. Ung dung khong sua so nua.** Bang `fact_override` bi bo han, cung voi
`apply` / `park` / `send_back`. Truoc kia so sua tay chi song trong Postgres
va duoc ap len luc xuat file — nghia la file gui khach va BigQuery co the
lech nhau ma khong ai phat hien, va override khong bao gio het han nen no
con de len ca so ma team Data da sua DUNG o lan nap sau. Bay gio so sai thi
mo ticket, team Data sua o nguon.

**2. Ticket mang dieu kien nghiem thu, va chi QC moi dong duoc.** Moi ticket
ghi `expected_value`; sau moi lan nap, QC doc so that len va doi chieu. Khop
thi dong, lech ma nguoi ta da bao "da sua" thi bat nguoc ve `open` kem so doc
duoc. Khong co endpoint nao dong ticket bang tay — do la diem quyet dinh cua
ca quy trinh, vi "da sua roi" la loi hua con cot nay la bang chung.

**3. Vi pham luat khong khoa cong; phieu duyet thay cho viec do.** Vi pham la
nghi ngo cua may: no bo sot duoc (10 tre nhap thanh 20 thi khong luat nao bat)
va bao nham duoc. Nen team lead ky duoc du con vi pham, mien la viet phieu
duyet — va phieu do di theo ban ky vinh vien, in ca vao file gui khach. Cai
khoa cung chi con ticket dang chan, va truong hop QC chua kiem lan nap hien
tai.

Ban ky tu day ghi them: van tay du lieu (`checksum`), so o vi pham theo tung
luat, van tay tap vi pham, version cua `rules.yaml`, va danh sach ticket chua
dong. Van tay du lieu la de bat truong hop team Data sua so TAI CHO duoi cung
mot `run_id` — luc do nhan van the ma so da khac.

```bash
# Migration
cd apps/api && alembic upgrade head    # c3a71e5b9042

# Sinh lai vi pham + doi chieu ticket
FORCE_QC=1 RULES_PATH=$PWD/rules/rules.yaml python jobs/qc/main.py
```

## AI Agent — doc them tren QC (P7, demo)

Theo [Demo_Build_Spec.md](Demo_Build_Spec.md): Deterministic QC Engine (bo
luat `rules/rules.yaml` + `jobs/qc`) bat loi cung tu dong; AI Agent la mot
lop **doc them**, khong thay the — no doc lai vi pham (`qc_exception`) va
ticket dang mo (bang chung nam san o cot `ticket.evidence`) trong pham vi
cua nguoi hoi, roi tra loi bang ngon ngu tu nhien. Agent khong dong ticket,
khong ky ban, khong sua so — ba viec do van chi lam duoc qua co che da co
o P3/P6 (QC Runner doi chieu, `POST /api/release`, mo ticket).

Kien truc "RAG-lite": moi luot hoi la mot lan doc lai Postgres (khong luu
gi giua cac lan goi, khong vector DB), nhet thang ket qua vao prompt goi
Gemini qua Vertex AI — dung ADC cua service account `dataops-api`, khong
can API key.

| | |
|---|---|
| Backend | `POST /api/agent/chat` — [app/agent.py](apps/api/app/agent.py) (system prompt, ngu canh, goi Vertex AI), wire vao [main.py](apps/api/app/main.py) |
| Giao dien | Trang `/agent` — [app/agent/page.tsx](apps/web/app/agent/page.tsx), chat don gian qua cong gateway hien co |
| Model | `gemini-2.5-flash` (doi bang bien `AGENT_MODEL` neu can) |
| Quyen GCP | Service account `dataops-api` them `roles/aiplatform.user` — [infra/modules/iam/main.tf](infra/modules/iam/main.tf) |
| Test | `test_agent_chat_khong_lo_pham_vi` trong [test_agent.py](apps/api/tests/test_agent.py) — mock `agent.ask`, chi kiem phan tu dieu khien duoc: ngu canh phai loc dung pham vi |

**Truoc khi dung**: bat API `aiplatform.googleapis.com` cho project (repo
nay khong co resource Terraform tu bat API — cac API duoc bat tay tu P1,
xem [Ha tang da dung (P1)](#ha-tang-da-dung-p1)):

```bash
gcloud services enable aiplatform.googleapis.com --project=dataops-poc-2026
cd infra && terraform apply   # cap them role aiplatform.user cho dataops-api
```

## Day qc_exception len BigQuery (P7, mirror mot chieu)

Khach hang muon xem vi pham QC tren BigQuery de lam bao cao/BI, nhung ung
dung VAN doc/ghi qua Postgres nhu truoc — khong doi duong doc de tiet kiem
chi phi query BigQuery. Day la **mot chieu duy nhat**: sau moi lan QC quet
xong (`jobs/qc/main.py`), toan bo bang `qc_exception` duoc **thay the
nguyen khoi** (`WRITE_TRUNCATE`) vao `dataops_analytics.qc_exception` tren
BigQuery — anh chup luon khop voi Postgres, khong tu tich luy lich su
rieng (Postgres da giu du lich su vi no khong xoa vi pham cua `run_id` cu).

| | |
|---|---|
| Code | `mirror_qc_exception_to_bigquery` trong [jobs/qc/main.py](jobs/qc/main.py), goi o cuoi `main()` |
| Bat/tat | Bien `MIRROR_QC_TO_BIGQUERY=1` (mac dinh tat — job chay local/test khong can BigQuery) |
| Dataset dich | `dataops_analytics` (rieng voi `dataops_src` — dataset do la "team Data ghi, ung dung chi doc", khong the ghi vao) |
| Ha tang | `google_bigquery_dataset "analytics"` + IAM `bigquery.dataEditor` cho SA `jobs` — [infra/modules/data/main.tf](infra/modules/data/main.tf) |
| Test | 2 test thuan (khong can BigQuery that) trong [jobs/tests/test_qc.py](jobs/tests/test_qc.py) — chuyen datetime sang ISO, giu nguyen `observed` (JSON) |

Loi day len BigQuery **khong lam hong lan chay QC**: du lieu that (Postgres)
da ghi xong truoc do, job chi log ro va lan chay sau se day lai ban moi.

```bash
# Test tay: day 1 lan thu cong
MIRROR_QC_TO_BIGQUERY=1 GCP_PROJECT_ID=dataops-poc-2026 \
  FORCE_QC=1 RULES_PATH=$PWD/rules/rules.yaml python jobs/qc/main.py
```

## Doi dataset sang FDIC Summary of Deposits (P8)

Theo dung dataset `Demo_Build_Spec.md` mo ta tu dau (`year, state,
institution, deposit`), thay cho `usa_names` (`year, state, gender, name,
number`) — chi tiet nguon/cot moi xem muc [Du lieu (P2, doi nguon o
P8)](#du-lieu-p2-doi-nguon-o-p8).

**Day la doi mien du lieu, khong phai doi ten cot** — `fact_current`,
`qc_exception`, `ticket` bi DROP va tao lai; du lieu cu (ten khai sinh)
khong con y nghia trong mien moi nen khong migrate. Khoa tu nhien rut tu
**bon phan xuong ba**: `(year, state, institution_id)` — FDIC khong co
truc tuong duong "gioi tinh" nen bi bo han, khong thay the.

| | |
|---|---|
| Migration | `apps/api/alembic/versions/e91a2c5f7b14_p8_doi_dataset_sang_fdic_sod.py` — drop + tao lai 3 bang |
| Model | `FactCurrent` / `QcException` / `Ticket` trong [apps/api/app/models.py](apps/api/app/models.py) |
| Bo luat | `rules/rules.yaml` version 5 — viet lai ca 5 luat; `duoi_nguong_kiem_duyet` (nguong cong bo cua SSA, khong ap dung cho FDIC) doi thanh `deposit_am_hoac_khong` (deposit <= 0); them moi `deposit_share_sai_cong_thuc` — kiem TUNG dong deposit_share dung cong thuc, khong chi kiem tong ca nhom |
| Seed | `jobs/seed/main.py` — xem muc [Seed Job (P8)](#seed-job-p8) |
| Endpoint doi tham so | `/api/facts`, `/api/exceptions`, `/api/summary`: `gender`/`name` -> `institution`; `/api/tickets` nhan `institution_id` (khong con `gender`/`name`) |
| Giao dien | Thanh loc bo o "Phan khuc" (gioi tinh), o "Ten" doi thanh "To chuc"; luoi du lieu doi cot `Gioi/Ten` -> `To chuc`, `So tre` -> `Deposit` |

`institution_id` (CERT cua FDIC) la ID on dinh; `institution` (ten hien
thi) KHONG nam trong khoa vi FDIC ghi ten khong nhat quan cach viet
hoa/thuong giua cac nam (du lieu that: "Keybank" nam 2022 vs "KeyBank" tu
2023, cung mot CERT) — dung ten lam khoa se tach nham mot to chuc thanh
hai.

Da chay tron tren du lieu that (khong mock): seed 5 nam FDIC (2022-2026,
385.625 dong chi nhanh -> gop con 31.502 dong to chuc) vao `dataops_src`,
sync ve Postgres, QC bat **634 vi pham that** (509 `deposit_am_hoac_khong`,
29 `tang_dot_bien`, 96 `bien_dong_bat_thuong`), AI Agent tra loi dung theo
schema moi, 40 test API + 18 test jobs deu qua.

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
- ~~Quy trinh chat luong khong khep vong~~ — P6 da go: bo `fact_override`,
  them ticket co dieu kien nghiem thu, ban ky ghi ro mon no. Con lai hai
  mon nho, ghi o cuoi [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md):
  bo luat khong tu lon len sau moi ticket kieu "QC khong bat duoc", va ticket
  van phai bao cho team Data bang tay.
