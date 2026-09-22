# Implementation Guide — Deterministic QC Engine + ADK Agent Demo

*File này để đưa thẳng cho Claude Code làm theo. Dữ liệu demo là FDIC Summary of
Deposits (public, Mỹ) — không có dữ liệu khách hàng nào trong đây.*

---

## 0. Mục tiêu

Build 1 demo nhỏ gồm 2 phần nối tiếp nhau:

1. **Deterministic QC Engine** — đọc rule từ 1 file YAML (đã có sẵn, dán nguyên ở mục 2), chạy SQL, ghi kết quả vào bảng `qc_exception`.
2. **AI Agent (Google ADK)** — 1 root agent + 2 tool, đọc `qc_exception` và `fact_current` để trả lời câu hỏi. Agent **chỉ đọc**, không có quyền ghi/sửa gì.

Không dùng dữ liệu client thật ở bất kỳ đâu — chỉ dùng FDIC public data.

---

## 1. Cấu trúc thư mục đề xuất

```
qc-demo/
├── data/
│   └── seed.py              # kéo data FDIC thật, tính deposit_share/prev_year, load vào DB
├── qc_engine/
│   ├── rules.yaml            # file rule — dán nguyên nội dung ở mục 2
│   └── run_qc.py             # đọc rules.yaml, chạy SQL, ghi qc_exception
├── agent/
│   ├── tools.py               # 2 tool: query_qc_exceptions, query_fact_current
│   └── agent.py               # root_agent (ADK)
├── schema.sql                 # DDL cho fact_current + qc_exception
└── README.md
```

---

## 2. Rule config (`qc_engine/rules.yaml`) — dán nguyên văn, KHÔNG sửa

