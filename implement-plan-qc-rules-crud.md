# Implementation Plan — CRUD bộ luật QC (P10)

*Thêm / sửa / xoá / tắt luật QC ngay trong ứng dụng, thay vì sửa
`rules/rules.yaml` rồi build lại image. Tài liệu này là plan để triển khai,
viết theo cùng cấu trúc với [implement-plan.html](implement-plan.html).*

| | |
|---|---|
| Giai đoạn | **P10** — nối tiếp P9 (AI Agent sang ADK) |
| Phạm vi | bộ luật QC trong `rules/rules.yaml` → bảng `qc_rule` trong Postgres, có giao diện CRUD |
| Người dùng bị ảnh hưởng | team_lead, admin (sửa) · analyst, sale (chỉ đọc, như hiện tại) |
| Effort ước tính | **~7 ngày công** cho một người |
| Chi phí vận hành thêm | $0 — không thêm dịch vụ cloud nào |

> **Về chữ "role" trong yêu cầu.** Yêu cầu ghi là "CRUD cho các role trong
> rules/rules.yaml". File đó không có role nào — nó chứa **rule** (luật QC:
> `deposit_spike`, `unusual_deposit_change`…). Đã xác nhận với người yêu cầu:
> "role" = "rule". Plan này không đụng tới vai trò người dùng (`app_user` /
> `app_role`).

---

## 01 · Tổng quan

### Hiện trạng

Bộ luật QC là một file YAML trong repo, được đọc ở hai chỗ:

| Ai đọc | Ở đâu | Để làm gì |
|---|---|---|
| API | [apps/api/app/rules.py](apps/api/app/rules.py) → `GET /api/rules` | hiện lên hộp "Xem bộ luật" ([rules-panel.tsx](apps/web/app/ui/rules-panel.tsx)) |
| QC Runner | [jobs/qc/main.py](jobs/qc/main.py), env `RULES_PATH` | chạy SQL từng luật, ghi `qc_exception`, ghi `rules_version` vào `sync_state` |

Cả hai image ([apps/api/Dockerfile](apps/api/Dockerfile), [jobs/Dockerfile](jobs/Dockerfile))
đều `COPY rules ./rules`. Hệ quả: **đổi một ngưỡng trong một luật** là commit → build
lại hai image → deploy → chạy lại QC. Người sửa luật thường không phải người
deploy, và giao diện hiện tại nói thẳng: *"khong sua duoc tu web"*.

Hai thứ đã có sẵn và plan này phải giữ nguyên ngữ nghĩa:

- `version` của bộ luật được ghi vào **bản ký** (`signed_version.rules_version`)
  và `sync_state.rules_version`, để tái hiện team lead đã duyệt dưới bộ luật nào
  ([docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md), mục "Bản ký ghi gì").
- Hộp xem luật hiện **hai version cạnh nhau**: version trong bộ luật và version
  QC đã chạy thật; lệch nhau thì cảnh báo `rules.outOfSync`.

### Mục tiêu

| | |
|---|---|
| Mục tiêu 1 | **Sửa luật không cần deploy.** Thêm / sửa / tắt / xoá luật từ hộp "Bộ luật QC", có hiệu lực ở lần QC kế tiếp. |
| Mục tiêu 2 | **Không mất dấu vết.** Mỗi thay đổi là một version mới, có snapshot toàn bộ bộ luật, có `audit_log` ai sửa gì; bản ký cũ vẫn tái hiện được đúng bộ luật đã duyệt. |
| Mục tiêu 3 | **Không lưu luật hỏng.** SQL được chạy thử trong transaction chỉ đọc trước khi lưu; sai cột, sai cú pháp, sai severity thì báo ngay trên form. |

### Phạm vi

| Hạng mục | Trong phạm vi | Ngoài phạm vi (để sau) |
|---|---|---|
| Lưu trữ | bảng `qc_rule` + `qc_ruleset` + `qc_ruleset_snapshot`; migration seed từ `rules.yaml` | đồng bộ ngược DB → file trong repo (GitOps) |
| API | CRUD, preview SQL, xem snapshot theo version, kích hoạt QC | import YAML hàng loạt — đã chốt không làm, tạo thủ công từng luật (mục 09) |
| QC Runner | đọc luật từ DB, bỏ qua luật đang tắt, tự chạy lại khi version đổi | thay đổi cách ghi `qc_exception` |
| Giao diện | form thêm/sửa, nút xoá có hỏi lại, nút "Thử SQL", nút "Chạy QC ngay", xử lý 409 | soạn SQL có gợi ý cột, diff giữa hai version |
| Phân quyền | team_lead + admin sửa; mọi người đọc | vai trò mới riêng cho "người viết luật" |
| Tài liệu | README, runbook, quy trình chất lượng, comment đầu `rules.yaml` | — |

---

## 02 · Thiết kế

### Quyết định gốc: bộ luật sống trong Postgres

Ba phương án đã cân nhắc, chọn phương án đầu:

| Phương án | Nhận xét |
|---|---|
| **DB là nguồn sự thật, `rules.yaml` là seed** (chọn) | Khớp kiến trúc đang có: *"Cloud SQL là nơi ghi và chịu trách nhiệm — override, phân quyền, audit"*. Có transaction, có `audit_log`, có khoá lạc quan sẵn (`ApiError` 409). QC job và API đã nối Postgres. Không thêm dịch vụ. |
| GitOps: UI tạo PR sửa `rules.yaml` | Cần token GitHub trong API, luật chỉ có hiệu lực sau khi merge + build 2 image + deploy. Không phải "CRUD", là "đề xuất sửa". |
| File YAML trên GCS, API ghi đè, job đọc | Đơn giản nhưng mất audit từng luật, không khoá được hai người sửa cùng lúc, không có snapshot theo version, và thêm một nguồn sự thật thứ ba. |

