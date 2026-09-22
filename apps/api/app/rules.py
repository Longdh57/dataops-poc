"""Bo luat QC doc len de NGUOI DUNG XEM — khong phai de chay.

Cho chay luat la QC Runner (jobs/qc/main.py). Module nay chi doc dung
file do, y nguyen, roi tra ve ca hai dang:

- `rules` — da tach thanh tung muc, de giao dien bay ra thanh danh sach.
- `raw`   — noi dung tho cua file. Giu lai vi thu nguoi ta can doi chieu
  khi cai gi do sai la FILE, khong phai ban dien giai cua API.

API nay KHONG sua file luat. Them/sua luat van la sua rules/rules.yaml
roi chay lai QC — xem README muc "Bo luat".
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def rules_path() -> Path | None:
    """Tim file luat, thu lan luot ba cho.

    Trong image API, rules/ nam canh app/ (xem apps/api/Dockerfile). Khi
    chay tu source — uvicorn o apps/api, pytest — no nam o goc repo.
    Thu lan luot chu khong bat dat bien moi truong: quen dat la man hinh
    trong, ma bo luat thi luon nam dung mot trong ba cho nay.
    """
    candidates: list[Path] = []
    if env := os.getenv("RULES_PATH"):
        candidates.append(Path(env))
    candidates.append(Path("/srv/rules/rules.yaml"))
    candidates.append(Path(__file__).resolve().parents[3] / "rules" / "rules.yaml")
    for c in candidates:
        if c.is_file():
            return c
    return None


def parse(raw: str) -> dict[str, Any]:
    """Doc noi dung file luat. Nem ValueError kem cau giai thich.

    Khong kiem tra sau (severity hop le, sql chay duoc…): viec do la cua
    `validate()` trong QC Runner, va no phai chay TRUOC khi ghi vi pham.
    O day chi can du de bay ra man hinh, nen hong o dau thi noi ro o do.
    """
    try:
        config = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"file luat khong phai YAML hop le: {exc}") from exc

    if not isinstance(config, dict) or not isinstance(config.get("rules"), list):
        raise ValueError("file luat phai co khoa 'rules' la mot danh sach")

    rules = []
    for r in config["rules"]:
        if not isinstance(r, dict):
            continue
        scope = r.get("scope")
        rules.append({
            "id": r.get("id"),
            "severity": r.get("severity"),
            # Bo `scope` di = luat ap cho moi bang. Giu nguyen None de
            # giao dien noi duoc "moi bang" thay vi hien danh sach rong.
            "scope": [str(s).upper() for s in scope] if isinstance(scope, list) and scope else None,
            "message": r.get("message"),
            "sql": (r.get("sql") or "").strip(),
        })

    version = config.get("version")
    return {"version": version if isinstance(version, int) else None, "rules": rules}


def load() -> dict[str, Any]:
    """Bo luat dang nam trong file + noi dung tho cua chinh file do."""
    path = rules_path()
    if path is None:
        raise FileNotFoundError(
            "khong tim thay rules/rules.yaml — image API chua kem thu muc rules/, "
            "hoac dat RULES_PATH tro toi file luat")
    raw = path.read_text(encoding="utf-8")
    # Ten hien thi, khong phai duong dan tren may chu: nguoi doc can biet
    # day la file nao trong repo, khong can biet no nam o /srv hay /Users.
    return {**parse(raw), "raw": raw, "source": f"{path.parent.name}/{path.name}"}
