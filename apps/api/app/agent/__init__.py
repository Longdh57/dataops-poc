"""AI Agent (Google ADK) — doc Issue Log + ticket, khong quyet dinh.

Xem docs/quy-trinh-chat-luong.md va root_agent.SYSTEM_PROMPT cho gioi han
day du. `service.chat()` la diem vao duy nhat tu apps/api/app/main.py, con
`usage.month_usage()` la so token/chi phi Vertex AI thang nay.
"""

from .service import chat
from .usage import month_usage

__all__ = ["chat", "month_usage"]