Sau P10, `rules/rules.yaml` vẫn nằm trong repo với hai vai trò: **seed** cho
migration (và cho môi trường dựng mới), và **tài liệu** mô tả định dạng luật.
Nó không còn là thứ QC chạy. Comment đầu file phải nói rõ điều đó.

### Mô hình dữ liệu

Ba bảng mới trong [apps/api/app/models.py](apps/api/app/models.py), migration
`p10_bo_luat_trong_db` (DDL đầy đủ ở Phụ lục A):

```
qc_rule                       một dòng = một luật, id là slug (PK, bất biến)
  id, severity, scope, message, sql, enabled, sort_order,
  created_by/at, updated_by/at

qc_ruleset                    MỘT dòng (id=1), như sync_state
  version, updated_by, updated_at, note

qc_ruleset_snapshot           toàn bộ bộ luật tại MỖI version
  version (PK), rules (json), created_by, created_at, note
```

Vì sao ba bảng chứ không phải một:

- `qc_rule` là thứ giao diện sửa. Khoá là `id` dạng slug vì `rule_id` đang được
  lưu **dưới dạng chuỗi** trong `qc_exception`, `ticket.from_rule_id`, và
  `signed_version.violations` — không có FK nào để đổi tên theo. Đổi tên luật =
  xoá + tạo mới, có chủ đích.
- `qc_ruleset.version` giữ đúng ngữ nghĩa số nguyên tăng dần của
  `rules_version` hiện tại. Mọi thao tác ghi thành công **tăng version lên 1**
  trong cùng transaction. Không semver, không version theo từng luật.
- `qc_ruleset_snapshot` là câu trả lời cho "bản ký #12 được duyệt dưới bộ luật
  nào". Trước P10 câu trả lời là `git show <commit>:rules/rules.yaml`; sau P10
  file không còn là sự thật, nên snapshot là bắt buộc, không phải tuỳ chọn.

`enabled = false` là "tắt tạm" — luật vẫn nằm trong catalog, QC bỏ qua. Khác
với xoá: xoá là bỏ hẳn khỏi `qc_rule` (vẫn còn trong snapshot và `audit_log`).

### Vòng đời một thay đổi

```
team_lead mở hộp "Bộ luật QC" ─▶ bấm Sửa trên deposit_spike
        │
        ▼
form: đổi ngưỡng 15 → 12 ─▶ "Thử SQL"  ──▶ POST /api/rules/preview
        │                                   (READ ONLY, timeout 10s)
        │                                   ◀── cột đủ · 41 dòng · 20 dòng mẫu
        ▼
"Lưu" (expected_version = 6) ──▶ PUT /api/rules/deposit_spike
        │                          ├─ validate + dry-run SQL lần nữa
        │                          ├─ UPDATE qc_rule
        │                          ├─ qc_ruleset.version 6 → 7
        │                          ├─ INSERT qc_ruleset_snapshot (7, toàn bộ luật)
        │                          └─ audit_log (rule_update, before/after)
        ▼
hộp luật hiện: version 7 · QC đã chạy version 6 ─▶ banner "chưa đồng bộ"
        │                                            + nút "Chạy QC ngay"
        ├─ bấm nút  ──▶ POST /api/rules/run-qc ──▶ Cloud Run Job dataops-qc (FORCE_QC=1)
        └─ không bấm ──▶ Scheduler gọi QC (mỗi 5 phút) ──▶ job thấy
                          sync_state.rules_version (6) ≠ qc_ruleset.version (7)
                          ──▶ tự chạy lại dù run_id chưa đổi
        ▼
sync_state.rules_version = 7 ─▶ banner tắt · vi phạm trên màn hình là của bộ luật 7
```

Điểm quan trọng ở nhánh dưới: hôm nay QC Runner **bỏ qua** nếu `qc_run_id`
đã bằng `last_run_id`. Sau P10 điều kiện bỏ qua là *"cùng run VÀ cùng version
luật"*. Nhờ vậy quên bấm nút cũng không sao — tối đa 5 phút sau bộ luật mới
được áp.

### Version và bản ký

Không đổi gì ở `POST /api/release`: nó vẫn đọc `sync_state.rules_version`
(version QC **đã chạy**), không đọc `qc_ruleset.version`. Đây là đúng: bản ký
phải ghi bộ luật đã sinh ra danh sách vi phạm mà team lead nhìn thấy, không phải
bộ luật vừa sửa xong chưa chạy. Khoá cứng "QC chưa kiểm lần nạp hiện tại thì
không ký được" (`require_gate_open`) nên mở rộng thêm một vế: *QC đã kiểm nhưng
dưới version cũ* cũng tính là chưa kiểm. Nếu không, team lead sửa luật rồi ký
ngay sẽ ký một bản mà phiếu duyệt nói về vi phạm của bộ luật cũ.

Trang Phiên bản hiện "version luật 6" — sau P10 con số đó bấm được, mở hộp
luật ở đúng snapshot 6 (`GET /api/rules?version=6`).

### Phân quyền

| Vai | Đọc catalog | Thử SQL | Thêm / sửa / tắt / xoá | Chạy QC ngay |
|---|---|---|---|---|
| analyst, sale | ✓ | — | — | — |
| team_lead, admin | ✓ | ✓ | ✓ | ✓ |

