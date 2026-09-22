"""NL -> SQL for get_fact: the model only generates a SINGLE WHERE condition,
not a full statement — see the Context section in the approved plan for why.

Four checks run before a condition is allowed to execute (`_validate_where`):
  1. Balanced parens () and balanced single quotes ' — this specifically
     closes the "1=1) OR (..." hole, which would break out of the wrapping
     group our own code builds and AND the scope condition onto the wrong
     branch (AND binds tighter than OR).
  2. No ';', '--', '/*' — no statement stacking, no comment tricks.
  3. No "function calls": a word immediately before "(" that isn't
     AND/OR/NOT/IN is treated as a function call and blocked (pg_sleep(),
     count(), etc.). Normal grouping parens after AND/OR/NOT/IN are fine.
  4. A blocklist of forbidden keywords (SELECT/INSERT/.../pg_*/
     information_schema).

A condition that passes all four is STILL always ANDed with the scope
condition at the SQL level (via `_scope_where` — the same helper every
other query in queries.py uses), then filtered again in Python after
reading — two layers of defense, neither one sufficient alone.
"""

from __future__ import annotations

import re

from fastapi import HTTPException
from google import genai
from google.genai import types

from ..settings import settings
from .queries import Scope, _scope_where

MAX_ATTEMPTS = 3
STATEMENT_TIMEOUT_MS = 3000

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(select|insert|update|delete|drop|alter|truncate|create|grant|revoke|"
    r"copy|call|execute|merge|union|pg_\w*|information_schema)\b",
    re.IGNORECASE,
)
# A word immediately before "(" that is NOT AND/OR/NOT/IN is treated as a
# function call (pg_sleep(...), count(...), etc.) and blocked. Normal
# grouping parens after AND/OR/NOT/IN (e.g. "... AND (year = 2025 OR
# year = 2026)") are fine.
_CALL_LIKE = re.compile(r"(\w+)\s*\(")
_SAFE_BEFORE_PAREN = {"and", "or", "not", "in"}

_ALLOWED_COLUMNS = (
    "year (int), state (text, 2-letter code), institution_id (int), "
    "institution (text — INSTITUTION NAME, casing is NOT stable across "
    "years so ALWAYS use ILIKE '%...%' to filter, never '='), deposit "
    "(bigint, in thousands of USD), deposit_share (float, 0..1), "
    "prev_deposit (bigint), prev_year (int)"
)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True, project=settings.gcp_project_id, location=settings.region)
    return _client


def _reference_values(cur) -> dict:
    """Real values currently in fact_current — queried live on every call,
    never cached/written to a file, so it can never go stale after a sync."""
    cur.execute("SELECT DISTINCT state FROM fact_current ORDER BY state")
    states = [r["state"] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT year FROM fact_current ORDER BY year")
    years = [r["year"] for r in cur.fetchall()]
    return {"states": states, "years": years}


def _parens_valid(fragment: str) -> bool:
    """Counting totals is NOT enough — "1=1) OR (state='CA'" has exactly 1
    "(" and 1 ")", but the close comes BEFORE the open: it breaks out of
    the wrapping group our own code builds, ANDing the scope condition onto
    the wrong branch. Must track real depth, reject as soon as depth goes
    negative."""
    depth = 0
    for ch in fragment:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _validate_where(fragment: str) -> str | None:
    """Returns an error message if the condition isn't safe, None if it passes."""
    if not fragment or not fragment.strip():
        return "empty condition"
    if not _parens_valid(fragment):
        return "parentheses () are unbalanced or out of order"
    if fragment.count("'") % 2 != 0:
        return "single quotes ' are unbalanced"
    if ";" in fragment or "--" in fragment or "/*" in fragment:
        return "must not contain ';', '--', or '/*'"
    for m in _CALL_LIKE.finditer(fragment):
        if m.group(1).lower() not in _SAFE_BEFORE_PAREN:
            return "function calls are not allowed (use simple comparison/logical operators only)"
    if _FORBIDDEN_KEYWORDS.search(fragment):
        return "contains a disallowed keyword (this must be a filter condition, not a statement)"
    return None


def _generate_where(question: str, reference: dict, prior_error: str | None) -> str:
    retry_note = (
        f"\n\nThe previous attempt was rejected because: {prior_error}. Fix it."
        if prior_error else ""
    )
    prompt = f"""Translate the following question into a SINGLE filter condition (WHERE) on the fact_current table.

Columns you can use: {_ALLOWED_COLUMNS}

States currently in the table: {reference['states']}
Years currently in the table: {reference['years']}

Return ONLY the condition expression — NO 'WHERE' keyword, NO 'SELECT', NO
semicolon, NO explanation, NO markdown/code fence. Example of the expected
format:
  state = 'TX' AND deposit > 100000
  institution ILIKE '%wells fargo%' AND year = 2026
{retry_note}

Question: {question}"""

    resp = _get_client().models.generate_content(
        model=settings.agent_model,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )
    text = (resp.text or "").strip()
    # Guard against the model wrapping the answer in a markdown code fence
    # despite being told not to:
    text = re.sub(r"^```(sql)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    return text.rstrip(";").strip()


def query_fact_natural_language(cur, scope: Scope, question: str, limit: int = 50) -> dict:
    """Generate a WHERE condition from a natural-language question, retrying
    up to MAX_ATTEMPTS times — the previous error (from the validator or
    from Postgres itself) is fed back into the next generation so the model
    can self-correct. Returns a clear error instead of making up data once
    attempts are exhausted.
    """
    reference = _reference_values(cur)
    scope_sql, scope_params = _scope_where(scope)

    last_error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            fragment = _generate_where(question, reference, last_error)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"could not call Vertex AI to generate SQL: {exc}") from exc

        problem = _validate_where(fragment)
        if problem:
            last_error = f"condition '{fragment}' was rejected: {problem}"
            continue

        # psycopg reads the whole SQL string as a %-format template whenever
        # params are passed, so a literal % in the condition (required for
        # ILIKE '%...%') must be doubled to %% so it isn't mistaken for a
        # placeholder — skipping this causes "only %s/%b/%t are allowed".
        where_clause = f"({fragment.replace('%', '%%')})"
        params = []
        if scope_sql:
            where_clause += f" AND {scope_sql}"
            params = list(scope_params)

        sql = (
            "SELECT year, state, institution_id, institution, deposit, deposit_share, "
            f"prev_deposit, prev_year FROM fact_current WHERE {where_clause} LIMIT %s"
        )
        try:
            cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute(sql, [*params, limit])
            rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            # Postgres aborts the whole transaction after one error — without
            # a rollback, the next attempt on the SAME connection fails in a
            # cascade with "current transaction is aborted", hiding the
            # fragment's real error.
            cur.connection.rollback()
            continue

        # Filtered again in Python — extra defense, even though the scope
        # condition is already ANDed in at the SQL level.
        if not scope.unrestricted:
            rows = [r for r in rows if r["state"] in scope.states]
        return {"sql_where": fragment, "rows": rows[:limit], "attempts": attempt}

    return {
        "error": "cannot_query",
        "message": f"Could not query the raw data after {MAX_ATTEMPTS} attempts.",
        "last_error": last_error,
    }
