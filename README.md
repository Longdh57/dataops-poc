# Data Operations WebApp

Ứng dụng nội bộ cho đội nghiên cứu dữ liệu. BigQuery là nguồn sự thật,
Cloud SQL là nơi ghi và chịu trách nhiệm. Xem `implement-plan.html` cho
bản thiết kế đầy đủ.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `apps/web` | Next.js 16 + TypeScript — giao diện, AG Grid + TanStack Query |
| `apps/api` | FastAPI — phục vụ dữ liệu, phân quyền |
| `jobs/sync` | BigQuery -> Cloud SQL, chạy mỗi 60s (P2) |
| `jobs/export` | Sinh Excel/CSV từ bản đã ký, qua GCS + signed URL |
| `jobs/seed` | Người dùng thử nghiệm + bảng fact demo trên BigQuery |
| `docs` | Runbook vận hành, kịch bản demo |
| `infra` | Terraform, state trên GCS |
| `rules` | Bộ luật QC khai báo bằng YAML |

## Chạy local

```bash
docker compose up --build
```

http://localhost:3000 — dashboard, lưới dữ liệu, vi phạm QC, ticket.
Đổi package.json thì phải dùng `docker compose up -d --build --renew-anon-volumes web`,
vì node_modules nằm trong anonymous volume.
Rebuild
```bash
docker compose up -d --build
```

## Hạ tầng đã dựng (P1)

| Hạng mục | Giá trị |
|---|---|
| Project | `dataops-poc-2026` · number `503189459024` |
| Region | `asia-southeast1` |
| VPC | `dataops-vpc` · subnet `10.10.0.0/24` |
| Cloud SQL | `dataops-pg-42c6` · POSTGRES_17 · db-f1-micro · **chỉ private IP** `10.70.0.3` |
| Cloud Run | `dataops-web`, `dataops-api` — scale-to-zero, Direct VPC egress |
| Registry | `asia-southeast1-docker.pkg.dev/dataops-poc-2026/dataops` |
| Secret | `dataops-database-url` — gắn vào Cloud Run lúc chạy |
| TF state | `gs://dataops-poc-2026-tfstate/poc` |

Hai service KHÔNG public: không có binding `allUsers`, request không
xác thực trả 403. Truy cập để kiểm tra:

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" https://dataops-web-503189459024.asia-southeast1.run.app
```

## Hai việc còn lại của P1 — cần làm bằng browser

Cả hai đều vướng cùng một gốc: **project không thuộc Organization nào**
(tài khoản gmail cá nhân).

### 1. Bật IAP

IAP trên Cloud Run cần OAuth client. API `gcloud iap oauth-brands` trả về
`Project must belong to an organization`, và API đó đã bị Google đóng vĩnh
viễn từ 19/03/2026. Phải tạo tay:

1. Console -> APIs & Services -> OAuth consent screen -> chọn **External**
2. Tạo OAuth 2.0 Client ID (Web application), redirect URI:
   `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect`
3. Console -> Security -> Identity-Aware Proxy -> bật cho từng Cloud Run service
4. Sau đó trong `infra/terraform.tfvars` đặt `iap_enabled = true` rồi apply

Cách sạch hơn: đăng ký **Cloud Identity Free** cho `3ddesigns.xyz`. Project
sẽ có Organization, IAP tự cấp OAuth client, và tạo được Google Group thật
để quản lý người dùng như plan mô tả.

### 2. Domain mapping

`gcloud domains list-user-verified` đang trống. Phải verify quyền sở hữu
`3ddesigns.xyz` trước:

```bash
gcloud domains verify 3ddesigns.xyz
```

Lệnh này mở Search Console. Verify xong:

```bash
gcloud beta run domain-mappings create --service=dataops-web --domain=dataops-dev.3ddesigns.xyz --region=asia-southeast1
gcloud beta run domain-mappings create --service=dataops-api --domain=api-dataops-dev.3ddesigns.xyz --region=asia-southeast1
```

Bản ghi CNAME ở Cloudflare phải để **DNS only**, không bật proxy — bật
proxy thì Google không cấp được chứng chỉ.

### 3. CI/CD

`.github/workflows/deploy.yml` đã sẵn sàng. Để bật:

1. Đặt `github_repo = "owner/repo"` trong `infra/terraform.tfvars`, apply
2. Lấy output `workload_identity_provider` và `deployer_email`
3. GitHub -> Settings -> Secrets and variables -> Actions -> Variables:
   `GCP_PROJECT_ID`, `GCP_REGION`, `WIF_PROVIDER`, `DEPLOYER_SA`
4. Settings -> Environments -> tạo `production`, đặt required reviewer
   để có bước duyệt tay

## Dữ liệu (P2, đổi nguồn ở P8)

Nguồn: [FDIC Summary of Deposits](https://banks.data.fdic.gov/bankfind-suite/SOD)
(`api.fdic.gov/banks/sod`) — deposit của từng tổ chức ngân hàng FDIC bảo
hiểm, khảo sát hàng năm vào 30/6. Dữ liệu thật, công khai, không cần API
key. Trước P8 dùng `bigquery-public-data.usa_names` (tên khai sinh ở Mỹ)
làm dữ liệu mẫu vì cùng dạng `year, state, <2 trục khác>, số đo` — xem
[docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md) cho bối cảnh
đổi dataset.

**Khác với nguồn cũ**: FDIC KHÔNG có sẵn trên `bigquery-public-data` (chỉ
có snapshot tổ chức/chi nhánh, không có lịch sử theo năm), nên
`jobs/seed/main.py` tự gọi API rồi nạp vào BigQuery — xem mục
[Seed Job](#seed-job-p8) ở dưới.

### Xem trên BigQuery

```bash
bq query --use_legacy_sql=false --location=asia-southeast1 \
 'SELECT run_id, COUNT(*) FROM `dataops-poc-2026.dataops_src.fact_names` GROUP BY run_id'
```

Hoặc Console: BigQuery -> dataops-poc-2026 -> dataops_src -> fact_names

| | |
|---|---|
| Bảng fact | `dataops-poc-2026.dataops_src.fact_names` |
| Partition | `DATE(loaded_at)` — mỗi lần nạp một partition |
| Cluster | `state, institution_id, year` |
| Cột | run_id, loaded_at, year, state, institution_id, institution, deposit, deposit_share, prev_deposit, prev_year |

`institution_id` (CERT của FDIC) là khóa THẬT của một tổ chức —
`institution` (tên hiển thị) không dùng làm khóa được vì FDIC ghi tên
không nhất quán cách viết hoa/thường giữa các năm (ví dụ "Keybank" năm
2022 vs "KeyBank" từ 2023, cùng một CERT).

`deposit_share` = tỷ trọng deposit của một tổ chức trong tổng deposit của
cả bang, năm đó. Cộng lại đúng bằng 1.0 ở mỗi nhóm `(year, state)` — đây
là cơ sở cho luật QC `deposit_share_sum_not_100`.

### Xem trên Postgres

Cloud SQL chỉ có private IP nên không nối trực tiếp từ máy cá nhân được.
Xem qua giao diện hoặc API:

- Giao diện: https://dataops-dev.3ddesigns.xyz
- `GET /api/schema` — toàn bộ bảng kèm số dòng và dung lượng
- `GET /api/facts?state=CA&year=2026` — dữ liệu thật
- `GET /api/version` — độ tuổi bản sao

Dưới local thì nối thẳng được:

```bash
docker exec dashboard-bigquery-db-1 psql -U dataops -d dataops -c '\d fact_current'
```

### Seed Job (P8)

`jobs/seed/main.py` (chỉ chạy tay, `SEED_BIGQUERY=1`, xem docstring "đây là
bước dựng môi trường demo, không phải đường chạy hàng ngày"):

1. Gọi `api.fdic.gov/banks/sod` phân trang (`limit=10000` + `offset`), lấy
   `SEED_YEAR_COUNT` năm gần nhất (mặc định 5) tính từ năm mới nhất FDIC có
   — không hard-code năm cụ thể.
2. Nạp (LOAD) dữ liệu thô mức CHI NHÁNH vào bảng tạm
   `dataops_src.sod_raw_stage` trên BigQuery.
3. Một câu SQL gộp từ chi nhánh lên tổ chức (`GROUP BY year, state,
   institution_id`), tính `deposit_share` và `prev_deposit`/`prev_year`
   bằng window function — cùng một kỹ thuật `LAG(...) OVER (...)` như
   trước, chỉ đổi trục partition.

```bash
GCP_PROJECT_ID=dataops-poc-2026 SEED_BIGQUERY=1 SEED_YEAR_COUNT=5 \
  python jobs/seed/main.py
