# Runbook vận hành

Tài liệu cho người trực, không phải cho người viết code. Mỗi mục trả lời
một tình huống có thật: dấu hiệu nhìn thấy, việc cần làm, và cách xác nhận
đã xong.

Bảng tra nhanh:

| Tình huống | Mục |
|---|---|
| Số trên màn hình có vẻ cũ | [Làm mới bảng khác Nạp lại từ nguồn](#làm-mới-bảng-khác-nạp-lại-từ-nguồn) |
| Cảnh báo "Sync Job im lặng quá 30 phút" | [Khi đồng bộ hỏng](#khi-đồng-bộ-hỏng) |
| Sale báo file tải về sai | [Khi file xuất sai](#khi-file-xuất-sai) |
| Cần quay lại số liệu của bản trước | [Quay lại phiên bản trước](#quay-lại-phiên-bản-trước) |
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
| `cong phat hanh dang khoa (N ngoai le nghiem trong)` | Cổng khoá lại sau lúc xin file | Xử lý hết ngoại lệ nghiêm trọng rồi xin lại |
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

**Quay lại một ô đã sửa nhầm** thì khác và đơn giản hơn: mở ngoại lệ tương
ứng, áp số cũ, ghi rõ lý do. `fact_override` tăng `version`, `audit_log` giữ
cả giá trị trước lẫn sau — không có gì biến mất.

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
