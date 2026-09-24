"use client";

// AI Agent — Google ADK, doc vi pham QC (qc_exception) + ticket dang mo qua
// 4 tool (chi doc), trong PHAM VI cua nguoi hoi. No la lop DOC THEM tren
// Deterministic QC Engine, khong thay the: khong dong ticket, khong ky
// ban, khong sua so — ba viec do van chi lam duoc qua co che da co. Xem
// gioi han day du o SYSTEM_PROMPT trong apps/api/app/agent/root_agent.py.
//
// Hoi thoai duoc nho boi SERVER (DatabaseSessionService tren Postgres) qua
// `session_id` — khong con gui lai toan bo lich su moi lan hoi nhu truoc.
//
// Rieng MAN HINH (danh sach bong chat hien thi + session_id dang dung) chi
// nam trong state cua component, nen chuyen tab roi quay lai se mat —
// component unmount/mount lai, con hoi thoai that tren server thi van con
// nguyen. Luu ban hien thi vao localStorage, khoa THEO TUNG DANH TINH, de
// (a) chuyen tab/tai lai trang van thay hoi thoai cu, va (b) doi danh tinh
// trong cung trinh duyet KHONG lam lo hoi thoai cua nguoi truoc.

import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { post } from "@/app/lib/api";
import { useAgentUsage, useMe } from "@/app/lib/queries";
import { ErrBox } from "@/app/ui/bits";

type Turn = { role: "user" | "agent"; text: string };

type ChatResponse = {
  reply: string;
  session_id: string;
};

type Saved = { turns: Turn[]; sessionId: string | null };

const GOI_Y: MessageKey[] = ["agent.suggest1", "agent.suggest2", "agent.suggest3"];

function storageKey(email: string | undefined): string | null {
  return email ? `dataops.agent.chat.${email}` : null;
}

/** O chi phi Vertex AI thang nay.
 *
 *  IM LANG BIEN MAT khi khong doc duoc — vai tro khong phai team_lead/
 *  admin (403), thieu quyen monitoring.viewer, hay chay local chua cau
 *  hinh project. Day chi la o phu: no khong duoc phep chen mot hop loi
 *  vao man hinh chat, va cang khong duoc chan viec hoi.
 *
 *  Con so la cua CA PROJECT va tien chi la uoc tinh theo gia niem yet —
 *  ca hai deu noi ro trong tooltip chu khong de nguoi doc tu suy. */
function UsagePill() {
  const { t } = useI18n();
  const { num } = useFmt();
  const { data } = useAgentUsage();

  if (!data?.available) return null;

  // Duoi mot xu thi lam tron thanh "$0.00" trong khi van co phat sinh —
  // noi "<$0.01" that hon.
  const cost =
    data.cost_usd > 0 && data.cost_usd < 0.01 ? "<$0.01" : `$${data.cost_usd.toFixed(2)}`;

  const tip = [
    t("agent.usage.tip", {
      from: data.period_start.slice(0, 10),
      input: num(data.input_tokens),
      output: num(data.output_tokens),
    }),
    data.unpriced_models.length
      ? t("agent.usage.unpriced", { models: data.unpriced_models.join(", ") })
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className="pill" title={tip} style={{ cursor: "help" }}>
      {t("agent.usage.pill", { tokens: num(data.total_tokens), cost })}
    </span>
  );
}

export default function AgentPage() {
  const { t } = useI18n();
  const { data: me } = useMe();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Nap lai hoi thoai da luu MOI KHI biet duoc dung danh tinh nao dang hoi
  // — chay lai khi doi danh tinh, va luc do phai xoa trang trong luc cho,
  // khong thi ban cu con hien tren man trong khoanh khac.
  useEffect(() => {
    setHydrated(false);
    const key = storageKey(me?.email);
    if (!key) {
      setTurns([]);
      setSessionId(null);
      setHydrated(true);
      return;
    }
    try {
      const raw = localStorage.getItem(key);
      const saved = raw ? (JSON.parse(raw) as Saved) : null;
      setTurns(saved?.turns ?? []);
      setSessionId(saved?.sessionId ?? null);
    } catch {
      // che do an danh, dung luong day, hoac JSON hong — bat dau lai tu dau.
      setTurns([]);
      setSessionId(null);
    } finally {
      setHydrated(true);
    }
  }, [me?.email]);

  // Ghi lai moi khi doi, nhung CHI sau khi da nap xong — thieu dieu kien
  // nay se co mot lan ghi mang rong luc component vua mount, de len ban da
  // luu truoc do dung 0 giay sau khi nap.
  useEffect(() => {
    const key = storageKey(me?.email);
    if (!key || !hydrated) return;
    try {
      localStorage.setItem(key, JSON.stringify({ turns, sessionId } satisfies Saved));
    } catch {
      // het dung luong hoac che do an danh — bo qua, khong lam hong UI.
    }
  }, [turns, sessionId, hydrated, me?.email]);

  const m = useMutation({
    mutationFn: (message: string) =>
      post<ChatResponse>("/agent/chat", { message, session_id: sessionId }),
    onSuccess: (res, message) => {
      setTurns((t) => [...t, { role: "user", text: message }, { role: "agent", text: res.reply }]);
      setSessionId(res.session_id);
      setInput("");
      queueMicrotask(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
    },
  });

  function send(text: string) {
    const q = text.trim();
    if (!q || m.isPending) return;
    m.mutate(q);
  }

  function newConversation() {
    setTurns([]);
    setSessionId(null);
    const key = storageKey(me?.email);
    if (key) {
      try {
        localStorage.removeItem(key);
      } catch {
        // bo qua
      }
    }
  }

  return (
    <>
      <div className="card-head">
        {/* `flex: 1 1 420px` de doan mo ta dai tu xuong dong thay vi day o
            chi phi va nut "Cuoc tro chuyen moi" xuong hang rieng — card-head
            la flex-wrap, khoi tieu de khong gioi han se chiem het mot hang. */}
        <div style={{ flex: "1 1 420px", minWidth: 0 }}>
          <h1>{t("agent.title")}</h1>
          <p className="sub">{t("agent.sub")}</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <UsagePill />
          {turns.length > 0 ? (
            <button className="btn btn-sm" onClick={newConversation}>
              {t("agent.newChat")}
            </button>
          ) : null}
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
