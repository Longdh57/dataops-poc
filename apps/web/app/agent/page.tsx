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

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { post } from "@/app/lib/api";
import {
  AGENT_SESSION_USAGE_KEY, useAgentSessionUsage, useAgentUsage, useMe, useRefreshAgentUsage,
} from "@/app/lib/queries";
import type { TokenByModel } from "@/app/lib/types";
import { ErrBox, Modal } from "@/app/ui/bits";

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

/** Duoi mot xu thi `toFixed(2)` lam tron thanh "$0.00" trong khi van co
 *  phat sinh — noi "<$0.01" that hon. */
function fmtCost(usd: number): string {
  return usd > 0 && usd < 0.01 ? "<$0.01" : `$${usd.toFixed(2)}`;
}

/** Bang token tach theo model + dong tong. Dung chung cho ca so cua phien
 *  chat lan so ca thang — hai khoi phai doc giong het nhau, khac moi nguon
 *  du lieu. */
function TokenTable({
  rows, input, output, cost,
}: {
  rows: TokenByModel[];
  input: number;
  output: number;
  cost: number;
}) {
  const { t } = useI18n();
  const { num } = useFmt();

  return (
    <table className="t">
      <thead>
        <tr>
          <th>{t("agent.usage.col.model")}</th>
          <th className="num">{t("agent.usage.col.input")}</th>
          <th className="num">{t("agent.usage.col.output")}</th>
          <th className="num">{t("agent.usage.col.cost")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.model}>
            <td className="mono">{r.model}</td>
            <td className="num">{num(r.input_tokens)}</td>
            <td className="num">{num(r.output_tokens)}</td>
            {/* cost_usd = null: model chua co trong bang gia. Hien dau gach
                chu KHONG hien $0.00 — $0.00 la noi doi. */}
            <td className="num">{r.cost_usd === null ? "—" : fmtCost(r.cost_usd)}</td>
          </tr>
        ))}
        <tr>
          <td><b>{t("agent.usage.total")}</b></td>
          <td className="num"><b>{num(input)}</b></td>
          <td className="num"><b>{num(output)}</b></td>
          <td className="num"><b>{fmtCost(cost)}</b></td>
        </tr>
      </tbody>
    </table>
  );
}

/** O token cua PHIEN CHAT dang mo — bam vao de mo bang chi tiet.
 *
 *  Truoc day o nay hien so ca thang doc tu Cloud Monitoring; so do tre 1-2
 *  phut va la cua ca project, nen hoi xong nhin vao khong thay gi doi.
 *  Gio o nay dem dung cuoc tro chuyen truoc mat, lay tu `usageMetadata`
 *  ung dung tu ghi — doi ngay sau moi cau hoi. So ca thang van con, nhung
 *  lui vao trong modal.
 *
 *  KHONG bien mat khi thieu quyen monitoring: so cua phien khong phu thuoc
 *  quyen do, ai chat cung thay duoc phan minh vua ton. */
