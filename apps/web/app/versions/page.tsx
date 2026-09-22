"use client";

// Trang phien ban: ky ban so lieu va tra loi cau hoi "so nay ho lay o dau".
//
// Cho ky khong con la mot o nhap ten va mot nut. No la cho NHIN THAY MON
// NO truoc khi dung ten: con bao nhieu vi pham luat, bao nhieu ticket chua
// dong, va cai gi da khac so voi ban ky truoc. Con no thi van ky duoc —
// QC khong co quyen phu quyet nguoi chiu trach nhiem — nhung phai viet
// phieu duyet, va phieu do di theo ban ky vinh vien.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import { gw, post } from "@/app/lib/api";
import { useGate } from "@/app/lib/queries";
import type { SignedVersion } from "@/app/lib/types";
import { ErrBox, Loading, Modal } from "@/app/ui/bits";

type Res = { rows: SignedVersion[]; can_sign: boolean };

export default function VersionsPage() {
  const { t, tn } = useI18n();
  const { dt, num } = useFmt();
  const qc = useQueryClient();
  const { data: gate } = useGate();
  const q = useQuery({ queryKey: ["versions"], queryFn: () => gw<Res>("/versions") });
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState<SignedVersion | null>(null);

  const sign = useMutation({
    mutationFn: () =>
      post<SignedVersion>("/release", { label: label.trim(), approval_note: note.trim() }),
    onSuccess: () => {
      setLabel("");
      setNote("");
      qc.invalidateQueries({ queryKey: ["versions"] });
      qc.invalidateQueries({ queryKey: ["gate"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    },
  });

  const chan = gate?.blocking_tickets ?? [];
  const stale = gate?.qc_stale ?? false;
  const locked = chan.length > 0 || stale;
  const canNo = gate?.needs_approval ?? false;
  const duNote = !canNo || note.trim().length >= 10;

  return (
    <>
      <div className="card-head">
        <div>
          <h1>{t("ver.title")}</h1>
          <p className="sub">{t("ver.sub")}</p>
        </div>
      </div>

      {q.data?.can_sign ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <h2>{t("ver.signNew")}</h2>
            {locked ? (
              <span className="pill pill-crit">
                {stale ? t("ver.pill.stale") : t("ver.pill.blocking", { n: chan.length })}
              </span>
            ) : canNo ? (
              <span className="pill pill-warn">{t("ver.pill.debt")}</span>
            ) : (
              <span className="pill pill-good">{t("ver.pill.clean")}</span>
            )}
          </div>

          {/* --- mon no, bay ra truoc khi ai do dung ten --- */}
          <Debt gate={gate} />

          {locked ? (
            <div className="banner banner-crit" style={{ marginBottom: 12, display: "block" }}>
              <div className="banner-title">
                {stale ? t("ver.blockedStaleTitle") : t("ver.blockedTicketTitle")}
              </div>
              <div className="banner-body">
                {stale ? (
                  tn("ver.blockedStaleBody", {
                    runId: <span className="mono">{gate?.run_id}</span>,
                    qcRunId: <span className="mono">{gate?.qc_run_id ?? "—"}</span>,
                  })
                ) : (
                  <>
                    {t("ver.blockedTicketBody")}
                    <ul style={{ margin: "6px 0 0 18px" }}>
                      {chan.slice(0, 8).map((ticket) => (
                        <li key={ticket.id}>
                          <span className="mono">#{ticket.id}</span> · {ticket.khoa} — {ticket.title}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </div>
          ) : null}

          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder={t("ver.labelPlaceholder")}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              style={{ flex: 1, minWidth: 260 }}
              disabled={locked}
            />
          </div>

          {canNo && !locked ? (
            <div style={{ marginTop: 10 }}>
              <label htmlFor="note" className="stat-label" style={{ display: "block", marginBottom: 4 }}>
                {t("ver.approvalLabel")}
              </label>
              <textarea
                id="note"
                rows={3}
                placeholder={t("ver.approvalPlaceholder")}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                style={{ width: "100%" }}
              />
              <p className="sub" style={{ marginTop: 4 }}>{t("ver.approvalHint")}</p>
            </div>
          ) : null}

          <div style={{ marginTop: 10 }}>
            <button
              className="btn btn-good"
              disabled={locked || label.trim().length < 3 || !duNote || sign.isPending}
              onClick={() => sign.mutate()}
            >
              {sign.isPending
                ? t("ver.signing")
                : canNo
                  ? t("ver.signWithApproval")
                  : t("ver.sign")}
            </button>
          </div>

          <div style={{ marginTop: 9 }}>
            <ErrBox error={sign.error} />
          </div>
        </div>
      ) : null}

      <div className="card card-pad0">
        {q.isPending ? (
          <div style={{ padding: 14 }}><Loading what={t("ver.loading")} /></div>
        ) : q.data?.rows.length ? (
          <table className="t">
            <thead>
              <tr>
                <th>{t("ver.col.version")}</th>
                <th>{t("ver.col.run")}</th>
                <th className="num">{t("ver.col.rows")}</th>
                <th>{t("ver.col.debt")}</th>
                <th>{t("ver.col.signedBy")}</th>
                <th>{t("ver.col.at")}</th>
                <th>{t("ver.col.sentTo")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((v) => (
                <tr key={v.id}>
                  <td style={{ color: "var(--ink)", fontWeight: 600 }}>
                    {v.label}
                    {v.checksum ? (
                      <div className="tone-muted mono" style={{ fontSize: 10.5, fontWeight: 400 }}>
                        {t("ver.fingerprint", { hash: v.checksum.slice(0, 12) })}
                      </div>
                    ) : (
                      <div className="tone-muted" style={{ fontSize: 10.5, fontWeight: 400 }}>
                        {t("ver.noFingerprint")}
                      </div>
                    )}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {v.run_id}
                    <div className="tone-muted" style={{ fontSize: 11 }}>
                      {v.source_run_ids?.length
                        ? t("ver.sourceRuns", { n: v.source_run_ids.length })
                        : t("ver.noSourceRuns")}
                      {v.rules_version ? t("ver.rulesVersion", { v: v.rules_version }) : ""}
                    </div>
                  </td>
                  <td className="num">{num(v.row_count)}</td>
                  <td style={{ fontSize: 12 }}>
                    <No version={v} />
                  </td>
                  <td>{v.signed_by}</td>
                  <td className="mono" style={{ fontSize: 11.5 }}>{dt(v.signed_at)}</td>
                  <td>
                    {v.sent?.length ? (
                      v.sent.map((s, i) => (
                        <div key={i} style={{ marginBottom: 3 }}>
                          <b style={{ color: "var(--ink)" }}>{s.customer}</b>{" "}
                          <span className="tone-muted" style={{ fontSize: 11.5 }}>
                            · {dt(s.sent_at)} · {s.sent_by}
                          </span>
                        </div>
                      ))
                    ) : (
                      <span className="tone-muted">{t("ver.notSent")}</span>
                    )}
                  </td>
                  <td>
                    <button className="btn btn-sm" onClick={() => setSending(v)}>
                      {t("ver.recordSent")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="spin" style={{ padding: 14 }}>{t("ver.empty")}</p>
        )}
      </div>

      {sending ? <SendModal version={sending} onClose={() => setSending(null)} /> : null}
    </>
  );
}

// --------------------------------------------------------- mon no truoc ky

function Debt({ gate }: { gate: ReturnType<typeof useGate>["data"] }) {
  const { t, tn } = useI18n();
  const { num } = useFmt();

  if (!gate) return null;
  const v = gate.violations;
  const truoc = gate.last_signed;

  return (
    <div style={{ marginBottom: 12 }}>
      <div className="compare" style={{ marginBottom: 10 }}>
        <div>
          <div className="stat-label">{t("ver.debt.violations")}</div>
          <div className="big">{num(v.total)}</div>
          <div className="stat-note">
            {v.by_severity.critical ? t("ver.debt.critical", { n: num(v.by_severity.critical) }) : ""}
            {v.by_severity.warning
              ? t("ver.debt.warning", { n: num(v.by_severity.warning) })
              : t("ver.debt.noWarning")}
          </div>
        </div>
        <div>
          <div className="stat-label">{t("ver.debt.openTickets")}</div>
          <div className="big">{num(gate.open_tickets)}</div>
          <div className="stat-note">
            {gate.blocking_tickets.length
              ? t("ver.debt.someBlocking", { n: gate.blocking_tickets.length })
              : t("ver.debt.noneBlocking")}
          </div>
        </div>
      </div>

      {v.by_rule.length ? (
        <table className="t" style={{ marginBottom: 8 }}>
          <tbody>
            {v.by_rule.map((r) => (
              <tr key={r.rule_id}>
                <td className="mono" style={{ fontSize: 12 }}>{r.rule_id}</td>
                <td style={{ width: 110 }}>{r.severity}</td>
                <td className="num" style={{ width: 90 }}>{num(r.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {/* Cai gi MOI so voi ban ky truoc — tinh luc hien, khong luu qua cac
          lan nap, nen cac ban ky van doc lap voi nhau. */}
      {truoc ? (
        <p className="sub">
          {tn("ver.debt.compare", { label: <b>{truoc.label}</b> })}
          {truoc.violations_fingerprint && truoc.violations_fingerprint === v.fingerprint ? (
            <>{t("ver.debt.same")}</>
          ) : truoc.violations_fingerprint ? (
            <b className="tone-crit">{t("ver.debt.different")}</b>
          ) : (
            <>{t("ver.debt.noFingerprint")}</>
          )}
        </p>
      ) : null}
    </div>
  );
}

function No({ version }: { version: SignedVersion }) {
  const { t } = useI18n();
  const { num } = useFmt();
  const vi = version.violations ?? {};
  const tk = version.open_tickets ?? [];
  const tong = Object.values(vi).reduce((a, b) => a + b, 0);

  if (!tong && !tk.length) {
    return <span className="pill pill-good">{t("ver.pill.clean")}</span>;
  }
  return (
    <>
      {tong ? (
        <div>
          <span className="pill pill-warn">{t("ver.no.violations", { n: num(tong) })}</span>{" "}
          <span className="tone-muted" style={{ fontSize: 11 }}>
            {Object.keys(vi).join(", ")}
          </span>
        </div>
      ) : null}
      {tk.length ? (
        <div style={{ marginTop: 3 }}>
          <span className="pill pill-accent">
            {t("ver.no.tickets", { list: tk.map((id) => `#${id}`).join(", ") })}
          </span>
        </div>
      ) : null}
      {version.approval_note ? (
        <div className="tone-muted" style={{ fontSize: 11, marginTop: 3, maxWidth: 320 }}>
          “{version.approval_note}”
        </div>
      ) : null}
    </>
  );
}

function SendModal({ version, onClose }: { version: SignedVersion; onClose: () => void }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [customer, setCustomer] = useState("");
  const m = useMutation({
    mutationFn: () => post(`/versions/${version.id}/sent`, { customer: customer.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["versions"] });
      onClose();
    },
  });

  return (
    <Modal title={t("ver.send.title", { label: version.label })} onClose={onClose}>
      <p className="sub" style={{ marginBottom: 10 }}>{t("ver.send.body")}</p>
      <input
        type="text"
        placeholder={t("ver.send.customer")}
        value={customer}
        onChange={(e) => setCustomer(e.target.value)}
        style={{ width: "100%", marginBottom: 10 }}
      />
      <ErrBox error={m.error} />
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
        <button className="btn" onClick={onClose}>{t("common.cancel")}</button>
        <button
          className="btn btn-primary"
          disabled={customer.trim().length < 2 || m.isPending}
          onClick={() => m.mutate()}
        >
          {t("ver.send.submit")}
        </button>
      </div>
    </Modal>
  );
}
