"use client";

// AI Agent — doc vi pham QC (qc_exception) + ticket dang mo qua Gemini/
// Vertex AI, trong PHAM VI cua nguoi hoi. No la lop DOC THEM tren
// Deterministic QC Engine, khong thay the: khong dong ticket, khong ky
// ban, khong sua so — ba viec do van chi lam duoc qua co che da co. Xem
// gioi han day du o SYSTEM_PROMPT trong apps/api/app/agent.py.

import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { post } from "@/app/lib/api";
import { ErrBox } from "@/app/ui/bits";

type Turn = { role: "user" | "agent"; text: string };

type ChatResponse = {
  reply: string;
  run_id: string | null;
  violation_count: number;
  ticket_count: number;
};

const GOI_Y = [
  "Tình hình QC hôm nay sao rồi?",
  "Tôi nên xử lý cái gì trước?",
  "Có ticket nào đang chặn phát hành không?",
];

export default function AgentPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const m = useMutation({
    mutationFn: (message: string) =>
      post<ChatResponse>("/agent/chat", { message, history: turns.slice(-10) }),
    onSuccess: (res, message) => {
      setTurns((t) => [...t, { role: "user", text: message }, { role: "agent", text: res.reply }]);
      setInput("");
      queueMicrotask(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
    },
  });

  function send(text: string) {
    const q = text.trim();
    if (!q || m.isPending) return;
    m.mutate(q);
  }

  return (
    <>
      <div className="card-head">
        <div>
          <h1>AI Agent — hỏi về vi phạm &amp; ticket</h1>
          <p className="sub">
            Agent chỉ đọc dữ liệu QC đang có trong phạm vi của bạn và trả lời có căn cứ — nó không
            đóng ticket, không ký bản, không sửa số. Quyết định cuối luôn là của con người.
          </p>
        </div>
      </div>

      <div
        className="card card-pad0"
        style={{ display: "flex", flexDirection: "column", height: "62vh" }}
      >
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: 14,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          {turns.length === 0 ? (
            <div>
              <p className="tone-muted" style={{ marginBottom: 8 }}>
                Thử hỏi:
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {GOI_Y.map((g) => (
                  <button key={g} className="btn btn-sm" onClick={() => send(g)}>
                    {g}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {turns.map((t, i) => (
            <div
              key={i}
              style={{
                alignSelf: t.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "78%",
                background: t.role === "user" ? "var(--accent-soft)" : "var(--surface2)",
                color: "var(--ink)",
                borderRadius: 10,
                padding: "8px 12px",
                whiteSpace: "pre-wrap",
                fontSize: 13.5,
              }}
            >
              {t.text}
            </div>
          ))}

          {m.isPending ? <p className="spin">Agent đang đọc dữ liệu…</p> : null}
          <div ref={bottomRef} />
        </div>

        <div style={{ padding: "0 14px" }}>
          <ErrBox error={m.error} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          style={{
            display: "flex",
            gap: 8,
            padding: 12,
            borderTop: "1px solid var(--line-soft)",
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Hỏi về vi phạm, ticket, ưu tiên xử lý…"
            style={{ flex: 1 }}
          />
          <button className="btn btn-primary" disabled={m.isPending || !input.trim()}>
            Gửi
          </button>
        </form>
      </div>
    </>
  );
}
