# QC Demo — Vai trò, Task List & Kịch bản Agent
*Tài liệu spec để vibe-code demo. Dùng dataset mẫu dạng "bank deposit market share" (FDIC Summary of Deposits — year, state, institution, deposit) — không dùng tên/dữ liệu khách hàng thật, an toàn để đưa vào GenAI/LLM.*

---

## 0. Dataset mẫu dùng cho demo — FDIC Summary of Deposits (SOD)

**Nguồn:** FDIC (Federal Deposit Insurance Corporation, Mỹ) — dữ liệu công khai, chính phủ Mỹ, cập nhật hàng năm, **có API + package Python chính thức**, không cần fabricate, không dính dữ liệu khách:
```bash
pip install fdicapi
```
```python
from fdicapi.sod import get_sod
from fdicapi.structure import get_institutions
from fdicapi.failures import get_failures
from fdicapi.history import get_history
```

Grain: **year × state × institution (bank)** — cấu trúc gần như 1:1 với market/player/country của dự án thật (chỉ khác domain: market share tiền gửi ngân hàng theo bang, thay vì market share dược phẩm/tên).

| Field (SOD) | Ý nghĩa | Tương đương domain gốc |
|---|---|---|
| `YEAR` | Năm khảo sát (SOD chạy hàng năm, mốc 30/6) | build_year |
| `CERT` | Mã định danh duy nhất của ngân hàng (FDIC certificate number) | player_id |
| `NAME` | Tên ngân hàng | canonical_player_name |
| `STALP` | Bang (VD: CA, NY) | country/state |
| `DEPSUMBR` | Tổng deposit tại bang đó, năm đó (đơn vị: nghìn USD) | number/revenue_native |
| `market_share` (tự tính) | Tỷ trọng deposit của ngân hàng đó trong tổng deposit toàn bang, năm đó | market_share |

**Công thức `market_share`** (tương đương SAFE_DIVIDE ban đầu, viết bằng pandas):
```python
df['market_share'] = df['DEPSUMBR'] / df.groupby(['YEAR', 'STALP'])['DEPSUMBR'].transform('sum')
```