function UsagePill({ sessionId }: { sessionId: string | null }) {
  const { t } = useI18n();
  const { num } = useFmt();
  const { data } = useAgentSessionUsage(sessionId);
  const [open, setOpen] = useState(false);

  return (
    <>
      <button className="pill" title={t("agent.usage.open")} onClick={() => setOpen(true)}>
        {t("agent.usage.pill", {
          tokens: num(data?.total_tokens ?? 0),
          cost: fmtCost(data?.cost_usd ?? 0),
        })}
      </button>
      {open ? <UsageModal sessionId={sessionId} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

/** Chi tiet token: khoi tren la phien chat dang mo, khoi duoi la ca project
 *  thang nay. Hai khoi doc hai NGUON khac nhau va phai noi ro dieu do:
 *
 *  - Phien: bang agent_token_usage cua chinh ung dung, ghi tu `usageMetadata`
 *    trong response Vertex AI. Co ngay sau moi luot chat.
 *  - Thang: metric Cloud Monitoring, tre 1-2 phut va gop moi lenh goi Vertex
 *    AI trong project. Khoi nay im lang vang mat voi vai tro khong doc duoc
 *    (analyst nhan 403) — luc do modal chi con khoi phien.
 *
 *  Mo hop khong ban them request nao: ca hai dung lai query cua pill. */
function UsageModal({ sessionId, onClose }: { sessionId: string | null; onClose: () => void }) {
  const { t } = useI18n();
  const { dt } = useFmt();
  const session = useAgentSessionUsage(sessionId);
  const monthQuery = useAgentUsage();
  const refresh = useRefreshAgentUsage();

  // Loi (403 vi vai tro, hay API chet) thi GIAU han khoi thang, khong dung
  // `data` con lai trong cache: doi danh tinh tu admin sang analyst ma van
  // ve so cu la hien nham so cua nguoi truoc.
  const month = monthQuery.isError ? undefined : monthQuery.data;

  // Mot nut lam moi CA HAI khoi — nguoi dung khong can biet so nao den tu
  // nguon nao moi bam dung cho.
  const busy = refresh.isPending || session.isFetching;
  const refreshAll = () => {
    void session.refetch();
    if (month) refresh.mutate();
  };

  return (
    <Modal title={t("agent.usage.modal.title")} onClose={onClose}>
      <h3 className="modal-sec" style={{ marginTop: 0 }}>{t("agent.usage.session.title")}</h3>
      {session.data && session.data.by_model.length ? (
        <>
          <TokenTable
            rows={session.data.by_model}
            input={session.data.input_tokens}
            output={session.data.output_tokens}
            cost={session.data.cost_usd}
          />
          {session.data.unpriced_models.length ? (
            <p className="hint tone-warn">
              {t("agent.usage.unpriced", { models: session.data.unpriced_models.join(", ") })}
            </p>
          ) : null}
          <p className="hint">{t("agent.usage.session.fresh")}</p>
        </>
      ) : (
        <p className="sub">{t("agent.usage.session.none")}</p>
      )}

      {month ? (
        <>
          <h3 className="modal-sec">{t("agent.usage.month.title")}</h3>
          {month.available ? (
            <>
              <p className="sub" style={{ marginBottom: 10 }}>
                {t("agent.usage.modal.period", {
                  from: month.period_start.slice(0, 10),
                  asOf: dt(month.as_of),
                })}
              </p>
              {month.by_model.length ? (
                <TokenTable
                  rows={month.by_model}
                  input={month.input_tokens}
                  output={month.output_tokens}
                  cost={month.cost_usd}
                />
              ) : (
                <p className="sub">{t("agent.usage.empty")}</p>
              )}
              {month.unpriced_models.length ? (
                <p className="hint tone-warn">
                  {t("agent.usage.unpriced", { models: month.unpriced_models.join(", ") })}
                </p>
              ) : null}
              <p className="hint">{t("agent.usage.delay")}</p>
              <p className="hint">{t("agent.usage.scope")}</p>
            </>
          ) : (
            <p className="sub">{t("agent.usage.unavailable", { reason: month.reason })}</p>
          )}
        </>
      ) : null}

      <ErrBox error={refresh.error} />
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
        <button className="btn" disabled={busy} onClick={refreshAll}>
          {busy ? t("agent.usage.refreshing") : t("agent.usage.refresh")}
        </button>
        <button className="btn btn-primary" onClick={onClose}>{t("common.close")}</button>
      </div>
    </Modal>
  );
}

export default function AgentPage() {
  const { t } = useI18n();
  const { data: me } = useMe();
  const qc = useQueryClient();
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
      // Token cua luot vua roi da nam trong DB truoc khi response nay ve,
      // nen doc lai la ra so dung ngay — day la khac biet lon nhat so voi
      // so ca thang (Cloud Monitoring con tre 1-2 phut).
      qc.invalidateQueries({ queryKey: AGENT_SESSION_USAGE_KEY });
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
          <UsagePill sessionId={sessionId} />
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
