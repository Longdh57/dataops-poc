"""AI Agent — chi kiem tra phan API tu dieu khien duoc: pham vi va guardrail
cua endpoint. Khong goi Vertex AI that (mock `agent.ask`), vi test chay
trong CI khong co credential GCP.
"""

from conftest import ADMIN, TX, as_user

from app import main as main_module


def test_agent_chat_khong_lo_pham_vi(client, monkeypatch):
    """Ngu canh dua vao prompt phai da loc theo pham vi cua nguoi hoi —
    agent khong duoc thay du lieu ngoai bang cua no, giong het /api/exceptions
    va /api/tickets."""
    captured = {}

    def fake_ask(message, history, context):
        captured["message"] = message
        captured["context"] = context
        return "cau tra loi gia lap"

    monkeypatch.setattr(main_module.agent, "ask", fake_ask)

    res = client.post(
        "/api/agent/chat", json={"message": "tinh hinh QC sao roi?"}, headers=as_user(TX))
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "cau tra loi gia lap"

    ctx = captured["context"]
    assert ctx["pham_vi"] == ["TX"]
    for row in ctx["violation_examples"]:
        assert row["state"] == "TX"
    for row in ctx["tickets"]:
        assert row["state"] == "TX"


def test_agent_chat_bat_buoc_co_message(client):
    res = client.post("/api/agent/chat", json={"message": ""}, headers=as_user(ADMIN))
    assert res.status_code == 422


def test_agent_chat_bat_buoc_dang_nhap(client):
    res = client.post("/api/agent/chat", json={"message": "hi"})
    assert res.status_code == 401
