"""ADK tool wrappers.

All of them are SELECT-only — no tool can write or modify anything (matches
the "AI Agent is read-only" principle from docs/quy-trinh-chat-luong.md).
Scope comes from `tool_context.state`, set by the server when the session
is opened in service.py — the LLM can never pass or change this value, even
if it "pretends" to call a tool with a scope argument.
"""

from google.adk.tools import ToolContext

from ..db import db
from . import queries
from .queries import Scope
from .sql_gen import query_fact_natural_language


def _scope_from(tool_context: ToolContext) -> Scope:
    st = tool_context.state
    return Scope(
        unrestricted=bool(st.get("unrestricted")),
        states=frozenset(st.get("scope_states") or []),
    )


def list_qc_exceptions(tool_context: ToolContext, severity: str | None = None,
                       rule_id: str | None = None, year: int | None = None) -> list[dict]:
    """List QC violations (qc_exception) from the current load, within the caller's scope.

    Use this when you need details on specific violations — rule name, key
    (state/institution/year), and the observed values. Can be filtered by
    severity (critical/warning), rule_id, or year if the user specifies one.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.list_qc_exceptions(cur, scope, severity=severity, rule_id=rule_id, year=year)


def summarize_qc_exceptions(tool_context: ToolContext) -> dict:
    """Summarize QC violations from the current load by rule and severity, within scope.

    Call this first when the user asks for the "overall situation" — returns
    the total and a count per rule_id without listing every row, so it costs
    far fewer tokens than list_qc_exceptions.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.summarize_qc_exceptions(cur, scope)


def list_open_tickets(tool_context: ToolContext, state: str | None = None) -> list[dict]:
    """List open tickets (open or awaiting_verify), within scope.

    A ticket is a CONFIRMED issue backed by evidence — unlike a QC violation,
    which is just the machine's suspicion. Use this when the user needs to
    know what's currently blocking release, or asks about the evidence for
    an issue that was already reported.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.list_open_tickets(cur, scope, state=state)


def get_deposit_trend(tool_context: ToolContext, institution: str | None = None,
                       state: str | None = None, year_from: int | None = None,
                       year_to: int | None = None) -> dict:
    """Year-by-year deposit trend, aggregated exactly in SQL (SUM per year) —
    use this for ANY question about trend, average, growth rate,
    year-over-year change, "which year was highest/lowest", or "which years
    were above/below average", instead of get_fact.

    get_fact CANNOT answer these reliably: it has no aggregate/GROUP BY
    ability and caps results at 50 raw rows, so a multi-state institution or
    a whole state's data silently gets cut off, and a name matching several
    institution_ids (e.g. "Wells Fargo Bank" also matches "Wells Fargo Bank
    South Central") gets conflated instead of summed correctly per year.

    Leave `institution` empty and pass only `state` to get that state's
    total deposit trend across all institutions. Leave both empty (within
    your scope) for an overall trend. The response already includes
    average_deposit, highest_year, lowest_year, above_average_years,
    below_average_years, largest_increase_year, largest_decrease_year, and
    per-year yoy_growth_pct — read these fields directly, do not recompute
    the average or growth yourself from the raw rows.

    year_from/year_to: leave BOTH empty for a relative phrase like "the last
    5 years" or "over time" — omitting them returns every year that exists
    for this filter, which already IS "the last N years" since the table
    only holds a handful of recent years. Do NOT guess absolute years for a
    relative phrase (e.g. do not turn "last 5 years" into 2019-2023) — you
    do not reliably know the current year or which years this table holds.
    Only set year_from/year_to when the user names an explicit year or
    range themselves (e.g. "since 2024", "between 2022 and 2024").
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.deposit_trend(cur, scope, institution=institution, state=state,
                                      year_from=year_from, year_to=year_to)


def rank_deposits(tool_context: ToolContext, year: int, state: str | None = None,
                   group_by: str = "institution", direction: str = "top",
                   limit: int = 15) -> dict:
    """Rank institutions or states by total deposit IN A SINGLE YEAR —
    use this for cross-entity questions like "which banks/states have
    deposits above the overall average", "top N banks by deposit", or
    "which state had the highest total deposits". get_fact cannot answer
    these (no ranking/aggregate ability); get_deposit_trend answers a
    different shape (one entity's trend over years, not many entities
    compared in one year).

    group_by: "institution" (optionally further filtered by `state`) or
    "state" (deposits totalled per state, across all institutions).
    direction: "top" / "bottom" N by deposit, or "above_average" /
    "below_average" relative to the overall average IN THAT SAME POOL
    (already computed and returned as overall_average_deposit — do not
    recompute it). If the user doesn't name a year, use the most recent
    year you know from other tool results, or ask which year they mean.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return queries.rank_deposits(cur, scope, year=year, state=state,
                                      group_by=group_by, direction=direction, limit=limit)


def get_fact(tool_context: ToolContext, question: str) -> dict:
    """Look up raw data in fact_current using a free-form question (no exact
    key known ahead of time) — e.g. by institution name, deposit range,
    year/state, or a combination of conditions.

    Use this when the other tools aren't enough: list_qc_exceptions/
    list_open_tickets only return violations/tickets, not raw data matching
    an open-ended condition. This tool generates its own filter condition,
    retries up to 3 times (self-correcting after a failed attempt), then
    returns {"error": "cannot_query", ...} if it still can't — in that case
    you must tell the user honestly that the question could not be
    answered, and NEVER fabricate a number.
    """
    scope = _scope_from(tool_context)
    with db() as conn, conn.cursor() as cur:
        return query_fact_natural_language(cur, scope, question)
