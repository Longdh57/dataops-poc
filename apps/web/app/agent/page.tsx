"use client";

// AI Agent — doc vi pham QC (qc_exception) + ticket dang mo qua Gemini/
// Vertex AI, trong PHAM VI cua nguoi hoi. No la lop DOC THEM tren
// Deterministic QC Engine, khong thay the: khong dong ticket, khong ky
// ban, khong sua so — ba viec do van chi lam duoc qua co che da co. Xem
// gioi han day du o SYSTEM_PROMPT trong apps/api/app/agent.py.
//
// Luu y: giao dien doi duoc ngon ngu, con cau tra loi cua agent thi do
// SYSTEM_PROMPT ben API quyet dinh — no van tra loi bang tieng Viet cho
// toi khi phia API nhan them tham so ngon ngu.

import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { post } from "@/app/lib/api";
import { ErrBox } from "@/app/ui/bits";

type Turn = { role: "user" | "agent"; text: string };

type ChatResponse = {
  reply: string;
  run_id: string | null;
  violation_count: number;
  ticket_count: number;
};

const GOI_Y: MessageKey[] = ["agent.suggest1", "agent.suggest2", "agent.suggest3"];

export default function AgentPage() {
  const { t } = useI18n();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const m = useMutation({
    mutationFn: (message: string) =>
      post<ChatResponse>("/agent/chat", { message, history: turns.slice(-10) }),
    onSuccess: (res, message) => {
      setTurns((prev) => [
        ...prev,
        { role: "user", text: message },
        { role: "agent", text: res.reply },
      ]);
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
          <h1>{t("agent.title")}</h1>
          <p className="sub">{t("agent.sub")}</p>
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
                {t("agent.try")}
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {GOI_Y.map((key) => (
                  <button key={key} className="btn btn-sm" onClick={() => send(t(key))}>
                    {t(key)}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {turns.map((turn, i) => (
            <div
              key={i}
              style={{
                alignSelf: turn.role === "user" ? "flex-end" : "flex-start",
                maxWidth: "78%",
                background: turn.role === "user" ? "var(--accent-soft)" : "var(--surface2)",
                color: "var(--ink)",
                borderRadius: 10,
                padding: "8px 12px",
                whiteSpace: "pre-wrap",
                fontSize: 13.5,
              }}
            >
              {turn.text}
            </div>
          ))}

          {m.isPending ? <p className="spin">{t("agent.thinking")}</p> : null}
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
            placeholder={t("agent.placeholder")}
            style={{ flex: 1 }}
          />
          <button className="btn btn-primary" disabled={m.isPending || !input.trim()}>
            {t("agent.send")}
          </button>
        </form>
      </div>
    </>
  );
}
