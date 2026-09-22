"use client";

// Ticket — loi da xac nhan, giao cho team Data sua o NGUON.
//
// Khac voi trang Vi pham o mot diem quyet dinh: vi pham la nghi ngo cua
// may va chet theo tung lan nap, con ticket song xuyen qua nhieu lan nap
// cho toi khi nguon that su doi.
//
// Khong co nut "Dong ticket" o day, va do la co y. Dong la viec cua QC:
// no doc so that o lan nap ke tiep va doi chieu voi `expected_value`. Cho
// nguoi tu bam dong thi quay lai dung cho cu — trang thai noi da sua,
// du lieu thi chua.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { patch } from "@/app/lib/api";
import { useTickets } from "@/app/lib/queries";
import type { Ticket } from "@/app/lib/types";
import { ErrBox, Loading, Modal, Status } from "@/app/ui/bits";

const LOC: { v: string; label: MessageKey }[] = [
  { v: "song", label: "tk.filter.live" },
  { v: "open", label: "tk.filter.open" },
  { v: "awaiting_verify", label: "tk.filter.awaiting" },
  { v: "closed", label: "tk.filter.closed" },
  { v: "cancelled", label: "tk.filter.cancelled" },
];

export default function TicketsPage() {
  const { t, tn } = useI18n();
  const { dt } = useFmt();
  const [status, setStatus] = useState("song");
  const q = useTickets(status);
  const [acting, setActing] = useState<{ ticket: Ticket; action: string } | null>(null);

  const rows = q.data?.rows ?? [];

  return (
    <>
      <div className="card-head">
        <div>
          <h1>{t("tk.title")}</h1>
          <p className="sub">
            {tn("tk.sub", { acceptance: <b>{t("tk.subAcceptance")}</b> })}
          </p>
        </div>
        <div className="field">
          <label htmlFor="st">{t("tk.statusLabel")}</label>
          <select id="st" value={status} onChange={(e) => setStatus(e.target.value)}>
            {LOC.map((o) => (
              <option key={o.v} value={o.v}>{t(o.label)}</option>
            ))}
          </select>
        </div>
      </div>

      {q.data?.blocking_open ? (
        <div className="banner banner-crit" style={{ marginBottom: 16 }}>
          <div>
            <div className="banner-title">
              {t("tk.blockingTitle", { n: q.data.blocking_open })}
            </div>
            <div className="banner-body">{t("tk.blockingBody")}</div>
          </div>
        </div>
      ) : null}

      <ErrBox error={q.error} />

      <div className="card card-pad0">
        {q.isPending ? (
          <div style={{ padding: 14 }}><Loading what={t("tk.loading")} /></div>
        ) : rows.length ? (
          <table className="t">
            <thead>
              <tr>
                <th>{t("tk.col.id")}</th>
                <th>{t("tk.col.cell")}</th>
                <th>{t("tk.col.issue")}</th>
                <th className="num">{t("tk.col.expected")}</th>
                <th className="num">{t("tk.col.sourceNow")}</th>
                <th>{t("tk.col.status")}</th>
                <th>{t("tk.col.openedBy")}</th>
                <th>{t("tk.col.lastQc")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const song = row.status === "open" || row.status === "awaiting_verify";
                return (
                  <tr key={row.id}>
                    <td className="mono">{row.id}</td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {row.state} · {row.year} · {row.institution}
                      <div className="tone-muted" style={{ fontSize: 11 }}>
                        {row.from_rule_id
                          ? t("tk.fromRule", { rule: row.from_rule_id })
                          : t("tk.selfFound")}
                      </div>
                    </td>
                    <td>
                      <div style={{ color: "var(--ink)" }}>{row.title}</div>
                      {row.evidence ? (
                        <div className="tone-muted" style={{ fontSize: 11.5 }}>{row.evidence}</div>
                      ) : null}
                    </td>
                    <td className="num mono">{row.expected_value}</td>
                    <td className="num mono">
                      {row.last_observed ?? row.observed_at_open ?? "—"}
                    </td>
                    <td>
                      <Status value={row.status} />
                      {row.blocking && song ? (
                        <div><span className="pill pill-crit">{t("tk.blockPill")}</span></div>
                      ) : null}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      {row.created_by}
                      <div className="tone-muted" style={{ fontSize: 11 }}>{dt(row.created_at)}</div>
                    </td>
                    <td className="mono" style={{ fontSize: 11 }}>
                      {row.last_checked_run_id ? (
                        <>
                          {row.last_checked_run_id}
                          <div className="tone-muted">{dt(row.last_checked_at)}</div>
                        </>
                      ) : row.closed_run_id ? (
                        <>{t("tk.closedAt", { runId: row.closed_run_id })}</>
                      ) : (
                        <span className="tone-muted">{t("tk.notChecked")}</span>
                      )}
                    </td>
                    <td>
                      {song ? (
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {row.status === "open" ? (
                            <button
                              className="btn btn-sm"
                              onClick={() => setActing({ ticket: row, action: "mark_fixed" })}
                            >
                              {t("tk.markFixed")}
                            </button>
                          ) : null}
                          {q.data?.can_set_blocking ? (
                            <button
                              className="btn btn-sm"
                              onClick={() => setActing({ ticket: row, action: "set_blocking" })}
                            >
                              {row.blocking ? t("tk.unblock") : t("tk.setBlock")}
                            </button>
                          ) : null}
                          <button
                            className="btn btn-sm"
                            onClick={() => setActing({ ticket: row, action: "cancel" })}
                          >
                            {t("tk.cancel")}
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p className="spin" style={{ padding: 14 }}>{t("tk.empty")}</p>
        )}
      </div>

      {acting ? (
        <ActionModal
          ticket={acting.ticket}
          action={acting.action}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}

const TIEU_DE: Record<string, MessageKey> = {
  mark_fixed: "tk.modal.mark_fixed",
  set_blocking: "tk.modal.set_blocking",
  cancel: "tk.modal.cancel",
};

function ActionModal({
  ticket,
  action,
  onClose,
}: {
  ticket: Ticket;
  action: string;
  onClose: () => void;
}) {
  const { t, tn } = useI18n();
  const qc = useQueryClient();
  const [reason, setReason] = useState("");

  const m = useMutation({
    mutationFn: () =>
      patch(`/tickets/${ticket.id}`, {
        action,
        reason: reason.trim(),
        ...(action === "set_blocking" ? { blocking: !ticket.blocking } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["gate"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      onClose();
    },
  });

  const title = t("tk.modal.title", {
    action: TIEU_DE[action] ? t(TIEU_DE[action]) : action,
    id: ticket.id,
  });

  return (
    <Modal title={title} onClose={onClose}>
      <p className="sub" style={{ marginBottom: 10 }}>
        {action === "mark_fixed"
          ? tn("tk.modal.markFixedBody", {
              awaiting: <b>{t("tk.modal.markFixedAwaiting")}</b>,
              expected: <span className="mono">{ticket.expected_value}</span>,
              cell: (
                <span className="mono">
                  {ticket.state}/{ticket.institution}/{ticket.year}
                </span>
              ),
            })
          : action === "set_blocking"
            ? ticket.blocking
              ? tn("tk.modal.unblockBody", { still: <b>{t("tk.modal.unblockStill")}</b> })
              : t("tk.modal.blockBody")
            : t("tk.modal.cancelBody")}
      </p>
      <textarea
        rows={2}
        placeholder={t("exc.reasonPlaceholder")}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        style={{ width: "100%", marginBottom: 10 }}
      />
      <ErrBox error={m.error} />
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
        <button className="btn" onClick={onClose}>{t("common.cancel")}</button>
        <button
          className="btn btn-primary"
          disabled={reason.trim().length < 3 || m.isPending}
          onClick={() => m.mutate()}
        >
          {m.isPending ? t("common.sending") : t("common.confirm")}
        </button>
      </div>
    </Modal>
  );
}
