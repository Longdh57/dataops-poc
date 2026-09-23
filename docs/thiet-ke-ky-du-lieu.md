# Thiết kế: ký dữ liệu và đóng băng bằng snapshot BigQuery (P11)

> Phạm vi: `POST /api/release` (ký), `POST /api/exports` (xin file) và Export Job.
> Code: [app/bq_snapshot.py](../apps/api/app/bq_snapshot.py), [app/main.py](../apps/api/app/main.py) (`release`, `create_export`), [jobs/export/main.py](../jobs/export/main.py), migration `a7d3e9c1b5f2_p11_snapshot_bigquery_khi_ky`.

## 1. Vấn đề

Trước P11, một bản ký chỉ lưu **danh sách `run_id`** (`signed_version.source_run_ids`) cùng vân tay dữ liệu `checksum`. Còn Export Job thì đọc thẳng bảng fact **đang sống** trên BigQuery:

```sql
SELECT ... FROM `<project>.dataops_src.fact_names` WHERE run_id IN UNNEST(@runs)
```

Trong khi đó, team Data sửa số **tại chỗ, dưới cùng một `run_id`** là chuyện bình thường. Hệ quả:

| Tình huống | Kết quả trước P11 |
|---|---|
| Team Data sửa số sau khi team lead ký | File gửi khách mang **số mới chưa ai duyệt**, nhưng vẫn đóng dấu "bản đã ký" |
| Team Data xoá hoặc ghi đè một `run_id` | Bản đã ký **không còn dữ liệu** để xuất lại |
| Có `checksum` | Chỉ tính trên bản sao Postgres lúc ký; Export **không đối chiếu lại**, nên không chặn được gì |

Bản ký ghi lại được *đã duyệt cái gì*, nhưng **không giữ lại dữ liệu đã duyệt**.

## 2. Quyết định

Mỗi lần ký, chụp bảng fact nguồn thành một **table snapshot BigQuery** (chỉ đọc), lưu table id vào Postgres. Từ đó Export **chỉ đọc từ snapshot**, không bao giờ đọc bảng đang sống.

```
               POST /api/release (team_lead / admin)
                          │
      ┌───────────────────┴────────────────────┐
      │ 1. Kiểm cổng: ticket chặn, QC chưa kiểm,  │   (giữ nguyên như P6/P10)
      │    phiếu duyệt khi còn nợ                  │
      │ 2. checksum ← fact_current (Postgres)      │   = dữ liệu QC đã kiểm
      │ 3. signed_at = now() làm tròn về giây      │
      │ 4. SNAPSHOT dataops_src.fact_names         │
      │      → dataops_signed.snapshot_<epoch>     │   BigQuery copy job
      │ 5. checksum' ← snapshot (BigQuery)         │
      │ 6. checksum' ≠ checksum → xoá snapshot, 409│
      │ 7. INSERT signed_version(... bq_snapshot)  │   Postgres, cùng signed_at
      │    lỗi → xoá snapshot, trả lỗi             │
      └────────────────────────────────────────────┘

  POST /api/exports  → từ chối nếu bản ký mới nhất không có bq_snapshot
  Export Job         → SELECT ... FROM `<bq_snapshot>` WHERE run_id IN (source_run_ids)
```

## 3. Chi tiết thiết kế

### 3.1 Tên snapshot

```
<project>.<BIGQUERY_SIGNED_DATASET>.snapshot_<epoch giây lúc ký>
ví dụ: dataops-poc-2026.dataops_signed.snapshot_1728203494
```

- `<epoch>` là `int(signed_at.timestamp())`, theo UTC.
- `signed_at` được **làm tròn về giây** và ghi tường minh vào `signed_version.signed_at` (không dùng `now()` của Postgres), nên tên bảng và thời điểm ký luôn chỉ cùng một khoảnh khắc: `snapshot_<epoch>` ⇔ `signed_at`.
- Hai người ký trong **cùng một giây** thì trùng tên. Copy job dùng `WRITE_EMPTY` nên người đến sau nhận `409 … thử lại sau vài giây`, và không bao giờ ghi đè bản ký của người kia. Cột `bq_snapshot` còn có ràng buộc `UNIQUE`, là lớp chặn thứ hai.

### 3.2 Snapshot nằm ở dataset riêng: `dataops_signed`

| | `dataops_src` (nguồn) | `dataops_signed` (bản ký) |
|---|---|---|
| Ai ghi | Team Data | API (`dataops-api`, `roles/bigquery.dataEditor` cấp trên dataset) |
| Ứng dụng | Chỉ đọc | Tạo snapshot lúc ký, xoá snapshot mồ côi khi ký thất bại |
| Export Job | Không đọc nữa | Đọc (`dataops-jobs`, `dataViewer`) |
| Hết hạn bảng | — | **Không có**: snapshot sống cùng bản ký |
| `terraform destroy` | Không xoá nội dung | Không xoá nội dung |