Cùng ngưỡng với nút "Refresh table" (Sync Job) hiện tại: `p.require("team_lead", "admin")`.
Luật là quy tắc chung, không theo phạm vi bang, nên không áp `scope_clause` —
giữ nguyên tinh thần của test `test_bo_luat_khong_phai_du_lieu_nen_khong_theo_pham_vi`.

### Kiểm tra trước khi lưu

Hai lớp, cả hai chạy ở server, form chỉ là lớp hiển thị:

1. **Cấu trúc** — chuyển `validate()` từ [jobs/qc/main.py](jobs/qc/main.py) sang
   dạng dùng chung được trong API (`app/rules.py`), giữ nguyên thông điệp lỗi
   tiếng Việt "báo hết một lượt". Thêm: `id` phải khớp `^[a-z][a-z0-9_]{2,63}$`,
   `scope` phải là mã bang viết hoa 2 ký tự.
2. **SQL chạy được và trả đúng cột** — chạy trong transaction
   `READ ONLY` + `SET LOCAL statement_timeout = '10s'`:
   `SELECT * FROM (<sql>) x LIMIT 0` → đọc `cursor.description`, đòi đủ
   `year, state, institution_id, institution, observed`. Thiếu cột → 422 kèm
   danh sách cột thiếu. SQL có INSERT/UPDATE/DROP → Postgres từ chối vì
   transaction chỉ đọc → 422 kèm thông điệp gốc.

`POST /api/rules/preview` dùng đúng lớp 2, thêm `count(*)` và 20 dòng mẫu
(có áp `scope` của luật) để người sửa **nhìn thấy** luật bắt được gì trước khi
lưu. QC Runner vẫn giữ `validate()` của riêng nó — phòng thủ hai lớp, vì DB có
thể bị sửa tay ngoài API.

---

## 03 · Thành phần thay đổi

| Thành phần | File | Thay đổi |
|---|---|---|
| Model | [apps/api/app/models.py](apps/api/app/models.py) | thêm `QcRule`, `QcRuleset`, `QcRulesetSnapshot` |
| Migration | `apps/api/alembic/versions/<rev>_p10_bo_luat_trong_db.py` | tạo 3 bảng; **seed** từ `rules/rules.yaml` qua `app.rules.rules_path()` + `parse()`; `qc_ruleset.version` = version trong file (6); snapshot 6. Idempotent: bảng đã có dữ liệu thì bỏ qua seed |
| Rules module | [apps/api/app/rules.py](apps/api/app/rules.py) | bỏ đọc file khỏi đường request; thêm `load_from_db(cur, version=None)`, `to_yaml(catalog)`, `validate_rule(rule)`, `dry_run(cur, sql, scope)` |
| API | [apps/api/app/main.py](apps/api/app/main.py) | `GET /api/rules` đọc DB, thêm `can_edit`, `?version=`; thêm `POST/PUT/DELETE /api/rules…`, `POST /api/rules/preview`, `POST /api/rules/run-qc`; mở rộng `require_gate_open` |
| Settings | [apps/api/app/settings.py](apps/api/app/settings.py) | `qc_job_name: str = "dataops-qc"` |
| QC Runner | [jobs/qc/main.py](jobs/qc/main.py) | `load_rules(conn)` từ `qc_rule WHERE enabled ORDER BY sort_order, id`; version từ `qc_ruleset`; điều kiện bỏ qua thêm vế version; `SAVEPOINT` từng luật để một luật hỏng không làm hỏng cả lần chạy; bỏ `RULES_PATH` |
| Jobs image | [jobs/Dockerfile](jobs/Dockerfile) | bỏ `COPY rules ./rules` (job không đọc file nữa) |
| API image | [apps/api/Dockerfile](apps/api/Dockerfile) | **giữ** `COPY rules` — migration seed cần file |
| Terraform | [infra/modules/runtime/main.tf](infra/modules/runtime/main.tf) | API service: env `QC_JOB_NAME`; `google_cloud_run_v2_job_iam_member.api_invoke_qc` role `roles/run.jobsExecutorWithOverrides` (vì gọi kèm `FORCE_QC=1`, cùng lý do với export job); QC job: bỏ env `RULES_PATH` |
| Web types | [apps/web/app/lib/types.ts](apps/web/app/lib/types.ts) | `QcRule` += `enabled`, `sort_order`, `updated_by`, `updated_at`; `RulesCatalog` += `can_edit`; thêm `RulePreview` |
| Web api | [apps/web/app/lib/api.ts](apps/web/app/lib/api.ts) | thêm `put`, `del` |
| Web UI | [apps/web/app/ui/rules-panel.tsx](apps/web/app/ui/rules-panel.tsx) | nút Thêm, nút Sửa/Xoá từng luật, pill "đang tắt", nút "Chạy QC ngay" trong banner lệch version, xử lý 409 |
| Web UI mới | `apps/web/app/ui/rule-form.tsx` | form thêm/sửa + panel kết quả "Thử SQL" |
| Web trang Phiên bản | [apps/web/app/versions/page.tsx](apps/web/app/versions/page.tsx) | "version luật N" bấm được → mở snapshot |
| i18n | [apps/web/app/i18n/vi.ts](apps/web/app/i18n/vi.ts), [en.ts](apps/web/app/i18n/en.ts) | ~30 khoá `rules.*` mới (danh sách ở Phụ lục B) |
| Seed file | [rules/rules.yaml](rules/rules.yaml) | sửa comment đầu file: đây là SEED, nguồn sự thật là bảng `qc_rule` |
| Test API | [apps/api/tests/test_rules.py](apps/api/tests/test_rules.py) | viết lại: đối chiếu với DB thay vì file; thêm test CRUD, 403, 422, 409, snapshot, audit |
| Test jobs | [jobs/tests/test_qc.py](jobs/tests/test_qc.py) | thêm test `load_rules` bỏ luật tắt, điều kiện bỏ qua theo version; giữ test file seed hợp lệ |
| Docs | README, [docs/runbook.md](docs/runbook.md), [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md) | xem Phụ lục C |

