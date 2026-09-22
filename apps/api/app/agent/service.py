"""Vong doi Runner/Session cua AI Agent.

Runner va SessionService duoc tao MOT LAN luc import module — ADK khuyen
nghi khong tao lai moi request (Runner khong giu state, SessionService moi
la noi giu). Phien luu tren chinh Postgres cua ung dung
(DatabaseSessionService), nen song qua nhieu request/instance va khong mat
khi Cloud Run scale-to-zero — khac han InMemorySessionService.
"""

import os

from fastapi import HTTPException
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from ..authz import Principal
from ..settings import settings
from .root_agent import root_agent

APP_NAME = "dataops_qc_agent"

# ADK doc ba bien nay truc tiep tu os.environ de chon Vertex AI thay vi
# Gemini Developer API — khong co API key nao ca, dung ADC nhu phan con lai
# cua ung dung (xem roles/aiplatform.user o infra/modules/iam/main.tf).
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.gcp_project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.region)

# DATABASE_URL dang o dang "postgresql://" (dung cho psycopg dong bo o moi
# cho khac trong app) — ADK can dialect bat dong bo, va psycopg3 da ho tro
# san qua "postgresql+psycopg://", khong can them driver moi.
_db_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
_session_service = DatabaseSessionService(db_url=_db_url)
_runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=_session_service)


async def chat(p: Principal, message: str, session_id: str | None) -> tuple[str, str]:
    """Hoi AI Agent, tra ve (cau tra loi, session_id).

    `scope_states`/`unrestricted` gan vao STATE CUA SESSION luc mo — tool
    trong tools.py doc lai tu day, LLM khong bao gio thay hay doi duoc.
    Truyen `session_id` cu de noi tiep hoi thoai; sai chu hoac cua nguoi
    khac thi lang le mo phien moi thay vi loi (get_session da tu loc theo
    dung user_id).
    """
    try:
        session = None
        if session_id:
            session = await _session_service.get_session(
                app_name=APP_NAME, user_id=p.email, session_id=session_id)
        if session is None:
            session = await _session_service.create_session(
                app_name=APP_NAME, user_id=p.email,
                state={"scope_states": sorted(p.scope_states), "unrestricted": p.unrestricted})

        content = types.Content(role="user", parts=[types.Part(text=message)])
        reply = ""
        async for event in _runner.run_async(
                user_id=p.email, session_id=session.id, new_message=content):
            if event.is_final_response() and event.content and event.content.parts:
                reply = event.content.parts[0].text or ""
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"khong goi duoc AI Agent: {exc}") from exc

    if not reply:
        raise HTTPException(502, "AI Agent tra ve phan hoi rong")
    return reply, session.id