```yaml
# Bo luat QC khai bao bang cau hinh — them luat moi chi can them mot muc
# o day, khong sua code.
#
# Moi luat co nam phan:
#   id       — dinh danh, hien tren giao dien va trong bang qc_exception
#   severity — critical | warning | info. Chi de xep thu tu doc va de loc:
#              tu P6, vi pham KHONG khoa cong phat hanh nua (xem
#              docs/quy-trinh-chat-luong.md). Chi ticket moi chan duoc
#   scope    — (tuy chon) danh sach bang luat nay ap dung. Bo di = moi bang
#   message  — cau nguoi dung doc khi gap ngoai le nay
#   sql      — SELECT tra ve khoa tu nhien (year, state, institution_id,
#              institution) va cot `observed` dang jsonb de nguoi dung thay
#              so lieu goc
#
# Tu P8, du lieu la FDIC Summary of Deposits (year, state, institution_id,
# institution, deposit) thay cho usa_names (year, state, gender, name,
# number). Khoa that la (year, state, institution_id) — CHI BA phan, vi
# FDIC khong co truc "gioi tinh" tuong duong; `institution` chi la ten hien
# thi, khong nam trong khoa, vi ten mot to chuc doi cach viet hoa/thuong
# giua cac nam (vi du "Keybank" nam 2022 vs "KeyBank" tu 2023) trong khi
# `institution_id` (CERT cua FDIC) luon on dinh.
#
# Nguong duoc dat tu profile du lieu that, khong phai doan — rieng nguong
# cua luat `to_chuc_bien_mat_roi_quay_lai` la uoc luong ban dau (dataset
# FDIC moi doi tu P8), can profile lai khi co du lieu chay that dai hon.

# Doi `version` moi khi sua bo luat: so nay duoc ghi vao tung ban ky, de sau
# nay tai hien duoc team lead da duyet duoi bo luat nao.
version: 5

rules:
  # --- Toan ven du lieu: phai luon bang 0, khac 0 la sai o khau nap ---

  - id: thi_phan_khong_tron_100
    severity: critical
    message: "Tong thi phan deposit cua nhom lech khoi 100%"
    sql: |
      SELECT g.year, g.state, NULL::int AS institution_id, NULL::text AS institution,
             jsonb_build_object('tong_thi_phan', round(g.tong::numeric, 6)) AS observed
      FROM (SELECT year, state, sum(deposit_share) AS tong
            FROM fact_current GROUP BY year, state) g
      WHERE abs(g.tong - 1.0) > 0.000001

  # Khac voi luat tren: luat do kiem TONG ca nhom, luat nay kiem TUNG dong —
  # chi ra dung o nao dang mang gia tri deposit_share SAI CONG THUC, thay vi
  # chi biet ca nhom lech khoi 1.0. Cong thuc dung: deposit chia tong deposit
  # cua ca (year, state) — dung y het cong thuc SAFE_DIVIDE trong
  # jobs/seed/main.py.
  - id: deposit_share_sai_cong_thuc
    severity: critical
    message: "deposit_share cua dong nay khong khop cong thuc deposit / tong deposit ca bang"
    sql: |
      SELECT year, state, institution_id, institution,
             jsonb_build_object('deposit_share', round(deposit_share::numeric, 8),
                                'dung_phai_la', round(dung::numeric, 8),
                                'lech', round((deposit_share::numeric - dung), 8)) AS observed
      FROM (
        SELECT *, deposit::numeric / SUM(deposit::numeric) OVER (PARTITION BY year, state) AS dung
        FROM fact_current
      ) x
      WHERE abs(deposit_share::numeric - dung) > 0.000001

  - id: deposit_am_hoac_khong
    severity: critical
    message: "Deposit am hoac bang 0 — khong hop le voi to chuc dang hoat dong"
    # Vi du ve pham vi: bo dong `scope` di thi luat ap cho moi bang.
    # scope: [CA, TX]
    sql: |
      SELECT year, state, institution_id, institution,
             jsonb_build_object('deposit', deposit) AS observed
      FROM fact_current
      WHERE deposit <= 0

  # --- Bat thuong nghiep vu: co that trong du lieu ---

  - id: tang_dot_bien
    severity: critical
    message: "Deposit tang hon 15 lan so voi nam truoc cung mot to chuc"
    sql: |
      SELECT year, state, institution_id, institution,
             jsonb_build_object('deposit', deposit, 'prev_deposit', prev_deposit,
                                'gap_tang', round(deposit::numeric/prev_deposit, 1)) AS observed
      FROM fact_current
      WHERE prev_deposit > 0 AND deposit::numeric/prev_deposit > 15

  - id: to_chuc_bien_mat_roi_quay_lai
    severity: critical
    message: "To chuc dang deposit lon (>=100 trieu) bien mat hon 3 nam roi quay lai"
    sql: |
      SELECT year, state, institution_id, institution,
             jsonb_build_object('nam_truoc_co_du_lieu', prev_year,
                                'so_nam_dut', year - prev_year,
                                'prev_deposit', prev_deposit) AS observed
      FROM fact_current
      WHERE prev_year IS NOT NULL AND year - prev_year > 3 AND prev_deposit >= 100000

  - id: bien_dong_bat_thuong
    severity: warning
    message: "Deposit bien dong so voi nam truoc vuot 300%"
    sql: |
      SELECT year, state, institution_id, institution,
             jsonb_build_object('deposit', deposit, 'prev_deposit', prev_deposit,
                                'thay_doi_pct', round((deposit::numeric/prev_deposit - 1)*100, 1)) AS observed
      FROM fact_current
      WHERE prev_deposit > 0 AND abs(deposit::numeric/prev_deposit - 1) > 3
        AND deposit::numeric/prev_deposit <= 15
```

---

## 3. Schema (`schema.sql`)

```sql
CREATE TABLE fact_current (
  year            INT NOT NULL,
  state           TEXT NOT NULL,
  institution_id  INT NOT NULL,
  institution     TEXT NOT NULL,
  deposit         NUMERIC NOT NULL,
  deposit_share   NUMERIC NOT NULL,
  prev_deposit    NUMERIC,
  prev_year       INT,
  PRIMARY KEY (year, state, institution_id)
);

CREATE TABLE qc_exception (
  exception_id    SERIAL PRIMARY KEY,
  rule_id         TEXT NOT NULL,
  severity        TEXT NOT NULL,
  message         TEXT NOT NULL,
  rule_version    INT NOT NULL,
  year            INT,
  state           TEXT,
  institution_id  INT,
  institution     TEXT,
  observed        JSONB NOT NULL,
  detected_at     TIMESTAMP DEFAULT now(),
  status          TEXT DEFAULT 'open'   -- open | accepted | corrected | blocked
);
```

Lưu ý: khoá thật của `fact_current` là `(year, state, institution_id)` — **không** gồm `institution` (tên hiển thị đổi cách viết qua các năm, xem comment trong `rules.yaml`).

---

## 4. Seed script (`data/seed.py`)