Không đổi: `POST /api/release`, `qc_exception`, `ticket`, Export Job, AI Agent
(agent đọc `qc_exception`, không đọc catalog luật).

---

## 04 · Hợp đồng API

| Method | Đường dẫn | Quyền | Ý nghĩa |
|---|---|---|---|
| GET | `/api/rules` | mọi vai | catalog từ DB. Thêm `can_edit`; `raw` giờ là YAML **render từ DB** (cùng định dạng file seed); `source: "qc_rule"`. `?version=N` → đọc từ snapshot, chỉ đọc |
| POST | `/api/rules` | team_lead, admin | tạo luật. 201 + `{rule, version}` |
| PUT | `/api/rules/{id}` | team_lead, admin | sửa toàn bộ luật (kể cả `enabled`). `id` bất biến |
| DELETE | `/api/rules/{id}` | team_lead, admin | xoá hẳn. 200 + `{version}` |
| POST | `/api/rules/preview` | team_lead, admin | chạy thử SQL: cột, số dòng, 20 dòng mẫu. Không ghi gì |
| POST | `/api/rules/run-qc` | team_lead, admin | 202, kích hoạt `dataops-qc` với `FORCE_QC=1`. Cùng khuôn với `/api/rebuild`: không gọi được job → 503 nói rõ |

Body ghi (POST/PUT):

```json
{
  "severity": "critical",
  "scope": ["CA", "TX"],
  "message": "Deposit increased more than 12x compared to the previous year",
  "sql": "SELECT year, state, institution_id, institution, jsonb_build_object(...) AS observed FROM fact_current WHERE ...",
  "enabled": true,
  "expected_version": 6
}
```

Mã lỗi, theo đúng quy ước đang dùng trong API:

| Mã | Khi nào | Body |
|---|---|---|
| 403 | không phải team_lead/admin | như `Principal.require` |
| 404 | PUT/DELETE id không tồn tại | |
| 409 | `expected_version` ≠ `qc_ruleset.version` | `{detail: {message, current_version, updated_by, updated_at}}` — giao diện đọc `ApiError.status === 409` như đã làm với xung đột khác |
| 422 | cấu trúc sai hoặc SQL không chạy được / thiếu cột | `{detail: {errors: [...], missing_columns: [...]}}` |
| 503 | `/run-qc` không gọi được Cloud Run | như `/api/rebuild` |

Mọi thao tác ghi đều đi qua `audit()` với `entity = "qc_rule"`, `action` ∈
`rule_create | rule_update | rule_delete | qc_run`, `before`/`after` là JSON
của luật. Trang chi tiết vi phạm đã đọc `audit_log` theo entity — không cần thêm
màn hình lịch sử riêng ở P10.

---

## 05 · Giao diện

Mở rộng hộp "Bộ luật QC" hiện có, không thêm trang mới. Hộp này đã được mở từ
Dashboard (kèm số vi phạm theo luật) và trang Vi phạm.

**Với người chỉ đọc** — không đổi gì, ngoài tab "YAML GỐC" đổi thành "YAML"
(vì không còn "gốc" nào nữa) và có nút tải xuống để copy về repo làm seed.

**Với team_lead / admin:**

- Đầu hộp: nút **Thêm luật**. Banner lệch version có thêm nút **Chạy QC ngay**.
- Mỗi luật: nút **Sửa**, **Xoá**; luật đang tắt hiện mờ kèm pill "đang tắt".
- **Form** (thay nội dung hộp, không mở hộp chồng hộp): `id` (khoá khi sửa),
  `severity` (select), `scope` (checkbox theo `useOptions().states`, bỏ trống =
  mọi bảng), `message`, `sql` (textarea monospace), `enabled`. Hai nút: **Thử
  SQL** và **Lưu**. Kết quả thử hiện ngay dưới SQL: cột thiếu (đỏ), số dòng bắt
  được, bảng 20 dòng mẫu với cột `observed` in JSON.
- **Xoá**: hộp hỏi lại (dùng `Modal` + `btn-danger` như "Refresh table"), nêu
  id và số vi phạm của luật ở lần nạp hiện tại nếu có.
- **409**: `ErrBox` hiện "bộ luật đã được X sửa lúc Y", kèm nút "Tải lại" →
  `invalidateQueries(["rules"])`, form giữ nguyên nội dung đang gõ.
- Sau mỗi thao tác ghi thành công: invalidate `["rules"]`; **không** tự chạy
  QC — người dùng bấm, hoặc chờ Scheduler.

Gợi ý cho người viết luật, hiện dưới ô `message` (không ép): *"id và message
viết tiếng Anh — AI Agent đọc và trả lời thẳng cho người dùng"* (quy ước P9).

---

## 06 · Task theo giai đoạn

Tổng ~7 ngày công. Mỗi giai đoạn có điều kiện kết thúc để không trôi.

### P10.0 · Schema & seed — 1 ngày