```

Đã chạy thật: 5 năm (2022–2026) → 385.625 dòng chi nhánh → gộp còn
**31.502 dòng** tổ chức.

Them `SEED_FAKE_VIOLATIONS=1` neu can demo QC co du vi du cho ca 6 luat
trong `rules.yaml`: du lieu FDIC that gan nhu khong bao gio tu vi pham
`deposit_share_sum_not_100`, `deposit_share_formula_mismatch` (cong thuc
tinh dung tu dau) hay `institution_reappeared_after_gap` (5 nam seed qua
ngan de co khoang trong that > 3 nam) — co nay pha 4 dong that thanh du
lieu gia de dam bao 3 luat do co it nhat 1 exception. 3 luat con lai da
tu nhien co vi pham tren du lieu that nen khong dung.

```bash
GCP_PROJECT_ID=dataops-poc-2026 SEED_BIGQUERY=1 SEED_YEAR_COUNT=5 \
  SEED_FAKE_VIOLATIONS=1 python jobs/seed/main.py
```

### Sync Job

```
07:29:05  team Data INSERT vào BigQuery
07:29:24  Scheduler kích hoạt, job phát hiện thay đổi   (+19s)
07:29:56  Postgres phản ánh xong                        (+51s tổng)
```

Phát hiện thay đổi bằng `__TABLES__` — truy vấn metadata, **quét 0 byte**,
nên poll mỗi 60 giây cả ngày không tốn đồng nào.

Nạp: EXPORT DATA -> parquet trên GCS -> COPY vào `fact_staging` ->
đổi tên trong một transaction. Đã kiểm chứng 1.062 request đọc đồng thời
trong lúc đổi tên: **0 thất bại**.

Migration chạy bằng Cloud Run Job vì Cloud SQL chỉ có private IP:

```bash
gcloud run jobs execute dataops-migrate --region=asia-southeast1
```

### Bài học về hiệu năng

Các con số dưới đây đo lúc còn dùng `usa_names` (~1,2 triệu dòng) — dataset
FDIC hiện tại gọn hơn (31,5 nghìn dòng) nên sync nhanh hơn nhiều, nhưng bài
học về `maintenance_work_mem` vẫn đúng, chỉ là không còn là nút thắt.

Lần đầu sync mất **229s** — vượt tiêu chí 2 phút. Đọc log thì 199s trong
số đó là dựng index, không phải COPY. Nguyên nhân: `db-f1-micro` chỉ có
~0,6GB RAM nên `maintenance_work_mem` mặc định rất nhỏ, sắp xếp khi build
index tràn ra đĩa PD_HDD.

Hai lệnh `SET` trong Sync Job đưa xuống **33,2s** — nhanh hơn 7 lần,
không đổi phần cứng, không tốn thêm tiền:

```sql
SET maintenance_work_mem = '160MB';
SET synchronous_commit = off;
```

`synchronous_commit = off` an toàn ở đây vì bảng staging là dữ liệu dùng
một lần — hỏng thì sync lại từ BigQuery.

## Phân quyền & cổng phát hành (P3)

### Nguyên tắc không được phá

Phạm vi dữ liệu LUÔN lấy từ database theo email, KHÔNG BAO GIỜ lấy từ
tham số client. Client gửi `?state=CA` chỉ là một ý kiến; điều kiện thật
là GIAO giữa tham số đó và phạm vi được gán trong `app_role`.

Kiểm chứng trên hạ tầng thật:

| Người dùng | Phạm vi | Gọi gì | Nhận được |
|---|---|---|---|
| analyst.tx | TX | `/api/facts` | chỉ TX |
| analyst.tx | TX | `/api/facts?state=CA` | **0 dòng** |
| analyst.ca | CA | `/api/facts` | chỉ CA |
| sale | CA+TX | `/api/exceptions` | 84 = 37 CA + 47 TX |

Trả về rỗng chứ không phải 403, để không rò rỉ thông tin bảng nào tồn tại.

### ~~Khóa lạc quan~~ — gỡ ở P6

P3 có khóa lạc quan trên `fact_override`: hai phiên sửa cùng một ô thì phiên
sau nhận 409 kèm diff. P6 bỏ hẳn việc sửa số, nên không còn hai phiên nào
tranh nhau một ô để mà khóa.

Chỗ tranh chấp chuyển sang bảng `ticket`, và được giải bằng một ràng buộc
ở tầng database thay vì một cột `version`: partial unique index
`uq_ticket_open_key` chỉ cho ĐÚNG MỘT ticket đang sống trên mỗi ô. Người thứ
hai nhận 409 kèm id của ticket đã có — không có cách nào để hai điều kiện
nghiệm thu mâu thuẫn cùng tồn tại.

### Cổng phát hành

Từ P6, vi phạm luật KHÔNG còn khóa cổng — xem mục [Quy trình chất lượng
(P6)](#quy-trình-chất-lượng-p6). Chỉ hai thứ khóa cứng:

| Thao tác | Kết quả |
|---|---|
| Ký khi còn ticket đang chặn | 409 + danh sách ticket |
| Ký khi QC chưa kiểm lần nạp hiện tại | 409 — danh sách vi phạm đang hiện là của lần trước |
| Ký khi còn nợ mà không có phiếu duyệt | 422 |
| Analyst thử ký | 403 — sai vai trò |
| Tải file khi còn ticket chặn | 409 |

### Endpoint

| Method | Đường dẫn | Ý nghĩa |
|---|---|---|
| GET | `/api/me` | danh tính, vai trò, phạm vi |
| GET | `/api/facts` | lọc, sắp xếp (allowlist), phân trang keyset; số LUÔN là số nguồn. Mỗi dòng kèm `violations` + `violation_severity` — đủ để vẽ chấm, không hơn (P13) |
| GET | `/api/facts/violations?year=&state=&institution_id=` | vi phạm của đúng một ô, nạp khi bấm vào chấm (P13) |
| GET | `/api/exceptions` | vi phạm của lần nạp hiện tại, trong phạm vi |
| POST | `/api/tickets` | báo lỗi cho team Data — bắt buộc có `expected_value` |
| GET | `/api/tickets` | ticket trong phạm vi |
| PATCH | `/api/tickets/{id}` | mark_fixed / set_blocking / cancel. KHÔNG có close |
| GET | `/api/gate` | món nợ + hai thứ khóa cứng |
| GET | `/api/rules` | bộ luật trong bảng `qc_rule` + YAML render từ đó; `?version=N` đọc snapshot (P10) |
| POST | `/api/rules` | thêm luật (team_lead / admin), kèm `expected_version` (P10) |
| PUT | `/api/rules/{id}` | sửa luật, kể cả bật/tắt. `id` bất biến (P10) |
| DELETE | `/api/rules/{id}?expected_version=` | xoá luật; vẫn còn trong snapshot cũ (P10) |
| POST | `/api/rules/preview` | chạy thử SQL của luật: cột, số dòng, 20 dòng mẫu (P10) |
| POST | `/api/rules/run-qc` | kích hoạt QC Runner ngay, `FORCE_QC=1` (P10) |
| GET | `/api/users` | danh sách tài khoản + vai trò + phạm vi, **chỉ admin** (P12) |
| GET | `/api/users/switchable` | danh sách cho bộ chọn danh tính; chỉ tồn tại khi `REQUIRE_IAP=false` (P12) |
| POST | `/api/users` | tạo tài khoản, chỉ admin (P12) |
| PUT | `/api/users/{id}` | sửa tên, vai trò, phạm vi, bật/tắt. Email bất biến (P12) |
| DELETE | `/api/users/{id}` | xoá hẳn; vết còn trong `audit_log` (P12) |
| POST | `/api/release` | ký bản số liệu (team_lead), kèm phiếu duyệt |
| POST | `/api/exports` | 202 + job_id |

### Bộ luật QC

Từ P10 bộ luật sống trong Postgres (`qc_rule`) và sửa ngay trong ứng dụng — xem
[CRUD bộ luật QC (P10)](#crud-bộ-luật-qc-p10). `rules/rules.yaml` chỉ còn là seed
cho migration. Ngưỡng đặt từ profile dữ liệu thật:

| Luật | Mức | Bắt được (chạy thật trên 5 năm FDIC, 31.502 dòng) |
|---|---|---|
| deposit_share_sum_not_100 | critical | 0 — kiểm tra TỔNG cả nhóm (year,state) ≈ 1.0 |
| deposit_share_formula_mismatch | critical | 0 — kiểm TỪNG dòng: `deposit_share` phải khớp `deposit / tổng deposit cả bang`, chỉ ra đúng ô nào sai (khác với luật trên, chỉ biết cả nhóm lệch) |
| deposit_negative_or_zero | critical | 509 — deposit <= 0 |
| deposit_spike | critical | 29 — deposit tăng >15 lần so năm trước |
| institution_reappeared_after_gap | critical | 0 |
| unusual_deposit_change | warning | 96 |

Từ P6, `severity` chỉ còn để xếp thứ tự đọc và để lọc — nó không quyết định
được gì nữa. Chỉ ticket mới chặn phát hành.

Bộ luật đọc được TỪ TRONG ỨNG DỤNG: nút **Xem bộ luật** trên Dashboard
(thẻ "Vi phạm theo luật") và trên trang Vi phạm mở ra cả danh sách luật —
id, mức, phạm vi, câu người dùng đọc, SQL — lẫn YAML gốc nguyên văn. Ai
đọc báo cáo cũng đối chiếu được `rule_id` với luật thật mà không cần mở
repo. API đọc file qua `app/rules.py`, nên image API build từ GỐC repo để
kèm thư mục `rules/` (xem `apps/api/Dockerfile`).

Hộp này hiện hai version cạnh nhau và có lý do: version trong FILE (sẽ
chạy ở lần QC kế tiếp) và version QC ĐÃ CHẠY trên lần nạp hiện tại. Lệch
nhau thì có cảnh báo — không thì người đọc sẽ đối chiếu vi phạm với một
bộ luật chưa từng chạy.

```bash
gcloud run jobs execute dataops-qc --region=asia-southeast1
```

### Danh tính khi chưa có IAP

IAP chưa bật được nên `REQUIRE_IAP=false`, danh tính lấy từ header
`X-Dev-User`. Giao diện có bộ chọn danh tính để thấy phân quyền hoạt động:

https://dataops-dev.3ddesigns.xyz/?as=analyst.tx@dataops.test

Từ P12, danh sách trong bộ chọn đọc từ `/api/users` chứ không còn gõ cứng
trong mã nguồn — tài khoản vừa tạo ở màn hình **Người dùng** thử được ngay.

Bật IAP lên thì `REQUIRE_IAP` tự chuyển sang true (buộc theo `iap_enabled`
trong Terraform), danh tính đến từ JWT Google ký và không giả được.
Mã verify IAP JWT đã viết sẵn trong `app/auth.py` — kiểm cả chữ ký,
issuer lẫn audience, và KHÔNG tin header `x-goog-authenticated-user-email`
vì header đó giả được nếu gọi thẳng vào URL run.app.

### Test

```bash
cd apps/api && pytest tests -q     # 25 test
```

## Giao diện (P4)

Năm màn hình, một thanh lọc dùng chung, mọi thứ đọc từ API qua một cổng
duy nhất.

| Trang | Làm gì |
|---|---|
| `/` | Dashboard: ô chỉ số, chênh lệch so với bản đã ký, vi phạm theo luật và theo khu vực, trạng thái cổng |
| `/data` | Lưới 1,2 triệu dòng bằng AG Grid, cuộn liên tục; dòng vi phạm QC mang chấm màu (P13) |
| `/exceptions` | Vi phạm của lần nạp hiện tại + panel điều tra bên phải |
| `/tickets` | Ticket gửi team Data — P6 |
| `/versions` | Bản đã ký: ai ký, lúc nào, đã gửi cho khách nào |
| `/requests` | Sale xin file, theo dõi trạng thái, tải về khi xong |

### Song ngữ vi / en

Nút `VI | EN` ở góc phải thanh trên. Không thêm thư viện i18n nào — một
React context nhỏ trong `apps/web/app/i18n` là đủ cho hai ngôn ngữ.

| File | Làm gì |
|---|---|
| `app/i18n/vi.ts` | Từ điển gốc, đồng thời là nguồn khai báo `MessageKey` |
| `app/i18n/en.ts` | Bản tiếng Anh, kiểu `Record<MessageKey, string>` |
| `app/i18n/translate.ts` | `translate()` / `template()` / `split()` — không dính React |
| `app/i18n/context.tsx` | `I18nProvider`, `useI18n()` (`t`, `tn`), `useFmt()` |
| `app/i18n/server.ts` | `getLocale()` — đọc cookie ở phía server |

Ba điểm đáng nhớ:

- **Thêm chuỗi mới thì thêm vào `vi.ts` trước.** `en.ts` khai báo kiểu
  `Record<MessageKey, string>` nên thiếu khóa là `npm run typecheck` đỏ,
  không phải đợi tới lúc người dùng thấy ô trống.
- **`t()` trả chuỗi, `tn()` trả JSX.** Câu nào có `<b>` hay `<Link>` ở
  giữa thì dùng `tn("khoa", { cho: <b>…</b> })` — chỗ trống `{ten}` trong
  template được thay bằng node, không phải nối chuỗi.
- **Ngôn ngữ nằm trong cookie `dataops_lang`, đọc ở root layout.** HTML
  từ server đã đúng thứ tiếng và `<html lang>` đúng ngay từ đầu — không
  chớp một nhịp tiếng Việt rồi mới đổi. Đổi lại: mọi route thành dynamic
  thay vì prerender tĩnh. Ứng dụng này lấy hết dữ liệu qua fetch ở client
  nên không mất gì.

Số và ngày tháng đi theo ngôn ngữ (`useFmt()` — `1.204.881` vs
`1,204,881`). Còn **nội dung từ API vẫn giữ nguyên**: tiêu đề ticket,
phiếu duyệt, `detail` của lỗi HTTP, và câu trả lời của AI Agent —
`SYSTEM_PROMPT` trong `apps/api/app/agent.py` vẫn là tiếng Việt.

### Trình duyệt không gọi thẳng API

`dataops-api` không public: chỉ service account của web gọi được bằng OIDC
token. Trình duyệt không có token đó, nên mọi request đi qua route handler
`apps/web/app/api/gw/[...path]/route.ts` — Next.js lấy token từ metadata
server rồi gọi tiếp. Có IAP thì chuyển tiếp nguyên assertion của Google;
chưa có thì lấy danh tính từ cookie `dataops_as` (đường này chỉ mở khi
`REQUIRE_IAP=false`).

### Lưới dữ liệu: vì sao Client-Side Row Model

API phân trang theo keyset (cursor), không theo offset — nên không nhảy
đến "dòng thứ 50.000" được, mà Infinite Row Model của AG Grid lại cần
đúng điều đó. Cách hợp với keyset là nối tiếp các slice 500 dòng vào một
mảng trong bộ nhớ và để AG Grid ảo hóa phần hiển thị. Cuộn gần cuối thì
`onBodyScrollEnd` tự gọi slice sau.

Cái giá phải nói rõ với người dùng, và giao diện có ghi: **bấm tiêu đề cột
chỉ sắp xếp trong số dòng đã tải**. Muốn sắp xếp toàn bộ thì đổi ô "Sắp
xếp toàn bộ" — cái đó chạy ở server và nạp lại từ đầu.

### Panel điều tra nhìn từ giao diện

Từ P6 panel chỉ để ĐỌC và để quyết định. Nó đặt bản đã ký gần nhất cạnh lần
nạp hiện tại — câu hỏi thật sự là "số này có thật sự đổi không", chứ không
phải "sửa thành bao nhiêu". Ô nhập duy nhất còn lại là *Số đúng phải là*, và
nó không ghi vào dữ liệu: nó thành điều kiện nghiệm thu của một ticket.

Ô nào đã có ticket thì panel hiện nguyên trạng thái ticket đó thay cho form,
kèm hai việc làm được: *Nguồn đã sửa — nhờ QC xác minh*, và *Báo nhầm — hủy
ticket*. Không có nút đóng.

### Hai nút dễ bấm nhầm

| Nút | Làm gì | Mất bao lâu |
|---|---|---|
| **Làm mới bảng** | gọi lại API, đọc bản sao Postgres | vài chục ms |
| **Nạp lại từ nguồn** | chạy hẳn Sync Job: đọc lại BigQuery, staging, đổi tên | 30–60s |

Nút thứ hai màu đỏ, chỉ team lead trở lên thấy, và có một bước hỏi lại.

### Banner độ tuổi

Poll `/api/version` mỗi 30 giây. Thấy `run_id` khác cái đang hiển thị thì
hiện banner kèm nút *Tải lại* — **không tự làm mới**, vì người dùng có thể
đang gõ dở dang trong panel điều tra.

### Endpoint P4 thêm vào

| Method | Đường dẫn | Ý nghĩa |
|---|---|---|
| GET | `/api/summary` | toàn bộ số liệu dashboard trong một lần gọi |
| GET | `/api/options` | giá trị cho thanh lọc — cũng áp phạm vi |
| GET | `/api/exceptions/{id}` | chi tiết cho panel điều tra, kèm ticket của ô đó |
| GET | `/api/versions` | bản đã ký + đã gửi cho ai |
| POST | `/api/versions/{id}/sent` | ghi nhận đã gửi cho khách |
| GET | `/api/exports` | job của chính mình |
| GET | `/api/exports/{id}/download` | signed URL 15 phút, chặn khi còn ticket chặn |
| POST | `/api/rebuild` | kích hoạt Sync Job (team_lead trở lên) |

### Kịch bản đã chạy trọn

Chạy trên docker compose local, dữ liệu thật 1.222.947 dòng:

1. Dashboard báo 382 vi phạm (21 nghiêm trọng), cổng **chờ ký kèm phiếu duyệt**
2. Mở một vi phạm -> panel hiện số của lần nạp cạnh bản đã ký
3. Mở ticket với `expected_value` -> cổng chuyển **KHÓA**, badge tab đỏ
4. Bấm *Đã sửa nguồn* -> ticket sang `awaiting_verify`, vẫn chặn
5. Chạy lại QC khi nguồn chưa đổi thật -> ticket **bật ngược về `open`** kèm
   số đọc được
6. Gỡ chặn ticket (team lead, có lý do) -> ký kèm phiếu duyệt -> `signed_version`
   ghi vân tay, số vi phạm theo luật, version luật, ticket chưa đóng
7. Đổi danh tính sang sale -> xin file -> job vào hàng đợi `pending`

Bước 1–6 là kịch bản P6, đã chạy trọn trên docker compose local. Bước cuối
(file tải về được) cần Export Job chạy thật.

### Còn thiếu so với plan

- ~~Bộ lọc "công ty" trong plan ánh xạ sang "tên" ở bộ dữ liệu này~~ — hết
  còn nợ từ P8: dataset FDIC có đúng chiều tổ chức (`institution`), bộ lọc
  ở giao diện là tìm theo tên tổ chức thật.
- Export Job chưa dựng lịch chạy, nên job dừng ở `pending`. Giao diện đã
  xử lý đủ bốn trạng thái `pending / running / done / error`.

## Hoàn thiện & bàn giao (P5)

### File gửi khách xuất từ đâu

Câu hỏi nghe đơn giản nhưng là chỗ dễ sai nhất. Trước P5, Export Job query
`WHERE run_id IS NOT NULL` — tức là lấy TẤT CẢ lần nạp có trong BigQuery.
Đo trên dữ liệu thật:

| | Số dòng |
|---|---|
| File xuất ra | 1.318.023 |
| Bản đã ký | 1.222.947 |
| Thừa | **95.076** |

95 nghìn dòng đó chưa qua rule engine, chưa qua cổng phát hành, không nằm
trong bản Team Lead đã ký.

Gốc rễ: `run_id` là HAI thứ khác nhau.

| Cột | Ví dụ | Ai đặt |
|---|---|---|
| `sync_state.last_run_id`, `signed_version.run_id` | `run-20260920T070541` | Sync Job, mỗi lượt đồng bộ |
| `fact_names.run_id` trên BigQuery | `run-2026-09-20-001` | team Data, mỗi lần nạp dữ liệu |

Lọc BigQuery bằng nhãn của Sync Job thì trả về 0 dòng — nên code cũ đành
lấy tất. P5 nối hai không gian này lại:

1. Sync Job ghi `sync_state.source_run_ids` — những lần nạp đang có trong
   bản sao. Đọc từ Postgres sau khi swap nên tốn 0 đồng chi phí query.
2. Ký phát hành đóng băng danh sách đó vào `signed_version.source_run_ids`.
3. Export Job lọc `WHERE run_id IN UNNEST(@runs)`.

Bản ký từ trước P5 không có danh sách này sẽ bị Export Job từ chối, kèm
thông báo nói rõ phải ký lại — thay vì lặng lẽ xuất sai.

### Ba ràng buộc còn lại của Export Job

- **Phạm vi**: sale phạm vi CA+TX xin file thì nhận đúng 170.682 dòng của
  CA và TX. Phạm vi được chốt lúc XIN FILE, không phải lúc job chạy — đổi
  phạm vi của họ hôm sau không làm đổi file đã phát.
- **Thị phần giữ nguyên của nguồn**: từ P6 không ai sửa số nữa, nên không
  còn phải tính lại thị phần — con số của BigQuery đã đúng sẵn. Đây là một
  nhánh code phức tạp biến mất theo bảng `fact_override`.
- **Giới hạn Excel**: 1.048.576 dòng một sheet. Vượt thì tách sheet và ghi
  cảnh báo vào `export_job.warning`, KHÔNG lặng lẽ cắt bớt dòng.

### Kích hoạt job

`POST /api/exports` gọi thẳng Cloud Run Job kèm `EXPORT_JOB_ID`, không dùng
Scheduler poll. Poll mỗi 1-2 phút sẽ bắt người dùng chờ vô cớ dù hàng đợi
rỗng.

Gọi thất bại — chạy local, job chưa deploy, thiếu quyền — thì yêu cầu VẪN
nằm trong hàng đợi và API nói rõ lý do. Trạng thái tệ nhất là đã ghi vào
database mà người dùng tưởng là chưa.

### Bộ luật: thêm `scope` và kiểm tra cấu hình

Luật giờ có năm phần: `id`, `severity`, `scope` (tùy chọn), `message`, `sql`.
Job từ chối chạy nếu file sai cấu trúc và báo **hết lỗi một lượt** — file
này bị sửa bởi người không đọc code, báo từng lỗi một thì họ phải đoán.

### Giám sát

| Cảnh báo | Bắt cái gì |
|---|---|
| Sync Job im lặng quá 30 phút | Bản sao cũ dần mà không ai biết |
| Cloud Run Job thất bại | Job có chạy, có báo lỗi, nhưng không ai đọc log |
| Web không phản hồi | Uptime check từ ba châu lục |

Dashboard `Dataops — do tre dong bo va suc khoe job`: khoảng trống trên
biểu đồ "lần sync thành công" chính là độ trễ đồng bộ.

### Terraform hóa toàn bộ

| Trước P5 | Sau P5 |
|---|---|
| 3 service account tạo bằng gcloud | `module.iam` quản lý, có import script |
| Dataset BigQuery tạo tay | `module.data` |
| Không có Export Job, Seed Job | Cả hai trong `module.runtime` |
| `secretAccessor` cấp ở cả project lẫn secret | Terraform chỉ cấp ở cấp secret |

Dự án đang chạy phải import một lần trước khi apply:

```bash
./scripts/import-existing.sh dataops-poc-2026
cd infra && terraform apply
```

Import không động tới tài nguyên thật — nó chỉ ghi vào state rằng tài
nguyên đó từ nay thuộc về Terraform.

### CI/CD: hai bước bị thiếu

Pipeline cũ build API và Web, rồi deploy. Thiếu hai thứ khiến deploy xong
là hỏng:

- **Migration không chạy.** Code mới gặp schema cũ là 500 ngay trên màn
  hình người dùng. Giờ `deploy-staging` cập nhật image cho job
  `dataops-migrate` rồi chạy `alembic upgrade head` và **đợi xong** trước
  khi deploy API. Thứ tự này an toàn vì migration chỉ thêm cột — code cũ
  vẫn chạy được với schema mới.
- **Image của job không được cập nhật.** Sync, QC, Export, Seed không phải
  service nên không có "deploy". Thiếu bước `gcloud run jobs update` thì
  chúng chạy code cũ mãi mà không ai thấy gì bất thường. Image `jobs` giờ
  cũng được build trong CI.

### Tài liệu

- [docs/runbook.md](docs/runbook.md) — làm mới khác nạp lại ra sao, sync
  lỗi thì làm gì, quay lại phiên bản trước, thêm người dùng, dựng lại từ
  project trống
- [docs/demo.md](docs/demo.md) — kịch bản trình bày 5 phút
- [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md) — quy trình
  chất lượng: lỗi đi vào từ đâu, ai duyệt, bản ký ghi gì, và bốn quyết định
  phát sinh lúc cài đặt. ĐỌC TRƯỚC khi sửa QC, ticket hay chỗ ký.

### Test

```bash
cd apps/api && pytest tests -q   # 54 test: phân quyền, ticket, cổng, phiếu duyệt, export, AI Agent
pytest jobs/tests -q             # 18 test: logic export, bộ luật, mirror lên BigQuery — không cần cloud
```

`jobs/tests` chạy được mà không cần cloud: phần dễ sai nhất của Export Job là
dấu bản ký, cắt sheet và định dạng dòng — đều là hàm thuần.

Hai test đáng giá nhất, vì chúng giữ đúng cái dễ mất nhất khi sửa code sau này:

- `test_nguoi_khong_dong_duoc_ticket` — không có đường nào đóng ticket bằng tay.
- `test_facts_tra_ve_so_cua_nguon_chu_khong_sua` — không có đường nào làm số
  đọc ra khác số trong `fact_current`.

## Quy trình chất lượng (P6)

Quy trình đầy đủ ở [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md).
Ba thay đổi lớn so với P3–P5:

**1. Ứng dụng không sửa số nữa.** Bảng `fact_override` bị bỏ hẳn, cùng với
`apply` / `park` / `send_back`. Trước kia số sửa tay chỉ sống trong Postgres
và được áp lên lúc xuất file — nghĩa là file gửi khách và BigQuery có thể
lệch nhau mà không ai phát hiện, và override không bao giờ hết hạn nên nó
còn đè lên cả số mà team Data đã sửa ĐÚNG ở lần nạp sau. Bây giờ số sai thì
mở ticket, team Data sửa ở nguồn.

**2. Ticket mang điều kiện nghiệm thu, và chỉ QC mới đóng được.** Mỗi ticket
ghi `expected_value`; sau mỗi lần nạp, QC đọc số thật lên và đối chiếu. Khớp
thì đóng, lệch mà người ta đã báo "đã sửa" thì bật ngược về `open` kèm số đọc
được. Không có endpoint nào đóng ticket bằng tay — đó là điểm quyết định của
cả quy trình, vì "đã sửa rồi" là lời hứa còn cột này là bằng chứng.

**3. Vi phạm luật không khóa cổng; phiếu duyệt thay cho việc đó.** Vi phạm là
nghi ngờ của máy: nó bỏ sót được (10 trẻ nhập thành 20 thì không luật nào bắt)
và báo nhầm được. Nên team lead ký được dù còn vi phạm, miễn là viết phiếu
duyệt — và phiếu đó đi theo bản ký vĩnh viễn, in cả vào file gửi khách. Cái
khóa cứng chỉ còn ticket đang chặn, và trường hợp QC chưa kiểm lần nạp hiện
tại.

Bản ký từ đây ghi thêm: vân tay dữ liệu (`checksum`), số ô vi phạm theo từng
luật, vân tay tập vi phạm, version của `rules.yaml`, và danh sách ticket chưa
đóng. Vân tay dữ liệu là để bắt trường hợp team Data sửa số TẠI CHỖ dưới cùng
một `run_id` — lúc đó nhãn vẫn thế mà số đã khác.

```bash
# Migration
cd apps/api && alembic upgrade head    # c3a71e5b9042