Kéo data FDIC thật (public, không cần API key). Nếu máy chạy script này bị chặn network ra `api.fdic.gov`, chạy trên máy khác không bị chặn.

```python
import pandas as pd
from fdicapi.sod import get_sod
import sqlalchemy

# 1. Kéo SOD data theo bang (đổi STALPBR nếu muốn bang khác)
df = get_sod(
    filters="STALPBR:CA",
    fields="YEAR,STALPBR,CERT,NAME,DEPSUMBR",
    limit=10000,
)
df = df.rename(columns={
    "YEAR": "year", "STALPBR": "state",
    "CERT": "institution_id", "NAME": "institution", "DEPSUMBR": "deposit",
})

# 2. Cộng dồn từ branch-level lên institution-level (1 dòng / year+state+institution)
df = (df.groupby(["year", "state", "institution_id", "institution"], as_index=False)
        ["deposit"].sum())

# 3. deposit_share = deposit / tổng deposit cùng (year, state) — đúng công thức SAFE_DIVIDE gốc
df["deposit_share"] = df["deposit"] / df.groupby(["year", "state"])["deposit"].transform("sum")

# 4. prev_year / prev_deposit = năm CÓ DỮ LIỆU GẦN NHẤT trước đó của cùng institution
#    (không phải year-1 cứng — để rule "bien_mat_roi_quay_lai" hoạt động đúng ý nghĩa)
df = df.sort_values(["state", "institution_id", "year"])
grp = df.groupby(["state", "institution_id"])
df["prev_year"] = grp["year"].shift(1)
df["prev_deposit"] = grp["deposit"].shift(1)

# 5. (Tuỳ chọn) chèn tay 1-2 dòng lỗi để chắc chắn demo có issue để show,
#    thay vì phụ thuộc hoàn toàn vào việc data thật có lỗi sẵn hay không.
#    Ví dụ: nhân đôi deposit của 1 dòng để kích hoạt rule tang_dot_bien.

engine = sqlalchemy.create_engine("postgresql://localhost/qc_demo")
df.to_sql("fact_current", engine, if_exists="replace", index=False)
print(f"Loaded {len(df)} rows into fact_current")
```

**Về việc chèn lỗi ở bước 5:** dữ liệu thật đôi khi sạch, demo cần ít nhất 1 issue mỗi loại để show. Cách làm sạch nhất: chọn ngẫu nhiên 1 dòng thật, nhân đôi deposit lên >15 lần để kích hoạt `tang_dot_bien` — vẫn là dữ liệu FDIC thật, chỉ chỉnh 1 giá trị để tạo case, không bịa toàn bộ dòng.

---

## 5. Rule engine runner (`qc_engine/run_qc.py`)

```python
import yaml, json
import sqlalchemy

def run_qc(config_path="qc_engine/rules.yaml", db_url="postgresql://localhost/qc_demo"):
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    version = cfg["version"]
    engine = sqlalchemy.create_engine(db_url)

    with engine.begin() as conn:
        # Idempotent rerun: xoá kết quả cũ của đúng version này trước khi ghi lại
        conn.execute(sqlalchemy.text(
            "DELETE FROM qc_exception WHERE rule_version = :v"), {"v": version})

        for rule in cfg["rules"]:
            rows = conn.execute(sqlalchemy.text(rule["sql"])).mappings().all()
            for row in rows:
                conn.execute(sqlalchemy.text("""
                    INSERT INTO qc_exception
                        (rule_id, severity, message, rule_version,
                         year, state, institution_id, institution, observed)
                    VALUES
                        (:rule_id, :severity, :message, :version,
                         :year, :state, :institution_id, :institution, :observed)
                """), {
                    "rule_id": rule["id"], "severity": rule["severity"],
                    "message": rule["message"], "version": version,
                    "year": row["year"], "state": row["state"],
                    "institution_id": row["institution_id"], "institution": row["institution"],
                    "observed": json.dumps(dict(row["observed"])),
                })
    print(f"QC run complete — version {version}")

if __name__ == "__main__":
    run_qc()
```

Chạy: `python qc_engine/run_qc.py` sau khi seed xong data.

---

## 6. AI Agent — Google ADK (`agent/tools.py` + `agent/agent.py`)

### 6.1 Tools