- Thêm 3 model vào `models.py`, docstring nói rõ vì sao `id` là slug bất biến.
- Migration: tạo bảng, seed từ `rules.yaml` (qua `rules_path()` để chạy được cả
  trong image `/srv/rules` lẫn từ source), ghi snapshot cho version seed.
- `alembic upgrade head` trên local và trên job `migrate`; `alembic downgrade -1`
  gỡ sạch.

**Điều kiện kết thúc:** sau migrate, `SELECT id FROM qc_rule` khớp từng id với
file; `qc_ruleset.version = 6`; `qc_ruleset_snapshot` có dòng 6. Chạy migrate
lần hai không nhân đôi dữ liệu.

### P10.1 · API — 2 ngày

- `app/rules.py`: `load_from_db`, `to_yaml`, `validate_rule`, `dry_run`.
- `GET /api/rules` đọc DB; `?version=`; `can_edit`.
- `POST / PUT / DELETE`, mỗi cái trong **một transaction**: validate → dry-run →
  ghi luật → tăng version → snapshot → audit.
- `POST /api/rules/preview`, `POST /api/rules/run-qc`, `settings.qc_job_name`.
- `require_gate_open`: thêm vế "QC chạy dưới version cũ" → 409 với thông điệp
  riêng, để màn hình ký nói đúng lý do.
- Test (`test_rules.py` viết lại + thêm): catalog khớp DB; `raw` parse lại ra
  đúng luật; analyst POST → 403; id sai / severity sai → 422 liệt kê hết lỗi;
  SQL thiếu `observed` → 422 kèm `missing_columns`; SQL có `INSERT` → 422;
  `expected_version` cũ → 409; tạo thành công → version +1, snapshot mới, 1 dòng
  audit; xoá → mất khỏi catalog nhưng còn trong snapshot cũ; `?version=6` sau khi
  đã lên 8 vẫn trả đúng 6 luật cũ; `run-qc` không có `GCP_PROJECT_ID` → 503.

**Điều kiện kết thúc:** `pytest apps/api` xanh; `curl` tạo một luật mới rồi
`GET /api/rules` thấy version tăng và `in_sync = false`.

### P10.2 · QC Runner & hạ tầng — 1 ngày

- `jobs/qc/main.py`: `load_rules(conn)`; điều kiện bỏ qua
  `da_kiem == run_id and applied_version == current_version`; `SAVEPOINT` từng
  luật — luật lỗi thì log + ghi `sync_state.last_error`, các luật khác vẫn chạy;
  `SET LOCAL statement_timeout` cho từng luật (đề xuất 120s) để một luật nặng
  không ăn hết 900s của job.
- `jobs/Dockerfile` bỏ `COPY rules`; Terraform: env `QC_JOB_NAME`, IAM
  `api_invoke_qc`, bỏ `RULES_PATH`; `terraform plan` sạch, `apply`.
- Test jobs: `load_rules` bỏ luật `enabled = false`; điều kiện bỏ qua với 4 tổ
  hợp (run mới/cũ × version mới/cũ); luật lỗi không làm mất kết quả luật khác.

**Điều kiện kết thúc:** sửa một ngưỡng qua API, **không bấm gì thêm**, trong
5 phút `sync_state.rules_version` nhảy lên version mới và số vi phạm đổi theo.
Bấm "Chạy QC ngay" thì dưới 1 phút.

### P10.3 · Giao diện — 2 ngày

- `types.ts`, `api.ts` (`put`, `del`), i18n vi/en.
- `rules-panel.tsx`: nút Thêm / Sửa / Xoá / Chạy QC ngay, pill "đang tắt",
  hộp hỏi lại khi xoá, xử lý 409, tab "YAML" + tải xuống.
- `rule-form.tsx`: form + "Thử SQL" + panel kết quả.
- `npm run typecheck` sạch; đi trọn kịch bản ở mục 07 trên `docker compose up`
  với danh tính `lead@dataops.test` và `analyst.tx@dataops.test`.

**Điều kiện kết thúc:** analyst mở hộp luật **không thấy** nút nào để sửa;
team lead thêm được luật mới có SQL cố tình thiếu cột và bị chặn ngay trên
form với đúng tên cột thiếu.

### P10.4 · Snapshot trên trang Phiên bản & tài liệu — 1 ngày

- Trang Phiên bản: "version luật N" bấm được → `RulesModal` với `version=N`,
  tiêu đề ghi rõ "snapshot, chỉ đọc".
- Hộp luật chịu được `rule_id` không còn trong catalog (đã xoá): Dashboard và
  trang Vi phạm hiện id thô + nhãn "luật đã xoá" thay vì bỏ qua.
- Tài liệu theo Phụ lục C. Comment đầu `rules.yaml`.

**Điều kiện kết thúc:** mở một bản ký cũ, bấm version luật, thấy đúng bộ luật
lúc ký dù bộ luật hiện tại đã khác.

---

## 07 · Kết quả cần đạt

### Kịch bản chạy trọn (nghiệm thu)

1. `lead@dataops.test` mở Dashboard → "Xem bộ luật" → Sửa `deposit_spike`, đổi
   `> 15` thành `> 12` → Thử SQL thấy số dòng tăng → Lưu. Version 6 → 7, banner
   "chưa đồng bộ" hiện.
2. Bấm "Chạy QC ngay" → dưới 1 phút banner tắt, thẻ "Vi phạm theo luật" đổi số.
3. Thêm luật mới `deposit_share_over_100` với SQL thiếu cột `observed` → 422,
   form đỏ đúng cột thiếu. Sửa lại → 201.
