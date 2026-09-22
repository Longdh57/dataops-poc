"""Truy van thuan cho AI Agent — khong dinh ADK, goi truc tiep va test duoc.

`Scope` la lat cat toi thieu cua authz.Principal can cho lop nay:
unrestricted + tap bang. `tools.py` doc no tu session state (server gan luc
mo session, KHONG BAO GIO tu tham so LLM truyen vao) roi goi thang cac ham
o day — tach rieng khoi ADK de test scope-filter ma khong can mock gi ca.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    unrestricted: bool
    states: frozenset[str]


def _scope_where(scope: Scope, alias: str = "") -> tuple[str, list]:
    col = f"{alias}.state" if alias else "state"
    if scope.unrestricted:
        return "", []
    if not scope.states:
        return "1 = 0", []
    return f"{col} = ANY(%s)", [sorted(scope.states)]


def _current_run_id(cur) -> str | None:
    cur.execute("SELECT qc_run_id, last_run_id FROM sync_state WHERE id = 1")
    st = cur.fetchone()
    return st and (st["qc_run_id"] or st["last_run_id"])


def list_qc_exceptions(cur, scope: Scope, severity: str | None = None,
                       rule_id: str | None = None, year: int | None = None,
                       limit: int = 50) -> list[dict]:
    """Vi pham QC cua lan nap hien tai, trong pham vi cua nguoi hoi."""
    target = _current_run_id(cur)
    if not target:
        return []

    where = ["run_id = %s"]
    params: list = [target]
    scope_sql, scope_params = _scope_where(scope)
    if scope_sql:
        where.append(scope_sql); params += scope_params
    if severity:
        where.append("severity = %s"); params.append(severity)
    if rule_id:
        where.append("rule_id = %s"); params.append(rule_id)
    if year:
        where.append("year = %s"); params.append(year)

    cur.execute(
        f"""SELECT id, run_id, rule_id, severity, year, state, institution_id, institution,
                   message, observed
            FROM qc_exception WHERE {' AND '.join(where)}
            ORDER BY severity, id LIMIT %s""",
        [*params, limit])
    return cur.fetchall()


def summarize_qc_exceptions(cur, scope: Scope) -> dict:
    """Dem vi pham theo rule_id + severity cua lan nap hien tai, trong pham vi.

    Dung khi agent tra loi 'tinh hinh chung sao roi' ma khong can liet ke
    tung dong — re hon nhieu ve token so voi doc toan bo danh sach.
    """
    target = _current_run_id(cur)
    if not target:
        return {"run_id": None, "total": 0, "by_rule": []}

    where = ["run_id = %s"]
    params: list = [target]
    scope_sql, scope_params = _scope_where(scope)
    if scope_sql:
        where.append(scope_sql); params += scope_params

    cur.execute(
        f"""SELECT rule_id, severity, count(*) AS n FROM qc_exception
            WHERE {' AND '.join(where)} GROUP BY rule_id, severity ORDER BY n DESC""",
        params)
    by_rule = cur.fetchall()
    return {"run_id": target, "total": sum(r["n"] for r in by_rule), "by_rule": by_rule}


def list_open_tickets(cur, scope: Scope, state: str | None = None, limit: int = 50) -> list[dict]:
    """Ticket dang mo (open/awaiting_verify), trong pham vi — kem bang chung."""
    where = ["status IN ('open','awaiting_verify')"]
    params: list = []
    scope_sql, scope_params = _scope_where(scope)
    if scope_sql:
        where.append(scope_sql); params += scope_params
    if state:
        where.append("state = %s"); params.append(state.upper())

    cur.execute(
        f"""SELECT id, year, state, institution_id, institution, title, expected_value,
                   observed_at_open, last_observed, blocking, status, evidence, from_rule_id
            FROM ticket WHERE {' AND '.join(where)}
            ORDER BY blocking DESC, id LIMIT %s""",
        [*params, limit])
    return cur.fetchall()