Lý do tách riêng:
- Dataset nguồn vẫn giữ nguyên nguyên tắc "team Data ghi, ứng dụng chỉ đọc".
- Team Data không có quyền ghi vào `dataops_signed`, nên không ai sửa hay xoá được bản đã ký sau lưng người ký.

Quyền để tạo snapshot:
- Trên bảng nguồn cần `bigquery.tables.createSnapshot` và `getData`. `dataViewer` cấp ở mức project đã có sẵn hai quyền này.
- Trên dataset đích cần `tables.create`, `tables.update` và `tables.delete`, có trong `dataEditor`.

### 3.3 Chụp cả bảng, lọc lúc xuất

Snapshot BigQuery không lọc được theo điều kiện: nó luôn chụp **cả bảng**. Điều này chấp nhận được vì:
- **Chi phí**: snapshot chỉ tính tiền lưu trữ cho phần dữ liệu **khác** với bảng gốc. Bảng gốc không đổi thì snapshot gần như miễn phí; team Data sửa bao nhiêu thì snapshot chỉ tốn chừng đó.
- **Đúng phạm vi**: Export vẫn lọc `run_id IN source_run_ids` và `state IN scope_states`, vì lúc ký bảng có thể đã chứa lần nạp chưa ai duyệt.

Phương án `CREATE TABLE … AS SELECT … WHERE run_id IN (…)` bị loại vì nó tạo một bản sao đầy đủ, tính tiền lưu trữ theo toàn bộ số dòng ở mỗi lần ký.

Snapshot được tạo bằng **copy job `operation_type=SNAPSHOT`** thay vì DDL `CREATE SNAPSHOT TABLE`, để không phải ghép tên bảng vào chuỗi SQL.

### 3.4 Đối chiếu vân tay: snapshot phải đúng là thứ QC đã kiểm

QC chạy trên **bản sao Postgres** (`fact_current`), bản này được Sync Job đồng bộ từ BigQuery. Giữa lần đồng bộ cuối và lúc bấm ký, team Data có thể đã sửa nguồn. Nếu cứ chụp mà không kiểm, snapshot sẽ chứa số mà QC chưa từng thấy.

Vì vậy, ngay sau khi chụp:
1. `checksum` được tính trên Postgres (`data_checksum`, như trước P11).
2. `checksum'` được tính trên snapshot bằng **cùng một công thức**, viết lại cho BigQuery (`bq_snapshot.bq_checksum`):
   ```
   md5( count(*) : sum(deposit) : sum(int32_có_dấu(md5(year|state|institution_id|deposit)[0:8])) )
   ```
   Postgres ép 8 ký tự hex đầu thành số **int32 có dấu** (`::bit(32)::int`). BigQuery đọc hex thành số không dấu, nên nửa trên phải trừ đi 2³² để ra cùng một số.
3. Nếu `checksum' ≠ checksum`, API **xoá snapshot** và trả `409 "BigQuery đã đổi số với bản QC đã kiểm"`. Cần chờ Sync và QC chạy lại trên số mới rồi mới ký.

Sau bước này, một bản ký có `bq_snapshot` đảm bảo rằng dữ liệu trong snapshot, giới hạn theo `source_run_ids`, **trùng khớp với dữ liệu QC đã kiểm và team lead đã duyệt**.

### 3.5 Tính nguyên tử giữa BigQuery và Postgres

BigQuery và Postgres không chung một transaction, nên thứ tự các bước được chọn để không bao giờ có **bản ký trỏ tới snapshot không tồn tại**:

| Lỗi xảy ra ở | Hệ quả | Xử lý |
|---|---|---|
| Tạo snapshot | Chưa có gì | 503 (hoặc 409 nếu trùng tên), không ghi bản ký |
| Cập nhật mô tả / tính checksum' | Có snapshot, chưa có bản ký | Xoá snapshot, 503 |
| Lệch vân tay | Có snapshot, chưa có bản ký | Xoá snapshot, 409 |
| INSERT / commit Postgres | Có snapshot, chưa có bản ký | Xoá snapshot (best-effort), 500 |

Trường hợp xấu nhất còn lại là việc xoá cũng thất bại. Khi đó sẽ có một **snapshot mồ côi**: vô hại, vì không bản ký nào trỏ tới nó, chỉ tốn chút lưu trữ. Truy vấn dọn dẹp ở mục 5.

### 3.6 Export

- `POST /api/exports` từ chối (409) nếu bản ký mới nhất có `bq_snapshot IS NULL`, tức các bản ký trước P11. Sẽ **không có** cơ chế lùi về đọc bảng đang sống.
- Export Job (`snapshot_table`) kiểm tra lại lần nữa, và kiểm cả **định dạng tên** `project.dataset.snapshot_<số>` trước khi ghép vào `FROM`.
- Dấu bản ký (`.ban-ky.txt` hoặc sheet bìa) có thêm dòng `Snapshot dữ liệu: …`, để người cầm file truy ngược được đúng bảng trên BigQuery.

