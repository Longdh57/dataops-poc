"""AI Agent (Google ADK) — doc Issue Log + ticket, khong quyet dinh.

Xem docs/quy-trinh-chat-luong.md va root_agent.SYSTEM_PROMPT cho gioi han
day du. `service.chat()` la diem vao duy nhat tu apps/api/app/main.py.
`usage.month_usage()` la so token/chi phi Vertex AI ca thang doc tu Cloud
Monitoring, con `token_log.session_usage()` la so cua RIENG mot phien chat
doc tu `usageMetadata` ma Vertex AI tra ve — hai nguon khac nhau, xem
docstring cua tung module.
"""

from .service import chat
from .token_log import session_usage
from .usage import month_usage

__all__ = ["chat", "month_usage", "session_usage"]