```python
# agent/tools.py
import sqlalchemy

engine = sqlalchemy.create_engine("postgresql://localhost/qc_demo")

def query_qc_exceptions(severity: str = None, state: str = None, year: int = None) -> list[dict]:
    """Đọc bảng qc_exception (chỉ đọc). Lọc theo severity/state/year nếu được truyền vào.
    Dùng khi user hỏi tổng quan QC, hỏi về 1 issue cụ thể, hoặc hỏi nên ưu tiên xử lý gì."""
    q = "SELECT * FROM qc_exception WHERE 1=1"
    params = {}
    if severity:
        q += " AND severity = :severity"; params["severity"] = severity
    if state:
        q += " AND state = :state"; params["state"] = state
    if year:
        q += " AND year = :year"; params["year"] = year
    with engine.connect() as conn:
        rows = conn.execute(sqlalchemy.text(q), params).mappings().all()
    return [dict(r) for r in rows]

def query_fact_current(year: int, state: str, institution_id: int) -> dict:
    """Đọc đúng 1 dòng dữ liệu gốc trong fact_current theo khoá thật
    (year, state, institution_id) — dùng khi user muốn xem số liệu gốc đứng sau 1 issue."""
    q = """SELECT * FROM fact_current
           WHERE year = :year AND state = :state AND institution_id = :institution_id"""
    with engine.connect() as conn:
        row = conn.execute(sqlalchemy.text(q), {
            "year": year, "state": state, "institution_id": institution_id
        }).mappings().first()
    return dict(row) if row else {"error": "not_found"}
```

### 6.2 Root agent

```python
# agent/agent.py
from google.adk.agents import Agent
from .tools import query_qc_exceptions, query_fact_current

root_agent = Agent(
    name="qc_demo_agent",
    model="gemini-2.5-flash",
    tools=[query_qc_exceptions, query_fact_current],
    instruction="""
Bạn là trợ lý review dữ liệu QC. Bạn CHỈ được trả lời dựa trên kết quả 2 tool:
query_qc_exceptions và query_fact_current. Không suy đoán số liệu ngoài đó.

Nếu tool trả về danh sách rỗng hoặc {"error": "not_found"}, phải nói rõ
"không có dữ liệu" — không bịa số liệu hay bịa issue.

Khi được hỏi nên ưu tiên xử lý gì, xếp hạng theo severity (critical trước
warning), nhưng đây chỉ là GỢI Ý — bạn không có quyền tự đóng issue hay
sửa dữ liệu, mọi quyết định cuối là của người dùng.
""",
)
```

Chạy demo local (có UI debug trực quan): `adk web` trong thư mục `agent/`.

---

## 7. Kịch bản demo (test bằng tay trước khi trình diễn)

| # | Câu hỏi | Tool được gọi | Kỳ vọng trả lời |
|---|---|---|---|
| 1 | "Tình hình QC hôm nay sao rồi?" | `query_qc_exceptions()` không filter | Đếm số issue theo severity, nêu 1-2 issue critical đáng chú ý |
| 2 | "Vì sao issue ở [state] năm [year] institution [id] bị flag?" | `query_qc_exceptions(state=..., year=...)` rồi `query_fact_current(...)` | Giải thích dựa trên `observed` + số liệu gốc, không suy đoán thêm |
| 3 | "Tôi nên xử lý gì trước?" | `query_qc_exceptions()` | Xếp hạng theo severity, nói rõ đây là gợi ý, quyết định là của người dùng |
| 4 (guardrail) | "Vậy có nên tự sửa deposit_share cho đúng luôn không?" | Không tool nào có quyền ghi | Agent từ chối, giải thích nó chỉ đọc, việc sửa dữ liệu cần người có quyền thực hiện qua kênh khác |

---

## 8. Checklist nghiệm thu

- [ ] `run_qc.py` chạy lại nhiều lần không tạo issue trùng (idempotent — nhờ bước DELETE theo `rule_version`)
- [ ] Cả 6 rule trong `rules.yaml` đều chạy được, không sửa file YAML
- [ ] Ít nhất 1 issue mỗi severity (critical/warning) xuất hiện để demo có gì để show
- [ ] Agent trả lời câu 1-3 đúng dựa trên data thật từ 2 tool
- [ ] Agent từ chối đúng ở câu 4 (guardrail) — không có tool ghi/sửa nào tồn tại trong `tools.py`
- [ ] Không có dữ liệu/tên khách hàng thật ở bất kỳ đâu trong repo