**3 nguồn phụ có sẵn, dùng làm "catalogue" và "evidence" thật — không cần bịa:**
- `get_institutions()` → danh sách ngân hàng đang hoạt động, có CERT chuẩn → dùng làm **Name/Entity Catalogue** (mục 3, rule #4).
- `get_failures()` → danh sách ngân hàng đã bị đóng cửa/sáp nhập → dùng để tạo case **"inactive institution vẫn có deposit"** (issue thật, không cần giả lập).
- `get_history()` → sự kiện M&A/structure change → dùng làm **evidence thật** để giải thích case tăng/giảm đột biến ở rule Thresholds (mục 3, rule #2) — Agent có thể trích dẫn đúng sự kiện M&A làm bằng chứng khi giải thích issue.

Dataset này an toàn tuyệt đối cho GenAI/LLM (100% public government data), lại đúng domain bank theo yêu cầu.

---

## 1. Vai trò tổng quan (2 mảng, đúng 2 pillar của proposal)

| Mảng | Vai trò của bạn | Tương ứng Phase |
|---|---|---|
| **Deterministic QC Engine** | Data/Backend Engineer — viết rule logic, chạy trên dataset, sinh Issue Log | Phase 1 |
| **AI Agent (LLM Review)** | AI Engineer — build agent đọc Issue Log + evidence, trả lời/giải thích/ưu tiên issue | Phase 2 |

Demo cần thể hiện rõ: **Agent không thay thế Deterministic Engine, mà đọc kết quả của nó** — đây chính là luận điểm bán hàng quan trọng nhất (2 tầng năng lực tách biệt nhưng nối vào nhau).

---

## 2. Task list — Deterministic QC Engine

1. Chuẩn bị dataset mẫu theo schema ở mục 0 (`YEAR, STALP, CERT, NAME, DEPSUMBR`), tính sẵn `market_share` bằng công thức trên (pandas: `df.groupby(['YEAR','STALP'])['DEPSUMBR'].transform('sum')` rồi chia).
2. Viết 4 rule (chi tiết ở mục 3) — mỗi rule là **1 function độc lập**, nhận `DataFrame` trả về list issue.
3. Viết 1 hàm orchestrator gọi tuần tự 4 rule, gộp kết quả thành 1 **Issue Log** (list of dict / DataFrame).
4. Issue Log tối thiểu cần các field: `issue_id, rule_id, affected_key, expected, actual, severity, suggested_action`.
5. (Không bắt buộc cho demo) Thêm bước "review" giả lập — 1 cột `status` (Open/Resolved) để agent có gì đó để nói về "issue chưa xử lý".

### Nguyên tắc quan trọng khi code (để giữ đúng tinh thần proposal)
- Rule tách biệt hoàn toàn khỏi nhau (không viết 1 hàm khổng lồ check hết) — để dễ demo "thêm 1 rule mới" nếu khách hỏi.
- Threshold nên là **biến số** (đọc từ config/dict), không hard-code trong logic — dễ chỉnh khi demo live.
- `unmatched` / `review-required` **không được xếp cùng mức với lỗi cứng (Blocker)** — đây là điểm khách sẽ hỏi kỹ nhất (đã bàn ở các câu trước), nhớ giữ đúng khi code.

---

## 3. Chọn 4 rule dễ code nhất để demo (xếp theo độ dễ tăng dần)

| # | Rule | Input cần | Logic (1 câu) | Vì sao dễ |
|---|---|---|---|---|
| 1 | **Structure & completeness** | Chỉ cần `get_sod()` | `YEAR/STALP/CERT/NAME/DEPSUMBR` bị null → flag | `df[cols].isnull()`, không cần dữ liệu phụ |
| 2 | **Thresholds & sanity** | `get_sod()` (nhiều năm để so YoY) | `DEPSUMBR` âm → Blocker; deposit 1 CERT tăng/giảm YoY vượt X% → Warning (dùng `get_history()` để check có sự kiện M&A giải thích được không) | So sánh số học đơn giản, không cần model |
| 3 | **Calculations & roll-up** | `get_sod()` đã tính `market_share` | `SUM(market_share)` theo từng `(YEAR, STALP)` phải ≈ 1.0 (dung sai nhỏ) | `groupby().sum()` rồi so sánh với 1.0 |
| 4 | **Entity/institution validity** | `get_sod()` + `get_institutions()` (catalogue) + `get_failures()` | `CERT` không có trong `get_institutions()` → *review-required* (có thể là bank mới); `CERT` có trong `get_failures()` (đã đóng cửa) nhưng vẫn có `DEPSUMBR` > 0 → Blocker | Join/lookup đơn giản với 2 API có sẵn, không cần tự tạo catalogue giả |

**Gợi ý demo:** rule #4 dùng thẳng `get_failures()` — sẽ ra được ít nhất 1 case "ngân hàng đã failed nhưng SOD vẫn ghi deposit" một cách **hoàn toàn tự nhiên từ data thật**, không cần chèn tay. Đây là issue mà AI Agent sẽ nói tới ở mục 5.

---

## 4. Task list — AI Agent (chatbot)

1. Agent đọc được 2 nguồn context: **Issue Log** (query từ BigQuery, mục 6) + 1 **evidence store** nhỏ (vài dòng text/note giả lập làm "bằng chứng" cho vài issue — không cần Vertex AI Search/vector DB thật ở quy mô demo, query BigQuery rồi inject thẳng vào prompt gửi cho Vertex AI (Gemini) là đủ).
2. Viết **system prompt** cố định vai trò + giới hạn (mục 5.1), gọi qua Vertex AI API (model Gemini).
3. Implement tối thiểu 3 khả năng hội thoại (map đúng 3/5 "Review task" trong proposal — đủ để demo, không cần làm hết 5):
   - **Trend/issue explanation** — giải thích 1 issue cụ thể bằng ngôn ngữ tự nhiên, có trích evidence.
   - **Exception priority** — khi hỏi "nên xử lý gì trước", agent xếp hạng theo severity + có giải thích, **không tự động đóng issue**.
   - **Name presence / contradiction** — với issue loại "chưa khớp catalogue", agent đưa ra nhận định có evidence, nhưng **luôn chốt lại là cần người duyệt**, không tự thêm vào catalogue.
4. (Optional nếu còn thời gian) **Missing evidence check** — agent tự nhận ra khi được hỏi về 1 issue không có evidence, và nói rõ "không đủ căn cứ" thay vì đoán.
5. Giao diện: chat đơn giản (CLI hoặc 1 trang chat tối giản) — không cần UI phức tạp, mục tiêu là chứng minh **hành vi** của agent, không phải UI đẹp.

---

## 5. Kịch bản demo Agent (dùng để prompt/test khi vibe-code)

### 5.1 System prompt gợi ý (điều chỉnh theo data thật của bạn)
```
Bạn là trợ lý review dữ liệu QC cho khách hàng.
Bạn CHỈ được trả lời dựa trên Issue Log và evidence được cung cấp trong context.
Nếu không có evidence cho 1 issue, phải nói rõ "không đủ căn cứ", không suy đoán.
Bạn có thể: giải thích issue, xếp hạng độ ưu tiên xử lý, và đưa nhận định về ngân hàng/entity
chưa khớp catalogue — nhưng KHÔNG được tự kết luận thêm/xoá entity khỏi catalogue.
Mọi thay đổi catalogue là quyết định của con người, bạn chỉ đề xuất.
```

### 5.2 Đoạn hội thoại mẫu (4 lượt, dùng issue_id giả — thay bằng ID thật của bạn)

**Lượt 1 — Tổng quan**
> User: Tình hình QC hôm nay sao rồi?
> Agent: Có [N] issue đang mở — [X] Blocker, [Y] Warning, [Z] cần review. Blocker đáng chú ý nhất là {issue_id}: {mô tả ngắn}. Bạn muốn xem chi tiết cái nào trước?

**Lượt 2 — Giải thích 1 issue cụ thể**
> User: Vì sao {issue_id} bị flag?
> Agent: Rule {rule_id} phát hiện {expected} nhưng thực tế là {actual} (lệch {variance}). Theo evidence {evidence_ref}: {trích ngắn}. Gợi ý xử lý: {suggested_action}.

**Lượt 3 — Ưu tiên xử lý**
> User: Tôi nên xử lý cái gì trước?
> Agent: Xếp theo mức ảnh hưởng: 1) {issue_id_A} — Blocker, market_share của cả bang (YEAR, STALP) đang lệch khỏi 1.0 do lỗi này. 2) {issue_id_B} — Review-required, ngân hàng mới chưa có trong catalogue, rủi ro thấp hơn vì không chặn số liệu khác. Đây là gợi ý ưu tiên, quyết định đóng issue vẫn cần bạn xác nhận.