4. Mở tab thứ hai cùng tài khoản, tắt luật vừa tạo. Quay lại tab đầu, sửa
   `message` → 409 kèm tên người sửa → Tải lại → sửa tiếp → OK.
5. Xoá luật vừa tạo → hộp hỏi lại → xác nhận → version tăng, luật mất khỏi
   danh sách, `audit_log` có `rule_delete`.
6. Ký một bản (POST /api/release) → `signed_version.rules_version` = version QC
   đã chạy. Trang Phiên bản bấm version đó → thấy đúng snapshot.
7. `analyst.tx@dataops.test` mở hộp luật: đọc được, không có nút sửa; gọi thẳng
   `PUT /api/rules/...` → 403.

### Tiêu chí nghiệm thu

| Tiêu chí | Ngưỡng | Cách kiểm chứng |
|---|---|---|
| Sửa luật không cần deploy | Bắt buộc | Kịch bản 1–2, không build image, không `gcloud run deploy` |
| Không lưu được luật hỏng | Bắt buộc | Kịch bản 3; thêm test 422 cho SQL có `DROP TABLE` |
| Không mất lịch sử | Bắt buộc | Kịch bản 5–6; mọi version ≤ hiện tại đều có snapshot |
| Chống ghi đè | Bắt buộc | Kịch bản 4: phiên sau nhận 409, không ghi đè |
| Phân quyền | Bắt buộc | Kịch bản 7 |
| Bộ luật mới tự có hiệu lực | ≤ 5 phút | P10.2, không bấm "Chạy QC ngay" |
| Preview không treo API | ≤ 10 s | `statement_timeout` trong `dry_run`; test với `pg_sleep(30)` → 422 |
| Test | Xanh | `pytest apps/api`, `pytest jobs`, `npm run typecheck` |

### Thay đổi cho người dùng

| | |
|---|---|
| Team Lead | Ngưỡng luật là thứ họ hiểu rõ nhất và đổi thường xuyên nhất. Giờ đổi được trong 2 phút, thấy ngay luật bắt được gì, và tên họ nằm trên thay đổi đó. |
| Analyst / Sale | Không đổi gì, ngoài việc bộ luật họ đọc luôn là bộ luật đang chạy hoặc sắp chạy — không còn lệch với file trong repo. |
| Người vận hành | Không còn "sửa YAML → build 2 image → deploy → chạy QC". `rules.yaml` chỉ còn để dựng môi trường mới. |

---

## 08 · Quyết định & rủi ro

### Quyết định

| Quyết định | Phương án bị loại | Lý do |
|---|---|---|
| Postgres là nguồn sự thật của luật | GitOps qua PR; file trên GCS | Xem mục 02. Cần transaction, audit, khoá lạc quan, snapshot — tất cả đã có sẵn trong Postgres. |
| `id` luật bất biến | Cho đổi tên | `rule_id` là chuỗi trong `qc_exception`, `ticket.from_rule_id`, `signed_version.violations`. Đổi tên = lịch sử đứt. Muốn tên mới thì tạo mới + xoá cũ, có audit. |
| Version là số nguyên toàn cục, +1 mỗi lần ghi | Version theo từng luật; semver | Giữ nguyên ngữ nghĩa `rules_version` đang ghi vào bản ký. Bộ luật nhỏ (dưới 20 luật), ít người sửa. |
| Snapshot toàn bộ bộ luật mỗi version | Chỉ dựa `audit_log` before/after | Ghép lại bộ luật tại một thời điểm từ audit là việc tay và dễ sai; snapshot vài KB mỗi lần, đọc một câu SELECT. |
| Khoá lạc quan theo version cả bộ luật | Theo từng luật | Đơn giản, đủ dùng: hai người sửa hai luật khác nhau cùng lúc là hiếm, và người sau chỉ mất một lần "Tải lại". |
| Có cả `enabled` lẫn DELETE | Chỉ một trong hai | Tắt tạm để thử nghiệm ngưỡng mà không mất SQL; xoá để dọn luật đã chết. Hai nhu cầu khác nhau. |
| team_lead được sửa luật | Chỉ admin | Team lead là người duyệt vi phạm và hiểu ngưỡng; bắt họ nhờ admin là quay lại vấn đề "người sửa không phải người deploy". |
| Preview chạy bằng DB user của API, trong transaction READ ONLY + timeout | DB role riêng chỉ SELECT trên `fact_current` | Đủ cho PoC. Rủi ro SQL tuỳ ý bởi team_lead **đã tồn tại** hôm nay với bất kỳ ai commit được `rules.yaml`. Nâng cấp lên role riêng ghi ở rủi ro. |
| QC tự chạy lại khi version đổi | Chỉ dựa nút "Chạy QC ngay" | Người quên bấm là chuyện chắc chắn xảy ra; Scheduler đã có sẵn, chỉ thêm một vế điều kiện. Nút để khỏi chờ. |
| `raw` là YAML render từ DB | Bỏ tab YAML | Tab này vẫn có ích: copy về repo làm seed, và đối chiếu nguyên văn. Nhưng không được gọi là "gốc" nữa. |

### Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Luật có SQL cực nặng hoặc `pg_sleep` làm treo QC job | Trung bình | `statement_timeout` từng luật trong job (120s) + `SAVEPOINT` để luật khác vẫn chạy; preview có timeout 10s nên người viết thấy trước. |
| SQL ghi/xoá dữ liệu lọt qua preview | Thấp | Transaction READ ONLY từ chối mọi câu ghi; `dry_run` chạy lại lúc lưu, không tin kết quả preview từ client. Nâng cấp sau: DB role `qc_reader` chỉ SELECT. |
| Bản ký cũ tham chiếu version không có snapshot | Cao nếu bỏ qua | Migration ghi snapshot cho version seed (6) **trước** khi bất kỳ ai sửa; test "mọi `signed_version.rules_version` đều có snapshot". Bản ký có version < 6 (trước P8) chấp nhận không tái hiện được — ghi rõ trong runbook. |
| `rules.yaml` trong repo lệch với DB, người mới đọc nhầm | Trung bình | Comment đầu file + README nói rõ file là seed; tab YAML có nút tải xuống để cập nhật seed khi cần. |
| Xoá luật đang có vi phạm / ticket tham chiếu | Thấp | Không cascade gì; `qc_exception` của run cũ giữ nguyên `rule_id`; giao diện hiện "luật đã xoá". Hộp xoá nêu số vi phạm hiện tại để người xoá biết. |
| Ký ngay sau khi sửa luật, chưa chạy QC | Trung bình | Mở rộng `require_gate_open`: QC dưới version cũ = chưa kiểm → 409. |
| Migration chạy trong image thiếu `rules/` | Thấp | Image API vẫn `COPY rules`; migration dùng `rules_path()` (đã có test đường dẫn nóng) và **thất bại rõ** nếu không tìm thấy file thay vì tạo bộ luật rỗng. |
| Hai người sửa cùng lúc, người sau mất công gõ | Thấp | 409 giữ nguyên nội dung form, chỉ bắt tải lại catalog. |

---

## 09 · Quyết định đã chốt (23/09/2026)

Bốn câu hỏi mở đã được người yêu cầu trả lời. Plan ở trên đã viết theo đúng
các câu trả lời này, không còn nhánh nào phải chọn trước khi bắt đầu P10.0.

| # | Câu hỏi | Quyết định | Hệ quả trong plan |
|---|---|---|---|
| 1 | "role" hay "rule"? | **Rule** — luật QC | Toàn bộ plan giữ nguyên. Không có việc gì với `app_user` / `app_role`. |
| 2 | Ai được sửa luật? | **team_lead và admin** | Bảng phân quyền ở mục 02; `p.require("team_lead", "admin")` cho mọi endpoint ghi, preview, run-qc. |
| 3 | Import YAML hàng loạt? | **Không** — tạo thủ công từng luật | Không có `POST /api/rules/import`. Bộ luật ban đầu vào DB duy nhất qua migration seed (P10.0). Tab YAML chỉ để đọc và tải xuống. |
| 4 | "Tạo luật từ ticket"? | **Không** | P10.4 giữ nguyên 1 ngày. Món nợ "bộ luật không tự lớn lên" ở cuối `docs/quy-trinh-chat-luong.md` vẫn để nguyên, ghi thêm rằng giờ có thể tạo luật trong app. |

---

## 10 · Ghi chú triển khai (23/09/2026)

Đã triển khai đủ P10.0–P10.4. Những chỗ code khác plan, và vì sao:

| Plan viết | Code làm | Lý do |
|---|---|---|
| Mở rộng `require_gate_open` cho vế "QC chạy dưới version cũ" | Thêm hàm `qc_stale()` dùng chung cho `POST /api/release`, `/api/gate`, `/api/summary`, `/api/exceptions`, trả lý do `"run"` hoặc `"rules"` | `require_gate_open` chỉ chặn tải file, không chặn ký. Bản ký đã đóng băng nên tải file của nó không cần chờ QC. Dashboard, trang Vi phạm và trang Phiên bản có câu riêng cho lý do "bộ luật vừa đổi" |
| Luật hỏng trong QC Runner ghi `sync_state.last_error` | Log `HONG`, exit 1, và **không** đánh dấu lần nạp đã kiểm | `last_error` đang là lỗi của Sync Job, trộn vào sẽ làm banner độ tươi nói sai. Không đánh dấu đã kiểm thì cổng vẫn khoá: danh sách vi phạm thiếu một luật không được ký |
| Chặn SQL ghi bằng transaction READ ONLY | Thêm hai lớp: từ chối dấu `;` giữa SQL (API và QC Runner), và mọi lệnh chạy thử đều mang tham số | Khi luật không có `scope`, bản đầu chạy thử không kèm tham số, psycopg dùng simple protocol cho phép nhiều lệnh, và `) x; COMMIT; DROP TABLE …` thoát được khỏi READ ONLY. Test đã bắt được lỗi này — xem [`test_lop_protocol_cung_chan_nhieu_lenh`](apps/api/tests/test_rules.py) |
| `DELETE /api/rules/{id}` | `expected_version` đi qua query string | Body của DELETE không được mọi proxy chuyển tiếp; proxy `/api/gw` cũng được thêm method DELETE |
| (không có) | `%` trong SQL luật được nhân đôi ở cả chạy thử lẫn QC Runner | QC Runner truyền tham số vào cùng câu lệnh — trước P10 một luật có `LIKE 'A%'` làm hỏng cả job |

Kiểm chứng: `apps/api/tests/test_rules.py` từ 9 lên 32 test, `jobs/tests/test_qc.py` thêm 3 test
(tổng 21); suite API không có lỗi mới so với trước P10; chạy thật
QC Runner với luật hỏng và luật tắt; đi trọn kịch bản 3, 4, 5, 6, 7 trên giao
diện. Kịch bản 2 ("Chạy QC ngay") chỉ kiểm bằng test 503 và chạy QC Runner
local — local API trỏ vào project GCP thật nên không bấm.

