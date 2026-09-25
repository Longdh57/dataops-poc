"""Truy van thuan cho AI Agent — khong dinh ADK, goi truc tiep va test duoc.

`Scope` la lat cat toi thieu cua authz.Principal can cho lop nay:
unrestricted + tap bang. `tools.py` doc no tu session state (server gan luc
mo session, KHONG BAO GIO tu tham so LLM truyen vao) roi goi thang cac ham
o day — tach rieng khoi ADK de test scope-filter ma khong can mock gi ca.
"""

from dataclasses import dataclass

# The model sometimes passes a full state name ("Texas") instead of the
# 2-letter code the fact_current.state column actually holds ("TX") despite
# being told otherwise — get_fact sidesteps this by handing the model the
# real distinct codes on every call (see sql_gen._reference_values), but
# deposit_trend/rank_deposits take `state` as a plain arg, so normalize
# defensively here instead of trusting prompt compliance alone.
_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR", "guam": "GU", "american samoa": "AS",
    "virgin islands": "VI", "northern mariana islands": "MP",
}


def _state_code(state: str) -> str:
    """Accepts either a 2-letter code or a full state name, always
    case-insensitively, and returns the 2-letter code fact_current uses."""
    s = state.strip()
    return _STATE_NAME_TO_CODE.get(s.lower(), s.upper())


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


def deposit_trend(cur, scope: Scope, institution: str | None = None, state: str | None = None,
                   year_from: int | None = None, year_to: int | None = None) -> dict:
    """Year-by-year SUM(deposit) for the given filter, aggregated IN SQL —
    not estimated from a truncated row sample. Fixes two failure modes seen
    in get_fact: (1) an institution name matching several institution_ids
    (e.g. "Wells Fargo Bank" vs "Wells Fargo Bank South Central") got
    conflated into one arbitrary min/max instead of a real per-year total;
    (2) a filter matching >50 rows (a national bank across ~40 states, or an
    entire state) got silently cut off by get_fact's LIMIT 50, understating
    the true total with no reliable signal to the model that it was cut.

    average/highest/lowest/above-below-average/largest-increase are computed
    here in Python over the (small, one-row-per-year) aggregated result, not
    left to the model to eyeball from raw rows — deterministic and reusable
    across a follow-up question in the same session.
    """
    where = []
    params: list = []
    scope_sql, scope_params = _scope_where(scope)
    if scope_sql:
        where.append(scope_sql); params += scope_params
    if institution:
        where.append("institution ILIKE %s"); params.append(f"%{institution}%")
    if state:
        where.append("state = %s"); params.append(_state_code(state))
    if year_from:
        where.append("year >= %s"); params.append(year_from)
    if year_to:
        where.append("year <= %s"); params.append(year_to)
    where_sql = " AND ".join(where) if where else "TRUE"

    cur.execute(
        f"""WITH agg AS (
                SELECT year, SUM(deposit) AS total_deposit,
                       COUNT(DISTINCT institution_id) AS institution_count
                FROM fact_current WHERE {where_sql} GROUP BY year
            )
            SELECT year, total_deposit, institution_count,
                   LAG(total_deposit) OVER (ORDER BY year) AS prev_total_deposit
            FROM agg ORDER BY year""", params)
    rows = cur.fetchall()
    if not rows:
        return {"years": [], "message": "no matching data for this institution/state/year range"}

    # SUM(bigint) comes back from Postgres as numeric -> psycopg gives
    # decimal.Decimal, which doesn't mix with a plain float in arithmetic
    # below (and isn't the JSON number a caller expects either).
    for r in rows:
        r["total_deposit"] = float(r["total_deposit"])
        prev = float(r["prev_total_deposit"]) if r["prev_total_deposit"] is not None else None
        r["yoy_growth_pct"] = round(100.0 * (r["total_deposit"] - prev) / prev, 2) if prev else None
        del r["prev_total_deposit"]

    totals = [r["total_deposit"] for r in rows]
    avg = sum(totals) / len(totals)
    growth_rows = [r for r in rows if r["yoy_growth_pct"] is not None]

    return {
        "institution_filter": institution,
        "state_filter": state,
        "years": rows,
        "average_deposit": round(avg, 2),
        "highest_year": max(rows, key=lambda r: r["total_deposit"])["year"],
        "lowest_year": min(rows, key=lambda r: r["total_deposit"])["year"],
        "above_average_years": [r["year"] for r in rows if r["total_deposit"] > avg],
        "below_average_years": [r["year"] for r in rows if r["total_deposit"] <= avg],
        "largest_increase_year": (max(growth_rows, key=lambda r: r["yoy_growth_pct"])["year"]
                                   if growth_rows else None),
        "largest_decrease_year": (min(growth_rows, key=lambda r: r["yoy_growth_pct"])["year"]
                                   if growth_rows else None),
    }


_RANK_GROUP_COLUMNS = {
    "institution": "institution_id, institution, state",
    "state": "state",
}


def rank_deposits(cur, scope: Scope, year: int, state: str | None = None,
                   group_by: str = "institution", direction: str = "top",
                   limit: int = 15) -> dict:
    """Single-year ranking across many institutions/states — the shape
    get_fact could never answer (it has no GROUP BY/aggregate ability, and
    LIMIT 50 arrives before any ranking can happen). `group_by` and
    `direction` are constrained to a fixed Python allowlist below, never
    interpolated from free text, so this stays just as injection-safe as a
    fully parameterized query despite building the SQL dynamically.
    """
    if group_by not in _RANK_GROUP_COLUMNS:
        raise ValueError(f"group_by must be one of {list(_RANK_GROUP_COLUMNS)}")
    if direction not in ("top", "bottom", "above_average", "below_average"):
        raise ValueError("direction must be one of top/bottom/above_average/below_average")

    where = ["year = %s"]
    params: list = [year]
    scope_sql, scope_params = _scope_where(scope)
    if scope_sql:
        where.append(scope_sql); params += scope_params
    if state and group_by == "institution":
        where.append("state = %s"); params.append(_state_code(state))
    where_sql = " AND ".join(where)
    group_cols = _RANK_GROUP_COLUMNS[group_by]

    cur.execute(
        f"""WITH pool AS (
                SELECT {group_cols}, SUM(deposit) AS deposit
                FROM fact_current WHERE {where_sql} GROUP BY {group_cols}
            )
            SELECT *, AVG(deposit) OVER () AS avg_deposit FROM pool""", params)
    rows = cur.fetchall()
    if not rows:
        return {"year": year, "rows": [], "message": "no matching data for this year/state"}

    # SUM/AVG(bigint) come back as numeric -> decimal.Decimal; normalize to
    # float so comparisons/sorting/JSON output behave like plain numbers.
    for r in rows:
        r["deposit"] = float(r["deposit"])
        r["avg_deposit"] = float(r["avg_deposit"])
    avg_deposit = rows[0]["avg_deposit"]
    if direction == "above_average":
        rows = [r for r in rows if r["deposit"] > avg_deposit]
        rows.sort(key=lambda r: r["deposit"], reverse=True)
    elif direction == "below_average":
        rows = [r for r in rows if r["deposit"] <= avg_deposit]
        rows.sort(key=lambda r: r["deposit"])
    elif direction == "bottom":
        rows.sort(key=lambda r: r["deposit"])
    else:  # top
        rows.sort(key=lambda r: r["deposit"], reverse=True)

    return {"year": year, "group_by": group_by, "direction": direction,
            "overall_average_deposit": round(avg_deposit, 2), "rows": rows[:limit]}


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