# Sinh lại vi phạm + đối chiếu ticket
FORCE_QC=1 RULES_PATH=$PWD/rules/rules.yaml python jobs/qc/main.py
```

## AI Agent — đọc thêm trên QC (P7, demo; chuyển sang Google ADK ở P9)

Theo [Demo_Build_Spec.md](Demo_Build_Spec.md): Deterministic QC Engine (bộ
luật `rules/rules.yaml` + `jobs/qc`) bắt lỗi cứng tự động; AI Agent là một
lớp **đọc thêm**, không thay thế — 4 tool của nó đều là SELECT trong phạm vi
người hỏi, không tool nào ghi/sửa được gì. Agent không đóng ticket, không ký
bản, không sửa số — ba việc đó vẫn chỉ làm được qua cơ chế đã có ở P3/P6 (QC
Runner đối chiếu, `POST /api/release`, mở ticket).

**P9 đổi kiến trúc**: từ "RAG-lite" (nhồi sẵn toàn bộ ngữ cảnh vào prompt
mỗi lượt hỏi) sang [Google ADK](https://github.com/google/adk-python) —
agent **tự quyết định** gọi tool nào, chỉ đọc đúng phần dữ liệu cần cho câu
hỏi. Xác nhận thật qua bảng `events` (ADK tự ghi): mọi câu hỏi đều có
`functionCall` thật, không phải model bịa số.

| | |
|---|---|
| Backend | `POST /api/agent/chat` — package [app/agent/](apps/api/app/agent/) (`root_agent.py` = SYSTEM_PROMPT + `Agent`, `tools.py` = 4 tool ADK, `queries.py` = logic SQL thuần test được riêng, `sql_gen.py` = NL -> SQL cho `get_fact`, `service.py` = Runner + Session), wire vào [main.py](apps/api/app/main.py) |
| `get_fact` (NL -> SQL) | Nhận câu hỏi tự do (vd "tổ chức có chữ wells ở TX"), tự sinh **một điều kiện WHERE** (không phải cả câu lệnh) qua Gemini, validate 4 lớp (ngoặc/nháy cân bằng đúng THỨ TỰ, không `;`/`--`/`/*`, không gọi hàm lạ, không từ khóa câu lệnh), AND thêm điều kiện phạm vi ở tầng SQL, thử tối đa 3 lần (lỗi lần trước đưa lại vào lần sinh sau) — hết lượt vẫn sai thì trả lời không trả lời được, không bịa số. Xem [app/agent/sql_gen.py](apps/api/app/agent/sql_gen.py) |
| Giao diện | Trang `/agent` — [app/agent/page.tsx](apps/web/app/agent/page.tsx) — gửi `session_id` thay vì toàn bộ lịch sử mỗi lần hỏi |
| Session | `DatabaseSessionService` của ADK, lưu THẲNG trên Postgres đang có (`DATABASE_URL`, dialect `postgresql+psycopg://` — không cần driver mới). ADK tự tạo 5 bảng riêng (`sessions`, `events`, `app_states`, `user_states`, `adk_internal_metadata`) **ngoài Alembic** — đây là cách ADK tự quản lý, khác với mọi bảng khác trong repo này |
| Phạm vi | Ép tại TẦNG TOOL: `service.chat()` gắn `scope_states`/`unrestricted` vào session state LÚC MỞ PHIÊN (từ `authz.Principal`, không từ LLM); `tools.py` chỉ đọc lại từ đó. LLM không thể "giả vờ" gọi tool với scope khác |
| Model | `gemini-2.5-flash` qua Vertex AI (biến `GOOGLE_GENAI_USE_VERTEXAI=TRUE` đặt trong code lúc import, không cần Terraform/docker-compose thêm) — không dùng API key, ADC như trước |
| Quyền GCP | Service account `dataops-api` có `roles/aiplatform.user` (gọi Gemini) và `roles/monitoring.viewer` (đọc số token đã dùng) — [infra/modules/iam/main.tf](infra/modules/iam/main.tf) |
| Chi phí | `GET /api/agent/usage` — token + ước tính tiền Vertex AI **tháng này**, hiện ở ô góc phải trang `/agent`. Đọc từ Cloud Monitoring (metric `aiplatform.googleapis.com/publisher/online_serving/token_count`) chứ KHÔNG tự cộng `usage_metadata` của từng request. Chỉ `team_lead`/`admin` xem được — đây là chi phí hạ tầng, không phải dữ liệu nghiệp vụ. Hai giới hạn phải nói rõ với người đọc (tooltip có ghi): con số là của **cả project** nên không tách được theo người hỏi, và tiền chỉ là **ước tính theo giá niêm yết**, chưa trừ credit — số thật nằm ở Cloud Billing. Gọi không được (thiếu quyền, chạy local) thì ô tự ẩn, không làm hỏng chỗ chat. Xem [app/agent/usage.py](apps/api/app/agent/usage.py) |
| Test | [test_agent.py](apps/api/tests/test_agent.py) — phạm vi kiểm THẬT trực tiếp trên `queries.py` (không cần mock ADK), endpoint mock `agent.chat()` để không gọi Vertex AI thật trong CI |

**Trước khi dùng**: bật API `aiplatform.googleapis.com` cho project (repo
này không có resource Terraform tự bật API — các API được bật tay từ P1,
xem [Hạ tầng đã dựng (P1)](#hạ-tầng-đã-dựng-p1)):

```bash
gcloud services enable aiplatform.googleapis.com --project=dataops-poc-2026
cd infra && terraform apply   # cấp aiplatform.user + monitoring.viewer cho dataops-api
```

Ô chi phí trên trang `/agent` cần `roles/monitoring.viewer`. CI chỉ deploy
code, KHÔNG chạy Terraform — thiếu bước `terraform apply` ở trên thì ô này
lặng lẽ không hiện (endpoint trả `available: false`), chỗ chat vẫn chạy
bình thường. Cấp tay không qua Terraform:

```bash
gcloud projects add-iam-policy-binding dataops-poc-2026 \
  --member="serviceAccount:dataops-api@dataops-poc-2026.iam.gserviceaccount.com" \
  --role="roles/monitoring.viewer"
```

## Đẩy qc_exception lên BigQuery (P7, mirror một chiều)

Khách hàng muốn xem vi phạm QC trên BigQuery để làm báo cáo/BI, nhưng ứng
dụng VẪN đọc/ghi qua Postgres như trước — không đổi đường đọc để tiết kiệm
chi phí query BigQuery. Đây là **một chiều duy nhất**: sau mỗi lần QC quét
xong (`jobs/qc/main.py`), toàn bộ bảng `qc_exception` được **thay thế
nguyên khối** (`WRITE_TRUNCATE`) vào `dataops_analytics.qc_exception` trên
BigQuery — ảnh chụp luôn khớp với Postgres, không tự tích lũy lịch sử
riêng (Postgres đã giữ đủ lịch sử vì nó không xóa vi phạm của `run_id` cũ).

| | |
|---|---|
| Code | `mirror_qc_exception_to_bigquery` trong [jobs/qc/main.py](jobs/qc/main.py), gọi ở cuối `main()` |
| Bật/tắt | Biến `MIRROR_QC_TO_BIGQUERY=1` (mặc định tắt — job chạy local/test không cần BigQuery) |
| Dataset đích | `dataops_analytics` (riêng với `dataops_src` — dataset đó là "team Data ghi, ứng dụng chỉ đọc", không thể ghi vào) |
| Hạ tầng | `google_bigquery_dataset "analytics"` + IAM `bigquery.dataEditor` cho SA `jobs` — [infra/modules/data/main.tf](infra/modules/data/main.tf) |
| Test | 2 test thuần (không cần BigQuery thật) trong [jobs/tests/test_qc.py](jobs/tests/test_qc.py) — chuyển datetime sang ISO, giữ nguyên `observed` (JSON) |

Lỗi đẩy lên BigQuery **không làm hỏng lần chạy QC**: dữ liệu thật (Postgres)
đã ghi xong trước đó, job chỉ log rõ và lần chạy sau sẽ đẩy lại bản mới.

```bash
# Test tay: đẩy 1 lần thủ công
MIRROR_QC_TO_BIGQUERY=1 GCP_PROJECT_ID=dataops-poc-2026 \
  FORCE_QC=1 RULES_PATH=$PWD/rules/rules.yaml python jobs/qc/main.py
```

## Đổi dataset sang FDIC Summary of Deposits (P8)

Theo đúng dataset `Demo_Build_Spec.md` mô tả từ đầu (`year, state,
institution, deposit`), thay cho `usa_names` (`year, state, gender, name,
number`) — chi tiết nguồn/cột mới xem mục [Dữ liệu (P2, đổi nguồn ở
P8)](#dữ-liệu-p2-đổi-nguồn-ở-p8).

**Đây là đổi miền dữ liệu, không phải đổi tên cột** — `fact_current`,
`qc_exception`, `ticket` bị DROP và tạo lại; dữ liệu cũ (tên khai sinh)
không còn ý nghĩa trong miền mới nên không migrate. Khóa tự nhiên rút từ
**bốn phần xuống ba**: `(year, state, institution_id)` — FDIC không có
trục tương đương "giới tính" nên bị bỏ hẳn, không thay thế.

| | |
|---|---|
| Migration | `apps/api/alembic/versions/e91a2c5f7b14_p8_doi_dataset_sang_fdic_sod.py` — drop + tạo lại 3 bảng |
| Model | `FactCurrent` / `QcException` / `Ticket` trong [apps/api/app/models.py](apps/api/app/models.py) |
| Bộ luật | `rules/rules.yaml` version 6 — viết lại cả 5 luật; `duoi_nguong_kiem_duyet` (ngưỡng công bố của SSA, không áp dụng cho FDIC) đổi thành `deposit_negative_or_zero` (deposit <= 0); thêm mới `deposit_share_formula_mismatch` — kiểm TỪNG dòng deposit_share đúng công thức, không chỉ kiểm tổng cả nhóm. Tên luật/message/khóa trong `observed` đều bằng tiếng Anh (P9) — đây là phần bộ luật duy nhất AI Agent đọc và trả lời thẳng lại cho người dùng |
| Seed | `jobs/seed/main.py` — xem mục [Seed Job (P8)](#seed-job-p8) |
| Endpoint đổi tham số | `/api/facts`, `/api/exceptions`, `/api/summary`: `gender`/`name` -> `institution`; `/api/tickets` nhận `institution_id` (không còn `gender`/`name`) |
| Giao diện | Thanh lọc bỏ ô "Phân khúc" (giới tính), ô "Tên" đổi thành "Tổ chức"; lưới dữ liệu đổi cột `Giới/Tên` -> `Tổ chức`, `Số trẻ` -> `Deposit` |

`institution_id` (CERT của FDIC) là ID ổn định; `institution` (tên hiển
thị) KHÔNG nằm trong khóa vì FDIC ghi tên không nhất quán cách viết
hoa/thường giữa các năm (dữ liệu thật: "Keybank" năm 2022 vs "KeyBank" từ
2023, cùng một CERT) — dùng tên làm khóa sẽ tách nhầm một tổ chức thành
hai.

Đã chạy trọn trên dữ liệu thật (không mock): seed 5 năm FDIC (2022-2026,
385.625 dòng chi nhánh -> gộp còn 31.502 dòng tổ chức) vào `dataops_src`,
sync về Postgres, QC bắt **634 vi phạm thật** (509 `deposit_negative_or_zero`,
29 `deposit_spike`, 96 `unusual_deposit_change`), AI Agent trả lời đúng theo
schema mới, 40 test API + 18 test jobs đều qua.

## CRUD bộ luật QC (P10)

Plan: [implement-plan-qc-rules-crud.md](implement-plan-qc-rules-crud.md).
Trước P10, đổi một ngưỡng là sửa `rules/rules.yaml` → build lại image API và
image jobs → deploy → chạy QC. Giờ team lead sửa trong hộp **Bộ luật QC** và
bộ luật mới có hiệu lực ở lần QC kế tiếp, không deploy gì.

| | |
|---|---|
| Migration | `f4b82d6e1a37_p10_bo_luat_trong_db.py` — ba bảng `qc_rule`, `qc_ruleset` (một dòng, version toàn cục), `qc_ruleset_snapshot`; seed từ `rules/rules.yaml` (version 6) và ghi snapshot 6 trước khi ai kịp sửa. Không tìm thấy file seed thì dừng hẳn, không tạo bộ luật rỗng |
| API | 5 endpoint mới trong bảng Endpoint ở trên. Mỗi lần ghi: validate → chạy thử SQL chỉ đọc → ghi → version +1 → snapshot → `audit_log`, trong một transaction. Hai người sửa cùng lúc: người sau nhận 409 kèm tên người vừa sửa |
| Chặn luật hỏng | Cấu trúc (id slug, severity, scope là mã bang), SQL chạy được, đủ 5 cột, không có dấu `;`. SQL chạy trong transaction `READ ONLY` + timeout 10s, và **mọi lệnh đều mang tham số** để Postgres không nhận nhiều lệnh một lần |
| QC Runner | Đọc luật đang bật từ DB. Bỏ qua chỉ khi *cùng lần nạp VÀ cùng version luật* — sửa luật xong QC tự chạy lại trong ≤ 5 phút. Mỗi luật một `SAVEPOINT` + timeout 120s: luật hỏng không kéo theo luật khác, nhưng lần nạp không được đánh dấu đã kiểm |
| Cổng phát hành | Thêm lý do khoá thứ ba: QC đã kiểm lần nạp này nhưng dưới bộ luật cũ. `/api/gate`, `/api/summary`, `/api/exceptions` trả `qc_stale_reason` là `"run"` hoặc `"rules"` |
| Giao diện | Hộp Bộ luật QC: Thêm / Sửa / Xoá / Chạy QC ngay / Tải YAML, form có "Thử SQL". Trang Phiên bản: "luật vN" mở snapshot chỉ đọc |
| Hạ tầng | Image jobs bỏ `COPY rules`; QC job bỏ `RULES_PATH`; API service thêm `QC_JOB_NAME` và quyền `run.jobsExecutorWithOverrides` trên `dataops-qc` |

Deploy lần đầu: `alembic upgrade head` (job `dataops-migrate`) **trước** khi
deploy image jobs mới — QC Runner mới báo lỗi rõ và thoát nếu chưa có bảng
`qc_rule`, không chạy với bộ luật rỗng.

## Người dùng & phân quyền (P12)

Trước P12, thêm một người là mở psql gõ hai câu INSERT theo
[docs/runbook.md](docs/runbook.md). Giờ admin làm trong tab **Người dùng**.

| | |
|---|---|
| Bảng | Không thêm bảng nào: vẫn `app_user` + `app_role` có từ P3 |
| API | 4 endpoint `/api/users` trong bảng Endpoint ở trên — **cả đọc lẫn ghi đều chỉ admin**. Cấp quyền là việc của một vai trò, nên xem ai đang có quyền gì cũng vậy |
| Bộ chọn danh tính | Đi đường riêng `/api/users/switchable`, **không** dùng `/api/users`. Nó chỉ tồn tại khi `REQUIRE_IAP=false` — lúc đó danh tính vốn chưa được xác thực, ai cũng tự xưng được bằng header `X-Dev-User`, nên ở đó không có quyền nào để bảo vệ. Đổi lại nó buộc phải mở cho mọi vai trò: đổi sang analyst một lần rồi không đổi lại được thì bản demo coi như hết. Chỉ trả 4 trường và bỏ qua tài khoản đã tắt. Bật IAP lên thì 404 |
| Một người một vai trò | `app_role` chứa được nhiều dòng, nhưng màn hình chỉ ghi một. Sửa vai trò là **thay thế cả bộ**, không cộng dồn — cộng dồn là cách dễ nhất để một analyst giữ lại phạm vi cũ sau khi bị hạ quyền |
| Analyst phải có ít nhất một bang | `scope_states` rỗng nghĩa là **không giới hạn** (xem `authz.scope_clause`), nên "quên chọn" sẽ cấp nhầm toàn bộ dữ liệu chứ không phải cấp thiếu. Chặn ở cả form lẫn server (422) |
| Email bất biến | Nó là khoá định danh người gọi và được lưu dạng chuỗi trong `audit_log.actor`, `ticket.created_by`, `signed_version.signed_by` — không có khoá ngoại nào để đổi tên theo |
| Không tự bắn vào chân | Admin không tự hạ quyền, tự tắt hay tự xoá chính mình được (409). Admin khác thì làm được |
| Xoá vs tắt | Xoá là xoá hẳn (`app_role` xoá theo CASCADE). Muốn giữ dấu vết thì bỏ đánh dấu "Tài khoản đang dùng" — runbook vẫn khuyên cách này |
| Dấu vết | `user_create` / `user_update` / `user_delete` vào `audit_log`, có cả `before` lẫn `after` |

Vai trò cấp được ở màn hình này là `admin`, `team_lead`, `analyst`. Vai trò
`sale` vẫn chạy ở API (`POST /api/versions/{id}/sent`) nhưng đã gỡ khỏi giao
diện từ trước; tài khoản còn giữ nó thì màn hình cảnh báo trước khi lưu đè.

Test: `apps/api/tests/test_users.py` — 18 bài, trong đó bài cuối gọi
`/api/facts` để chắc rằng phạm vi vừa cấp **có hiệu lực thật** ở tầng dữ
liệu chứ không chỉ hiện đẹp trên màn hình.

## Đánh dấu vi phạm QC trên lưới dữ liệu (P13)

Trước P13, lưới dữ liệu và màn hình Vi phạm luật là hai thế giới tách rời:
đang đọc số ở `/data` thì không có cách nào biết dòng trước mặt có sạch hay
không, phải nhớ khoá rồi sang màn hình khác tra. Giờ dòng nào đang vi phạm
luật thì mang một **chấm màu** ở cột QC đầu bảng, kèm vạch màu mép trái dòng
để quét mắt nhanh cả màn hình.

| | |
|---|---|
| Bảng | Không thêm bảng nào: `qc_exception` đã có khoá `(year, state, institution_id)` từ P8, và index `ix_qc_key` nằm sẵn trên đúng ba cột đó |
| Đếm ở đâu | `LEFT JOIN LATERAL` ở **vòng ngoài**, sau khi `LIMIT` đã cắt. Một trang 500 dòng tốn đúng 500 lần tra index, không phải một lần đếm qua 1,2 triệu dòng. Đặt join vào trong truy vấn chính là bắt Postgres đếm cho **mọi** dòng lọt bộ lọc rồi mới sắp xếp và cắt |
| Chấm nói gì | Chỉ hai thứ: **có** vi phạm không, và **nặng đến đâu** (`violations`, `violation_severity` = mức nặng nhất trong các luật dòng đó phạm). Tên luật dài gấp mấy lần bề ngang một cột, mà phần lớn dòng thì không vi phạm gì |
| Luật gì thì bấm | `/api/facts/violations` trả về đúng một ô: luật, mức, lời giải thích, `observed`, và ticket đang sống nếu có. Cột `message` lặp lại nguyên văn ở từng dòng — kéo sẵn cả trang 500 dòng là trả tiền cho thứ hầu hết không ai mở ra xem |
| Ô sạch phải là NULL | Aggregate trên tập rỗng vẫn trả về một dòng, nên thiếu chặn `CASE WHEN count(*) = 0` là **mọi** dòng sạch đều đội một chấm. Đây là chỗ dễ sai nhất, và `test_dong_sach_khong_co_cham` giữ nó |
| Vi phạm cấp nhóm không dán vào dòng | Luật như `deposit_share_sum_not_100` sinh vi phạm với `institution_id` NULL — nó nói về cả bang, không về dòng nào. Dán cảnh báo đó lên từng dòng là báo sai cho cả nghìn dòng vô can, nên chúng chỉ nằm ở màn hình Vi phạm luật |
| Chấm thuộc về lần QC nào | `/api/facts` trả thêm `qc_run_id` / `qc_stale` / `qc_stale_reason`. Vừa sync xong mà QC chưa chạy lại thì chấm là **của lần nạp trước** — banner nói thẳng điều đó thay vì để người đọc tưởng chấm đang nói về con số trước mặt |
| Phạm vi | `/api/facts/violations` kiểm `state` theo phạm vi của người gọi trước khi đọc, y như `/api/exceptions/{id}` — endpoint mới là một đường rò rỉ mới nếu quên |

Bấm chấm mở hộp chi tiết; trong hộp có link sang `/exceptions` đã lọc sẵn
đúng ô đó (bộ lọc nằm trên URL nên link tự mang theo bang, năm, tổ chức).

Test: `apps/api/tests/test_facts_violations.py` — 10 bài. File này **tự dựng
dữ liệu của chính nó** (ba dòng giả ở năm 1901, dọn sạch sau mỗi bài) nên
chạy được cả trên database trống, không cần đợi lần seed 1,2 triệu dòng.

## Terraform

```bash
cd infra && terraform init && terraform plan
```

Biến quan trọng trong `terraform.tfvars`:

| Biến | Ý nghĩa |
|---|---|
| `iap_enabled` | `false` cho tới khi có OAuth client |
| `github_repo` | để trống thì bỏ qua toàn bộ CI/CD |
| `iap_members` | ai được mở ứng dụng |

## Còn nợ kỹ thuật

### ⚠️ VẪN CHƯA ĐÓNG — web đang mở public

`infra/terraform.tfvars` đang đặt `public_access = true`. Bất cứ ai có link
đều xem được https://dataops-dev.3ddesigns.xyz — KHÔNG cần đăng nhập.

Lý do: IAP chưa bật được (project không thuộc Organization), mà không có
IAP thì trình duyệt không có cách nào đăng nhập, mọi request đều 403.
Mở tạm để xem và demo.

Lý do mở tạm đã hết hiệu lực từ P2: trang không còn là ba dòng trạng thái
nữa mà là 1,2 triệu dòng dữ liệu thật, kèm danh tính giả lập qua
`X-Dev-User`. Đây là món nợ nặng nhất còn lại của cả dự án.

```bash
# trong infra/terraform.tfvars: public_access = false
cd infra && terraform apply
```

Kiểm chứng đã đóng:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://dataops-dev.3ddesigns.xyz
# phải trả về 403
```

Chỉ WEB được mở. API vẫn đóng kín, chỉ `dataops-web` gọi được bằng OIDC token.

Cách gỡ tận gốc: đăng ký Cloud Identity Free cho `3ddesigns.xyz` -> project
có Organization -> IAP tự cấp OAuth client -> bỏ được `public_access` hẳn.

### Các món khác

- ~~Service account tạo bằng gcloud~~ — P5 đã khai báo trong `module.iam`.
  Còn lại một lần `./scripts/import-existing.sh` trước khi apply.
- `secretmanager.secretAccessor` vẫn còn ở CẢ HAI nơi: cấp project (từ P0)
  và cấp secret (P1). Terraform chỉ cấp ở cấp secret; gỡ cái cấp project
  là lệnh `gcloud` có trong runbook, mục "Gỡ quyền thừa".
- Pipeline: job `deploy-staging` và `deploy-prod` deploy vào CÙNG service,
  cùng domain. `gcloud run deploy` cho revision mới 100% traffic ngay, nên
  bước duyệt tay ở `deploy-prod` không còn ý nghĩa — code đã live từ trước.
  Sửa bằng `--no-traffic --tag=staging` khi cần tách thật.
- ~~Quy trình chất lượng không khép vòng~~ — P6 đã gỡ: bỏ `fact_override`,
  thêm ticket có điều kiện nghiệm thu, bản ký ghi rõ món nợ. Còn lại hai
  món nhỏ, ghi ở cuối [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md):
  bộ luật không tự lớn lên sau mỗi ticket kiểu "QC không bắt được", và ticket
  vẫn phải báo cho team Data bằng tay.