**Lượt 4 — Guardrail (khoảnh khắc quan trọng nhất của demo)**
> User: Vậy có nên thêm ngân hàng đó vào catalogue luôn không?
> Agent: Dữ liệu tôi có cho thấy ngân hàng này {mô tả} và evidence là {ref}, nhưng tôi không được phép tự thêm vào catalogue — cần người có quyền duyệt (business owner) xác nhận trước.

*(Lượt 4 chính là điểm khách sẽ ấn tượng nhất — cho thấy agent tuân đúng nguyên tắc "human-in-the-loop" mà proposal yêu cầu ở Section 7.2, không phải chỉ là chatbot trả lời bừa.)*

---

## 6. Tech stack tối giản đề xuất

| Phần | Gợi ý | Lý do |
|---|---|---|
| Data | **FDIC public API** qua package `fdicapi` (`get_sod`, `get_institutions`, `get_failures`, `get_history`) | Data thật, public, có sẵn Python client — không cần fabricate, không dính dữ liệu khách |
| QC Engine | Python + pandas | Đủ cho quy mô demo, không cần Spark/Databricks |
| Issue Log | DataFrame in-memory hoặc ghi ra BigQuery table (`qc_issue_log`) nếu muốn nối tiếp lên GCP | Ghi vào BigQuery thì Agent có thể query trực tiếp, không cần truyền tay |
| **Agent** | **Vertex AI (Gemini)** qua Vertex AI API — inject Issue Log + evidence (trích từ `get_history()`, `get_failures()`) vào context mỗi lần hỏi = "RAG-lite trên GCP" | Đúng stack GCP, không cần vector DB riêng ở quy mô demo |
| (Mở rộng nếu có thời gian) | **Vertex AI Agent Builder** hoặc **Vertex AI Search** cho retrieval có structure hơn | Nâng cấp tự nhiên nếu muốn demo gần hơn với kiến trúc thật của Phase 2 (Section 7.2/8) |
| Hosting/UI | **Cloud Run** chạy 1 app Flask/Streamlit nhỏ có khung chat, hoặc chạy local cho nhanh khi demo | Cloud Run là lựa chọn nhẹ, đúng hệ GCP, deploy nhanh |

---

## 7. Trình tự trình diễn demo cho khách (gợi ý)

1. Show dataset thô (YEAR/STALP/CERT/NAME/DEPSUMBR từ `get_sod()`).
2. Chạy QC engine trực tiếp → Issue Log xuất hiện có severity rõ ràng (bắt được: market_share không tổng = 1.0, deposit âm, ngân hàng đã failed nhưng vẫn có deposit, ngân hàng mới chưa khớp catalogue).
3. Mở chat, hỏi tổng quan (lượt 1) → agent tóm tắt đúng số issue vừa sinh ra (chứng minh agent đọc thật, không phải demo giả).
4. Hỏi sâu 1 issue Blocker (lượt 2).
5. Hỏi ưu tiên xử lý (lượt 3).
6. Hỏi câu "bẫy" về catalogue (lượt 4) — để agent thể hiện guardrail.
7. Kết: nhấn lại 1 câu — "Deterministic engine bắt lỗi cứng tự động, Agent chỉ hỗ trợ review có bằng chứng, quyết định cuối luôn là con người."

---

## 8. Checklist trước khi demo

- [ ] 4 rule chạy đúng, sinh Issue Log có severity phân biệt rõ
- [ ] Ít nhất 1 issue thuộc loại "review-required" (không phải Blocker) để agent có gì "nhạy cảm" để nói
- [ ] Agent trả lời đúng bằng evidence thật trong context (test thử hỏi 1 câu KHÔNG có evidence — agent phải nói "không đủ căn cứ", không bịa)
- [ ] Agent từ chối tự thêm/sửa catalogue khi được hỏi thẳng (test lượt 4)
- [ ] Không có tên khách hàng/dữ liệu khách hàng thật ở bất kỳ đâu trong code, prompt, hay dataset demo
- [ ] Toàn bộ demo chạy được trong < 2 phút để trình diễn live