---

## Phụ lục A · DDL

```sql
CREATE TABLE qc_rule (
  id          varchar(64)  PRIMARY KEY,        -- ^[a-z][a-z0-9_]{2,63}$
  severity    varchar(16)  NOT NULL CHECK (severity IN ('critical','warning','info')),
  scope       json,                            -- ["CA","TX"]; NULL = mọi bảng
  message     text         NOT NULL,
  sql         text         NOT NULL,
  enabled     boolean      NOT NULL DEFAULT true,
  sort_order  integer      NOT NULL,           -- giữ thứ tự đọc như trong YAML
  created_by  varchar(320) NOT NULL,
  created_at  timestamptz  NOT NULL DEFAULT now(),
  updated_by  varchar(320) NOT NULL,
  updated_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE qc_ruleset (                      -- một dòng, id = 1
  id          integer      PRIMARY KEY DEFAULT 1,
  version     integer      NOT NULL,
  updated_by  varchar(320),
  updated_at  timestamptz,
  note        text
);

CREATE TABLE qc_ruleset_snapshot (
  version     integer      PRIMARY KEY,
  rules       json         NOT NULL,           -- [{id, severity, scope, message, sql, enabled, sort_order}]
  created_by  varchar(320) NOT NULL,
  created_at  timestamptz  NOT NULL DEFAULT now(),
  note        text
);
```

Seed trong migration (phác thảo):

```python
from app import rules as rules_file

path = rules_file.rules_path()
if path is None:
    raise RuntimeError("p10: khong tim thay rules/rules.yaml de seed — dung migration")
catalog = rules_file.parse(path.read_text(encoding="utf-8"))
version = catalog["version"] or 1
# INSERT qc_rule theo thứ tự file (sort_order = 10, 20, 30…)
# INSERT qc_ruleset (1, version, 'migration', now(), 'seed tu rules/rules.yaml')
# INSERT qc_ruleset_snapshot (version, <toàn bộ luật>, 'migration', now())
```

## Phụ lục B · Khoá i18n mới (vi)

```
rules.add            "Thêm luật"
rules.edit           "Sửa"
rules.delete         "Xoá"
rules.disabled       "đang tắt"
rules.deleted        "luật đã xoá"
rules.runQc          "Chạy QC ngay"
rules.runQcNote      "QC Runner đang chạy — banner này tắt khi xong"
rules.snapshotTitle  "Bộ luật QC · snapshot version {v} (chỉ đọc)"
rules.download       "Tải YAML"
rules.tab.raw        "YAML"                       (đổi từ "YAML GỐC")
rules.form.id        "Mã luật (slug, không đổi được sau khi tạo)"
rules.form.severity  "Mức"
rules.form.scope     "Phạm vi (bỏ trống = mọi bảng)"
rules.form.message   "Câu người dùng đọc"
rules.form.messageHint "Viết tiếng Anh — AI Agent đọc và trả lời thẳng cho người dùng"
rules.form.sql       "SQL — SELECT trả về year, state, institution_id, institution, observed"
rules.form.enabled   "Đang bật"
rules.form.preview   "Thử SQL"
rules.form.save      "Lưu"
rules.preview.ok     "SQL chạy được · {n} dòng · {ms} ms"
rules.preview.missing "Thiếu cột: {cols}"
rules.preview.error  "SQL lỗi: {err}"
rules.preview.sample "{n} dòng đầu"
rules.confirmDeleteTitle "Xoá luật {id}?"
rules.confirmDeleteBody  "Luật này đang bắt {n} vi phạm ở lần nạp hiện tại. Xoá thì lần QC kế tiếp không còn kiểm nữa. Snapshot và audit vẫn giữ lại."
rules.conflict       "Bộ luật đã được {who} sửa lúc {when}. Tải lại rồi sửa tiếp — nội dung bạn đang gõ được giữ nguyên."
rules.reload         "Tải lại"
rules.saved          "Đã lưu · bộ luật lên version {v}"
```

## Phụ lục C · Tài liệu phải cập nhật

| File | Sửa gì |
|---|---|
| [README.md](README.md) | bảng Endpoint: thêm 5 dòng; mục "Bộ luật QC": file → bảng `qc_rule`, `rules.yaml` là seed; thêm mục "CRUD bộ luật (P10)" theo khuôn các mục P8/P9; bỏ câu "image API build từ GỐC repo để kèm rules/" khỏi phần giải thích chạy luật (giữ cho migration) |
| [docs/runbook.md](docs/runbook.md) | mục mới "Sửa luật QC": ai sửa được, sửa xong bao lâu có hiệu lực, cách xem snapshot, cách khôi phục một version cũ (tạo lại luật từ snapshot — chưa có nút, ghi rõ) |
| [docs/quy-trinh-chat-luong.md](docs/quy-trinh-chat-luong.md) | "Bản ký ghi gì": version luật giờ trỏ tới snapshot; "Còn lại": giữ món "bộ luật không tự lớn lên" (không làm "tạo luật từ ticket" ở P10), ghi thêm rằng luật giờ tạo được ngay trong app nên bước "đẻ ra luật mới" không còn cần deploy |
| [rules/rules.yaml](rules/rules.yaml) | comment đầu file: SEED, không phải nguồn sự thật; cách xuất lại từ tab YAML |
| [apps/web/app/lib/types.ts](apps/web/app/lib/types.ts) | sửa comment `QcRule`: bỏ "khong sua duoc tu web" |
