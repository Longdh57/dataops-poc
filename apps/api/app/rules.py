"""Bo luat QC — doc, kiem tra va chay thu. Tu P10 bo luat song trong Postgres.

Ba bang (xem models.py): `qc_rule` la thu giao dien sua, `qc_ruleset`
giu version toan cuc, `qc_ruleset_snapshot` giu toan bo bo luat o moi
version de ban ky cu tai hien duoc.

rules/rules.yaml KHONG con la thu QC chay. No chi con la SEED cho
migration p10 (va cho moi truong dung moi) — nen `rules_path()` va
`parse()` van o day, nhung khong nam tren duong request nua.

Cho CHAY luat van la QC Runner (jobs/qc/main.py). Module nay chi can du
de: bay bo luat ra man hinh, chan luat hong truoc khi luu, va cho nguoi
sua thay luat bat duoc gi truoc khi luu.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import yaml

SEVERITIES = ("critical", "warning", "info")
# Slug: chu thuong, so, gach duoi. Bat dau bang chu. Toi da 64 (do dai cot).
RULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
STATE_RE = re.compile(r"^[A-Z]{2}$")
# QC Runner INSERT ... SELECT x.year, x.state, ... x.observed — thieu mot
# cot la ca lan chay hong. Kiem truoc khi luu.
REQUIRED_COLUMNS = ("year", "state", "institution_id", "institution", "observed")
PREVIEW_TIMEOUT_MS = 10_000
PREVIEW_SAMPLE = 20


# ------------------------------------------------------------- file seed

def rules_path() -> Path | None:
    """Tim file seed, thu lan luot ba cho.

    Trong image API, rules/ nam canh app/ (xem apps/api/Dockerfile). Khi
    chay tu source — uvicorn o apps/api, pytest, alembic — no nam o goc
    repo. Chi migration p10 con can file nay.
    """
    candidates: list[Path] = []
    if env := os.getenv("RULES_PATH"):
        candidates.append(Path(env))
    candidates.append(Path("/srv/rules/rules.yaml"))
    # Goc repo la cap cha thu tu tinh tu file nay — nhung CHI khi chay tu
    # source. Trong image, app/ nam ngay duoi /srv nen khong du bon cap,
    # va parents[3] nem IndexError truoc khi kip thu duong /srv o tren.
    here = Path(__file__).resolve()
    if len(here.parents) > 3:
        candidates.append(here.parents[3] / "rules" / "rules.yaml")
    for c in candidates:
        if c.is_file():
            return c
    return None


def parse(raw: str) -> dict[str, Any]:
    """Doc noi dung file luat YAML. Nem ValueError kem cau giai thich."""
    try:
        config = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"file luat khong phai YAML hop le: {exc}") from exc

    if not isinstance(config, dict) or not isinstance(config.get("rules"), list):
        raise ValueError("file luat phai co khoa 'rules' la mot danh sach")

    rules = [normalize(r) for r in config["rules"] if isinstance(r, dict)]
    version = config.get("version")
    return {"version": version if isinstance(version, int) else None, "rules": rules}


# ------------------------------------------------------------ kiem tra

def normalize(r: dict) -> dict[str, Any]:
    """Dua mot luat ve dang chuan truoc khi kiem hay luu.

    `scope` viet thuong van ra dung ma bang (QC Runner cung upper()); danh
    sach rong = bo di = moi bang. SQL bo dau `;` cuoi — no nam trong mot
    subquery, dau cham phay o do la loi cu phap.
    """
    scope = r.get("scope")
    if isinstance(scope, list):
        scope = [str(s).strip().upper() for s in scope if str(s).strip()] or None
    elif scope in ("", None):
        scope = None
    sql = (r.get("sql") or "").strip()
    while sql.endswith(";"):
        sql = sql[:-1].rstrip()
    return {
        "id": (r.get("id") or "").strip() if isinstance(r.get("id"), str) else r.get("id"),
        "severity": r.get("severity"),
        "scope": scope,
        "message": (r.get("message") or "").strip(),
        "sql": sql,
    }


def validate_rule(r: dict, *, check_id: bool = True) -> list[str]:
    """Loi cau truc cua MOT luat — bao het mot luot, khong dung o loi dau.

    Cung thong diep voi validate() trong QC Runner: nguoi sua luat khong
    doc code, bao ro tu day thi ho khong phai doan.
    """
    loi: list[str] = []
    ten = r.get("id") or "luat moi"
    if check_id:
        if not r.get("id"):
            loi.append(f"{ten}: thieu 'id'")
        elif not isinstance(r["id"], str) or not RULE_ID_RE.match(r["id"]):
            loi.append(f"{ten}: 'id' chi gom chu thuong, so, gach duoi; bat dau bang chu; "
                       "3–64 ky tu")
    if r.get("severity") not in SEVERITIES:
        loi.append(f"{ten}: 'severity' phai la mot trong {list(SEVERITIES)}, "
                   f"dang la {r.get('severity')!r}")
    if not r.get("message"):
        loi.append(f"{ten}: thieu 'message' — day la cau nguoi dung doc")
    if not r.get("sql"):
        loi.append(f"{ten}: thieu 'sql'")
    elif ";" in r["sql"]:
        # Luat la MOT cau SELECT nam trong subquery cua QC Runner. Dau `;`
        # o giua la dau hieu cua nhieu lenh — `) x; COMMIT; DROP ...` —
        # nen chan tu day, khong doi toi lop protocol ben duoi.
        loi.append(f"{ten}: 'sql' chi duoc la MOT cau SELECT — khong dung dau ';' "
                   "(ke ca trong chuoi; dung chr(59) neu that su can)")
    scope = r.get("scope")
    if scope is not None:
        if not isinstance(scope, list) or not scope:
            loi.append(f"{ten}: 'scope' phai la danh sach bang, hoac bo han di")
        else:
            sai = [s for s in scope if not isinstance(s, str) or not STATE_RE.match(s)]
            if sai:
                loi.append(f"{ten}: 'scope' co ma bang khong hop le: {sai}")
    return loi


def validate_catalog(rules: list[dict]) -> list[str]:
    """Kiem ca bo luat: tung luat + trung id. Dung cho seed."""
    loi: list[str] = []
    seen: set[str] = set()
    for r in rules:
        loi += validate_rule(r)
        if r.get("id") in seen:
            loi.append(f"{r['id']}: trung 'id' voi luat khac")
        seen.add(r.get("id"))
    return loi


# ---------------------------------------------------------- doc tu DB

RULE_COLS = """id, severity, scope, message, sql, enabled, sort_order,
               created_by, created_at, updated_by, updated_at"""


def ruleset_state(cur) -> dict[str, Any]:
    cur.execute("SELECT version, updated_by, updated_at FROM qc_ruleset WHERE id = 1")
    return cur.fetchone() or {"version": None, "updated_by": None, "updated_at": None}


def current_rules(cur) -> list[dict]:
    cur.execute(f"SELECT {RULE_COLS} FROM qc_rule ORDER BY sort_order, id")
    return cur.fetchall()


def snapshot_rows(rules: list[dict]) -> list[dict]:
    """Phan cua luat can giu trong snapshot — noi dung, khong phai ai sua."""
    return [{"id": r["id"], "severity": r["severity"], "scope": r["scope"],
             "message": r["message"], "sql": r["sql"], "enabled": r["enabled"],
             "sort_order": r["sort_order"]} for r in rules]


def load_from_db(cur, version: int | None = None) -> dict[str, Any] | None:
    """Bo luat hien tai, hoac bo luat o dung mot version (tu snapshot).

    Tra None khi xin mot version khong co snapshot.
    """
    st = ruleset_state(cur)
    if version is None or version == st["version"]:
        rules = current_rules(cur)
        v = st["version"]
        meta = {"updated_by": st["updated_by"], "updated_at": st["updated_at"],
                "snapshot": False}
    else:
        cur.execute("""SELECT version, rules, created_by, created_at
                       FROM qc_ruleset_snapshot WHERE version = %s""", (version,))
        snap = cur.fetchone()
        if not snap:
            return None
        rules = snap["rules"]
        v = snap["version"]
        meta = {"updated_by": snap["created_by"], "updated_at": snap["created_at"],
                "snapshot": True}
    return {"version": v, "rules": rules, "raw": to_yaml(v, rules),
            "source": "qc_rule", **meta}


# ------------------------------------------------------------ YAML

class _Dumper(yaml.SafeDumper):
    pass


def _str_repr(dumper: yaml.SafeDumper, data: str):
    # SQL nhieu dong in thanh khoi `|` — doc duoc va copy nguoc ve file seed.
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_repr)


def to_yaml(version: int | None, rules: list[dict]) -> str:
    """Bo luat dang YAML, cung dinh dang file seed rules/rules.yaml.

    Dung de doc nguyen van tren man hinh, va de tai ve thay file seed khi
    can dung moi truong moi voi bo luat hien tai.
    """
    items = []
    for r in rules:
        item: dict[str, Any] = {"id": r["id"], "severity": r["severity"]}
        if r.get("scope"):
            item["scope"] = list(r["scope"])
        if r.get("enabled") is False:
            item["enabled"] = False
        item["message"] = r["message"]
        item["sql"] = r["sql"].rstrip() + "\n"
        items.append(item)
    head = ("# Bo luat QC xuat tu bang qc_rule (Postgres) — nguon su that tu P10.\n"
            "# Dung lam file seed rules/rules.yaml khi dung moi truong moi.\n")
    body = yaml.dump({"version": version, "rules": items}, Dumper=_Dumper,
                     sort_keys=False, allow_unicode=True, width=100)
    return head + body


# --------------------------------------------------------- chay thu SQL

def escape_percent(sql: str) -> str:
    """QC Runner truyen tham so vao cau SQL cua luat, nen `%` trong luat
    (vi du LIKE 'A%') phai nhan doi — neu khong psycopg coi no la cho
    trong. Chay thu va chay that phai escape GIONG NHAU."""
    return sql.replace("%", "%%")


def dry_run(conn, sql: str, scope: list[str] | None,
            sample: int = PREVIEW_SAMPLE) -> dict[str, Any]:
    """Chay thu SQL cua luat trong transaction CHI DOC, co timeout.

    Tra ve cot tim thay, cot con thieu, so dong bat duoc (da ap scope) va
    vai dong mau. SQL loi thi tra `error` chu khong nem — nguoi goi quyet
    dinh 422 hay chi hien len form.

    Transaction READ ONLY la cai chan that: INSERT/UPDATE/DROP trong luat
    bi Postgres tu choi, khong phai bi mot danh sach tu khoa bat.
    `conn` phai la connection rieng — ham nay rollback het khi xong.
    """
    base = escape_percent(sql)
    # MOI lenh o day deu mang it nhat mot tham so. Co tham so thi psycopg
    # di extended query protocol, va Postgres tu choi nhieu lenh trong mot
    # lan goi. Khong tham so thi no di simple protocol — luc do
    # `) x; COMMIT; DROP TABLE ...` chay duoc, va COMMIT ket thuc luon
    # transaction chi doc. Dung nhu QC Runner: no luon truyen tham so.
    where, params = ("WHERE x.state = ANY(%s)", [scope]) if scope else ("WHERE %s", [True])
    t0 = time.monotonic()
    out: dict[str, Any] = {"ok": False, "columns": [], "missing_columns": [],
                           "count": None, "rows": [], "ms": None, "error": None}
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = {int(PREVIEW_TIMEOUT_MS)}")
            cur.execute(f"SELECT * FROM ({base}) x LIMIT %s", [0])
            cols = [d.name for d in cur.description or []]
            out["columns"] = cols
            out["missing_columns"] = [c for c in REQUIRED_COLUMNS if c not in cols]
            if out["missing_columns"]:
                return out
            cur.execute(f"SELECT count(*) AS n FROM ({base}) x {where}", params)
            out["count"] = cur.fetchone()["n"]
            if sample:
                cur.execute(
                    f"""SELECT x.year, x.state, x.institution_id, x.institution, x.observed
                        FROM ({base}) x {where} LIMIT %s""", [*params, sample])
                out["rows"] = cur.fetchall()
            out["ok"] = True
    except Exception as exc:  # noqa: BLE001 — loi SQL cua nguoi viet luat
        msg = str(exc).strip().splitlines()
        out["error"] = msg[0] if msg else exc.__class__.__name__
    finally:
        conn.rollback()
        out["ms"] = round((time.monotonic() - t0) * 1000)
    return out
