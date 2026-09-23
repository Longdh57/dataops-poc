# Runbook vận hành

Tài liệu cho người trực, không phải cho người viết code. Mỗi mục trả lời
một tình huống có thật: dấu hiệu nhìn thấy, việc cần làm, và cách xác nhận
đã xong.

Bảng tra nhanh:

| Tình huống | Mục |
|---|---|
| Số trên màn hình có vẻ cũ | [Làm mới bảng khác Nạp lại từ nguồn](#làm-mới-bảng-khác-nạp-lại-từ-nguồn) |
| Vi phạm vừa xem xong lại hiện ra | [Vi phạm lại hiện ra sau khi sync](#vi-phạm-lại-hiện-ra-sau-khi-sync) |
| Cổng phát hành khoá mà không rõ vì sao | [Cổng phát hành khoá…](#cổng-phát-hành-khoá-mà-không-thấy-vi-phạm-nghiêm-trọng-nào) |
| Cảnh báo "Sync Job im lặng quá 30 phút" | [Khi đồng bộ hỏng](#khi-đồng-bộ-hỏng) |
| Sale báo file tải về sai | [Khi file xuất sai](#khi-file-xuất-sai) |
| Cần quay lại số liệu của bản trước | [Quay lại phiên bản trước](#quay-lại-phiên-bản-trước) |
| Cần đổi ngưỡng, thêm hoặc tắt một luật QC | [Sửa luật QC](#sửa-luật-qc) |
| QC Runner báo "luật HONG" | [Sửa luật QC](#sửa-luật-qc) |
| Có người mới vào đội | [Thêm người dùng](#thêm-người-dùng) |
| Dựng lại hệ thống ở project khác | [Dựng lại từ đầu](#dựng-lại-từ-đầu) |

---

## Làm mới bảng khác Nạp lại từ nguồn

Hai nút nằm cạnh nhau trên mọi màn hình và làm hai việc hoàn toàn khác nhau.

| | Làm mới bảng | Nạp lại từ nguồn |
|---|---|---|
| Làm gì | Gọi lại API, đọc bản sao trong Cloud SQL | Chạy Sync Job: đọc lại BigQuery → parquet → staging → đổi tên |
| Mất bao lâu | vài chục mili giây | 30–60 giây |
| Chạm vào BigQuery | không | có |
| Ai bấm được | mọi người | team lead, admin |
| Dùng khi | vừa có người sửa số, muốn thấy ngay | nghi bản sao lệch so với nguồn |

**Sai lầm hay gặp:** thấy số cũ nên bấm *Nạp lại từ nguồn*. Trong hầu hết
trường hợp cái cần bấm là *Làm mới bảng* — số cũ là do trình duyệt đang
giữ kết quả cũ, chứ không phải bản sao sai. Banner độ tươi ở đầu trang nói
rõ bản sao được cập nhật cách đây bao lâu; nếu con số đó nhỏ thì bản sao
không có vấn đề gì.

Sync Job tự chạy mỗi 60 giây và **tự bỏ qua nếu nguồn không đổi** (nó so
`last_modified_time` của bảng BigQuery, truy vấn metadata nên quét 0 byte).
Bấm *Nạp lại từ nguồn* chỉ để ép nó chạy ngay thay vì chờ chu kỳ sau.

---

## Vi phạm lại hiện ra sau khi sync

**Dấu hiệu:** danh sách vi phạm vừa xem xong, sau một lần nạp mới lại đầy đúng
những lỗi cũ.

**Đây là hành vi đúng, không phải hỏng.** Vi phạm là ảnh chụp của **một lần
nạp**: QC quét lại toàn bộ luật sau mỗi lần nạp và thay thế cả bộ. Không có
trạng thái "đã xử lý" nào mang sang lần sau — và đó là chủ ý, vì một dấu "đã bỏ
qua" từ tháng trước có thể nuốt mất một lỗi mới xuất hiện ở đúng ô đó.

Cái **có** mang sang là hai thứ khác:

- **Ticket** — lỗi đã xác nhận, sống xuyên qua các lần nạp cho tới khi QC đọc
  được đúng số kỳ vọng ở nguồn. Xem trang *Ticket*.
- **Phiếu duyệt** — nằm trong bản ký cũ, không mất đi. Nó nói bản đó đã được ký
  kèm những vi phạm nào.

Vậy nên việc cần làm không phải là "xử lý lại": đọc danh sách, cái nào là số
thật thì ghi vào phiếu duyệt lúc ký, cái nào sai thật thì mở ticket.

**Nạp lại từ nguồn khi nguồn không đổi thì không có gì xảy ra cả** — Sync Job
dừng ngay ở bước so vân tay, không sinh lần nạp mới.

---

## Cổng phát hành khoá mà không thấy vi phạm nghiêm trọng nào

Từ P6, vi phạm luật **không còn khoá cổng**. Chỉ hai thứ khoá được, và cả hai
đều không phải chuyện ý kiến:

| Nguyên nhân | Nhìn thấy ở đâu | Gỡ thế nào |
|---|---|---|
| Ticket đang chặn | Trang *Ticket*, banner đỏ | Sửa ở nguồn rồi chờ QC xác minh; hoặc team lead gỡ chặn từng cái (có ghi lý do) |
| QC chưa kiểm lần nạp hiện tại | Trang *Phiên bản*, banner đỏ | Chờ — QC chạy mỗi 5 phút. Ép ngay: `gcloud run jobs execute dataops-qc --region=asia-southeast1` |
| QC chưa chạy dưới bộ luật hiện tại (P10) | Dashboard / *Phiên bản*: "QC chưa chạy dưới bộ luật hiện tại" | Ai đó vừa sửa luật. Chờ tối đa 5 phút, hoặc bấm **Chạy QC ngay** trong hộp Bộ luật QC. Nếu vẫn khoá: có luật hỏng — xem [Sửa luật QC](#sửa-luật-qc) |

Còn vi phạm luật mà vẫn ký được — đó là thiết kế. Team lead viết phiếu duyệt,
và câu đó đi theo bản ký vĩnh viễn, in cả vào file gửi khách.

---

## Khi đồng bộ hỏng

**Dấu hiệu:** email cảnh báo "Sync Job im lặng quá 30 phút", hoặc banner độ
tươi hiện đỏ "đồng bộ cách đây … — quá cũ".

**Hậu quả cần hiểu đúng:** bản sao Cloud SQL cũ dần, nên *mọi thứ trên màn
hình* đều cũ. Nhưng file gửi khách đọc thẳng BigQuery nên **số gửi khách
không bị ảnh hưởng**.

Thứ tự kiểm tra:

```bash
# 1. Job có chạy không, lần gần nhất kết quả gì
gcloud run jobs executions list --job=dataops-sync --region=asia-southeast1 --limit=5

# 2. Scheduler có còn kích hoạt không
gcloud scheduler jobs describe dataops-sync-every-60s --location=asia-southeast1

# 3. Lỗi thật nằm ở đây, không chỉ trong log
```

Câu trả lời đầy đủ nhất nằm trong database chứ không phải log: bảng
`sync_state` giữ `status` và `last_error` của lần chạy gần nhất. Xem qua
giao diện bằng `GET /api/version`, hoặc:

```bash
gcloud run jobs execute dataops-migrate --region=asia-southeast1   # chạy từ trong VPC
```

Ba nguyên nhân đã gặp:

- **Số dòng lệch.** Job cố tình dừng và không đổi bảng khi số dòng nạp được
  khác số dòng nguồn báo. Bản sao cũ vẫn nguyên, không mất gì. Chạy lại là
  xong nếu team Data đang ghi dở lúc job đọc.
- **Hết thời gian.** Job timeout 900 giây. Nếu dữ liệu phình to, tăng
  `timeout` của `google_cloud_run_v2_job.sync` trong Terraform.
- **Hết bộ nhớ khi build index.** Xem mục "Bài học về hiệu năng" trong
  README — hai lệnh `SET` trong Sync Job giữ việc sắp xếp trong RAM.

Sau khi sửa, ép chạy lại:

```bash
gcloud run jobs execute dataops-sync --region=asia-southeast1
```

Xác nhận xong: `GET /api/version` trả `age_seconds` nhỏ và `status = ok`.

---

## Khi file xuất sai

**Dấu hiệu:** yêu cầu trên trang *Yêu cầu dữ liệu* dừng ở `lỗi`, hoặc sale
báo file thiếu/thừa dữ liệu.

Lý do thật luôn nằm ở cột `error` của bảng `export_job`, không chỉ trong log.
Ba lý do job tự từ chối làm việc — đều là cố ý:

| Thông báo | Nghĩa là | Cách xử lý |
|---|---|---|
| `job khong gan voi ban ky nao co danh sach lan nap` | Bản ký được tạo trước khi hệ thống biết ghi lại danh sách lần nạp | Chạy lại Sync Job rồi **ký một bản mới**, xin file lại |
| `cong phat hanh dang khoa (N ticket chan: #…)` | Có người mở ticket chặn sau lúc xin file | Sửa ở nguồn rồi chờ QC xác minh, hoặc gỡ chặn ticket, rồi xin lại |
| Cảnh báo `vuot gioi han … da tach thanh N sheet` | File Excel vượt 1.048.576 dòng một sheet | Không phải lỗi. Muốn một sheet thì xuất CSV hoặc thu hẹp phạm vi |

**Nếu file thiếu bang:** đó là đúng thiết kế. File chỉ chứa những bang trong
phạm vi của *người xin*, và phạm vi được chốt ngay lúc bấm nút — đổi phạm vi
của họ sau đó không làm đổi file đã phát.

**Nếu file thiếu dữ liệu mới:** cũng đúng thiết kế. File chỉ lấy những lần
nạp nằm trong bản đã ký (`signed_version.source_run_ids`). Dữ liệu team Data
đẩy lên sau khi ký sẽ không có trong file cho tới khi ai đó ký bản mới.

Chạy lại một yêu cầu:

```bash
gcloud run jobs execute dataops-export --region=asia-southeast1 \
  --update-env-vars=EXPORT_JOB_ID=<id>
```

Trước đó phải đặt lại trạng thái về `pending`, vì job chỉ nhặt việc đang chờ:

```sql
UPDATE export_job SET status='pending', error=NULL WHERE id = <id>;
```

---

## Quay lại phiên bản trước

Bản đã ký **không bao giờ bị xoá hay sửa** — `signed_version` là bảng chỉ
ghi thêm. "Quay lại" nghĩa là ký lại một bản mới trỏ vào cùng tập dữ liệu
cũ, chứ không phải xoá bản hiện tại.

1. Mở trang *Phiên bản*, tìm bản cần quay về, ghi lại `run_id` và danh sách
   lần nạp của nó.
2. Nếu dữ liệu hiện tại đã khác: đây là quyết định nghiệp vụ, không phải
   thao tác kỹ thuật. Team Lead ký bản mới với nhãn nói rõ, ví dụ
   *"Khôi phục số liệu bản 12/9 — bản 19/9 có lỗi ở TX"*.
3. File đã gửi khách trước đó vẫn tra được: bảng `versions_sent` giữ ai
   nhận bản nào ngày nào.

**Quay lại một ô sai** thì không còn là thao tác trên dashboard nữa: từ P6 ứng
dụng không sửa số. Mở ticket ghi rõ số đúng phải là bao nhiêu, team Data sửa ở
BigQuery, QC đọc lại ở lần nạp sau và tự đóng ticket. Mở nhầm thì *Huỷ ticket* —
`audit_log` giữ cả hai việc, không có gì biến mất.

**Quay lại một bản deploy hỏng** lại là chuyện thứ ba:

```bash
gcloud run services update-traffic dataops-api --region=asia-southeast1 \
  --to-revisions=<revision-cũ>=100
```

---

## Thêm người dùng

Hai lớp, phải làm cả hai:

**Lớp 1 — vào được ứng dụng.** Thêm tài khoản vào Google Workspace group đã
gán `roles/iap.httpsResourceAccessor`, hoặc thêm vào `iap_members` trong
`infra/terraform.tfvars` rồi `terraform apply`.

**Lớp 2 — vào rồi làm được gì.** Quyền nghiệp vụ nằm trong Postgres, không
nằm trong IAM, vì nó đổi thường xuyên hơn nhiều:

```sql
INSERT INTO app_user (email, display_name) VALUES ('ten@cty.com', 'Tên hiển thị');

INSERT INTO app_role (user_id, role, scope_states)
SELECT id, 'analyst', '["TX"]'::json FROM app_user WHERE email = 'ten@cty.com';
```

| Vai trò | Làm được gì |
|---|---|
| `analyst` | Xem và sửa số trong phạm vi được gán |
| `team_lead` | Thêm: ký phát hành, nạp lại từ nguồn |
| `sale` | Xem trong phạm vi, xin file, ghi nhận đã gửi khách |
| `admin` | Toàn quyền, không giới hạn phạm vi |

`scope_states` để `NULL` nghĩa là **không giới hạn bang** — cân nhắc kỹ, đây
là thứ dễ cấp nhầm nhất.

**Bỏ một người:** đặt `is_active = false` trong `app_user` thay vì xoá. Xoá
sẽ làm mất dấu vết trong `audit_log` khi truy ngược sau này.

Cloud SQL chỉ có private IP nên chạy SQL phải từ trong VPC:

```bash
gcloud run jobs execute dataops-migrate --region=asia-southeast1
```

---

## Gỡ quyền thừa

`dataops-api` và `dataops-jobs` đang được cấp `secretmanager.secretAccessor`
ở **cả hai nơi**: cấp project (tạo tay từ P0) và đúng trên một secret (module
`database`). Giữ cả hai làm câu hỏi "ai đọc được bí mật nào" trả lời sai.

Kiểm tra binding ở cấp secret còn nguyên trước khi gỡ:

```bash
gcloud secrets get-iam-policy dataops-database-url --project=dataops-poc-2026
```

Thấy cả hai service account trong đó rồi mới gỡ ở cấp project:

```bash
gcloud projects remove-iam-policy-binding dataops-poc-2026 \
  --member=serviceAccount:dataops-api@dataops-poc-2026.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

Xác nhận: deploy lại `dataops-api` và gọi `/health` — `database.connected`
phải là `true`.

---

## Sửa luật QC

Từ P10 bộ luật nằm trong Postgres (bảng `qc_rule`) và sửa ngay trong ứng dụng.
`rules/rules.yaml` chỉ còn là **seed** cho migration — sửa file đó không đổi
gì trên hệ thống đang chạy.

**Ai sửa được:** team_lead và admin. Người khác mở hộp luật chỉ đọc được.

**Sửa ở đâu:** nút **Xem bộ luật** trên Dashboard hoặc trang Vi phạm →
**Thêm luật** / **Sửa** / **Xoá** trên từng luật. Muốn ngừng tạm một luật thì
bỏ tick *Đang bật* thay vì xoá — SQL được giữ lại.

**Bao lâu có hiệu lực:** mỗi lần lưu, bộ luật lên một version. QC Runner thấy
version đổi ở chu kỳ kế tiếp (tối đa 5 phút) và tự chạy lại, kể cả khi lần nạp
không đổi. Bấm **Chạy QC ngay** trong banner vàng để khỏi chờ. Trong khoảng đó
cổng phát hành khoá với lý do "QC chưa chạy dưới bộ luật hiện tại" — đúng như
thiết kế, để không ai ký dưới danh sách vi phạm của bộ luật cũ.

**Trước khi lưu:** bấm **Thử SQL**. Server chạy câu SQL trong transaction chỉ
đọc, timeout 10 giây, và báo cột thiếu, số dòng bắt được, 20 dòng mẫu. Lúc lưu
server chạy thử lại một lần nữa — luật hỏng không lưu được.

**Khi QC Runner báo luật hỏng** (log `luat HONG`, job exit 1): thường là do
schema `fact_current` đổi sau khi luật được lưu. Các luật khác vẫn chạy, nhưng
lần nạp **không** được đánh dấu đã kiểm, nên cổng vẫn khoá. Mở hộp luật, sửa
hoặc tắt luật đó — version tăng, QC chạy lại.

```bash
gcloud logging read 'resource.labels.job_name="dataops-qc" AND textPayload:"HONG"' \
  --limit=20 --format='value(textPayload)'
```

**Xem bộ luật một bản ký đã dùng:** trang Phiên bản, bấm "luật vN" ở cột lần
nạp. Hộp mở ra đúng bộ luật tại version đó, chỉ đọc — kể cả luật đã bị xoá sau này.

**Quay lại một version cũ:** chưa có nút. Mở snapshot version cũ, tab YAML,
rồi sửa lại từng luật cho khớp. Mỗi thao tác là một version mới, có audit.

**Ai sửa gì:**

```sql
SELECT created_at, actor, action, entity_key, before, after
FROM audit_log WHERE entity = 'qc_rule' ORDER BY id DESC LIMIT 20;
```

**Cập nhật file seed** khi muốn môi trường dựng mới có bộ luật hiện tại: tab
YAML → **Tải YAML** → thay `rules/rules.yaml` → commit. Chỉ migration p10 đọc
file này, và chỉ khi bảng `qc_rule` còn rỗng.

---

## Dựng lại từ đầu

Mục tiêu của P5: một project trống thành hệ thống chạy được bằng
`terraform apply` và một lần deploy.

```bash
# 1. Bật API (việc duy nhất làm trước Terraform)
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  bigquery.googleapis.com storage.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com iap.googleapis.com secretmanager.googleapis.com \
  cloudscheduler.googleapis.com monitoring.googleapis.com \
  servicenetworking.googleapis.com --project=<PROJECT>

# 2. Bucket giữ state
gsutil mb -l <REGION> gs://<PROJECT>-tfstate

# 3. Hạ tầng
cd infra
cp terraform.tfvars.example terraform.tfvars   # điền project_id, region, alert_email
terraform init && terraform apply

# 4. Image
gcloud builds submit --config=apps/api/cloudbuild.yaml .
gcloud builds submit --config=apps/web/cloudbuild.yaml .
gcloud builds submit --config=jobs/cloudbuild.yaml .

# 5. Schema
gcloud run jobs execute dataops-migrate --region=<REGION>

# 6. Dữ liệu mẫu
gcloud run jobs execute dataops-seed --region=<REGION>
```

Để trống ba biến `api/web/jobs_service_account` trong `terraform.tfvars` thì
Terraform tự tạo và tự quản lý service account.

**Với project đang chạy** (service account đã tạo tay từ trước) thì phải
kéo chúng vào Terraform một lần trước khi apply:

```bash
./scripts/import-existing.sh dataops-poc-2026
```

Import không đụng tới tài nguyên thật — nó chỉ ghi vào state rằng tài nguyên
này từ nay thuộc về Terraform.
