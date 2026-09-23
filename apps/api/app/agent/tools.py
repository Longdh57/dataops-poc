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