### 3.7 Mô tả và nhãn trên snapshot

Mỗi snapshot được gắn:
- `description`: `Ban ky '<nhãn>' — <người ký> — <signed_at>. Export doc tu day; KHONG xoa …`
- `labels`: `app=dataops`, `kind=signed-version`

Nhờ đó, người mở BigQuery Console biết ngay bảng nào là bản ký, và lọc được bằng nhãn.

## 4. Thay đổi schema và cấu hình

**Postgres** (migration `a7d3e9c1b5f2`, sau `f4b82d6e1a37`):

```sql
ALTER TABLE signed_version ADD COLUMN bq_snapshot VARCHAR(1024);   -- NULL = ký trước P11
ALTER TABLE signed_version ADD CONSTRAINT uq_signed_version_bq_snapshot UNIQUE (bq_snapshot);
```

**Biến môi trường API** (`app/settings.py`):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `BIGQUERY_DATASET` | `dataops_src` | Dataset nguồn |
| `BIGQUERY_TABLE` | `fact_names` | Bảng fact được chụp |
| `BIGQUERY_SIGNED_DATASET` | `dataops_signed` | Nơi chứa snapshot |
| `REGION` | `asia-southeast1` | Location của các job BigQuery |

Nếu thiếu `GCP_PROJECT_ID`, API **không ký được** (503), vì ký mà không đóng băng được dữ liệu thì không còn là ký.

**Terraform**:
- `modules/data`: thêm dataset `dataops_signed`, cấp `dataEditor` cho SA `api` và `dataViewer` cho SA `jobs`.
- `modules/runtime`: truyền `BIGQUERY_DATASET` và `BIGQUERY_SIGNED_DATASET` cho service API.

## 5. Vận hành

**Triển khai lần đầu**: chạy `terraform apply` để tạo dataset và quyền, chạy migration (`dataops-migrate`), rồi deploy API và jobs. Môi trường local (docker-compose) gọi BigQuery thật bằng ADC, nên dataset phải có sẵn:

```bash
bq --location=asia-southeast1 mk --dataset dataops-poc-2026:dataops_signed
```

**Bản ký cũ (trước P11)**: không xuất file được nữa, vì dữ liệu của chúng chưa bao giờ được đóng băng. Muốn xuất thì ký lại.

**Tìm snapshot mồ côi**: là những snapshot có trong `dataops_signed` nhưng không có dòng nào trong `signed_version.bq_snapshot` trỏ tới.

```sql
-- BigQuery
SELECT table_name FROM `dataops-poc-2026.dataops_signed.INFORMATION_SCHEMA.TABLES`
WHERE table_type = 'SNAPSHOT';
```

So danh sách này với `SELECT bq_snapshot FROM signed_version` trên Postgres. Chỉ xoá những bảng **không** xuất hiện trong kết quả đó.

**Không bao giờ xoá snapshot của một bản ký còn dùng**. File đã gửi khách phải tái tạo được từ đúng snapshot đó.

**Lưu ý hết hạn**: snapshot BigQuery không phụ thuộc time travel của bảng gốc. Bảng gốc bị xoá hay ghi đè (`WRITE_TRUNCATE`) thì snapshot vẫn còn nguyên.

## 6. Kiểm thử

| Test | Giữ điều gì |
|---|---|
| `apps/api/tests/test_p11_snapshot.py::test_ten_snapshot_theo_epoch_giay_luc_ky` | Tên theo mẫu `snapshot_<epoch>` |
| `…::test_ky_ghi_ten_snapshot_khop_thoi_diem_ky` | `bq_snapshot` được lưu, khớp với `signed_at`, đối chiếu đúng checksum và `run_id` |
| `…::test_khong_chup_duoc_snapshot_thi_khong_co_ban_ky` | Snapshot lỗi hoặc lệch thì không có dòng `signed_version` nào |
| `…::test_ban_ky_khong_co_snapshot_thi_khong_xuat_file` | Bản ký cũ không xuất được |
| `jobs/tests/test_export.py` (4 test P11) | Export đọc từ snapshot, không lùi về bảng sống, từ chối tên lạ, dấu bản ký ghi tên snapshot |

Test API không gọi BigQuery thật: fixture `bigquery_gia` trong `conftest.py` thay `bq_snapshot.freeze` và `drop` bằng bản giả. Công thức `bq_checksum` chỉ kiểm được trên BigQuery thật. Sau khi deploy, hãy ký thử một lần: ký thành công nghĩa là vân tay hai phía đã khớp.
