"use client";

// Vi pham luat cua lan nap hien tai + panel dieu tra.
//
// Doi vai so voi ban cu: man hinh nay khong con la cho SUA SO. Khong co o
// nhap so nao o day nua. No tra loi dung mot cau — "so nay co that su sai
// khong" — va neu sai thi mo ticket cho team Data sua o nguon.
//
// Mot man hinh, hai nua: trai la danh sach de quet nhanh, phai la cho
// quyet dinh. Bam mot dong ben trai thi ben phai doi — khong dieu huong,
// khong mat vi tri cuon.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef, RowClickedEvent } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useEffect, useMemo, useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import { gw, patch, post, qs } from "@/app/lib/api";
import { useFilters } from "@/app/lib/filters";
import type { ExceptionDetail, QcException } from "@/app/lib/types";
import { ErrBox, Loading, Severity, Status } from "@/app/ui/bits";
import RulesButton from "@/app/ui/rules-panel";
import { gridTheme, useGridLocale } from "@/app/ui/grid";

type ListRes = {
  total: number;
  rows: QcException[];
  run_id: string | null;
  qc_stale?: boolean;
  qc_stale_reason?: "run" | "rules" | null;
  rules_version?: number | null;
  ruleset_version?: number | null;
};

export default function ExceptionsPage() {
  const { t, tn } = useI18n();
  const { num } = useFmt();
  const gridLocale = useGridLocale();
  const { filters } = useFilters();
  const [severity, setSeverity] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const list = useQuery({
    queryKey: ["exceptions", filters, severity],
    queryFn: () => gw<ListRes>(`/exceptions${qs({ ...filters, severity, limit: 500 })}`),
  });

  const cols = useMemo<ColDef<QcException>[]>(
    () => [
      {
        field: "severity", headerName: t("exc.severity"), width: 124,
        cellRenderer: (p: { value: string }) => <Severity value={p.value} />,
      },
      { field: "rule_id", headerName: t("exc.col.rule"), width: 190, cellClass: "cell-code" },
      {
        headerName: t("exc.col.key"), width: 230, cellClass: "cell-code",
        valueGetter: (p) =>
          [p.data?.state, p.data?.institution, p.data?.year].filter(Boolean).join(" · "),
      },
      { field: "message", headerName: t("exc.col.message"), flex: 1, minWidth: 220 },
      {
        field: "observed", headerName: t("exc.col.observed"), width: 250,
        valueFormatter: (p) => (p.value ? JSON.stringify(p.value) : ""),
        cellClass: "cell-obs",
      },
    ],
    [t],
  );

  return (
    <>
      <div className="card-head">
        <div>
          <h1>{t("exc.title")}</h1>
          <p className="sub">
            {tn("exc.sub", {
              total: list.data ? num(list.data.total) : "…",
              runId: <span className="mono">{list.data?.run_id ?? "—"}</span>,
              rules: list.data?.rules_version
                ? t("exc.rulesVersion", { v: list.data.rules_version })
                : "",
            })}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="field">
            <label htmlFor="sv">{t("exc.severity")}</label>
            <select id="sv" value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">{t("common.all")}</option>
              <option value="critical">{t("severity.critical")}</option>
              <option value="warning">{t("severity.warning")}</option>
            </select>
          </div>
          {/* Cot rule_id tren bang chi la ma. Bo luat de ngay canh de doc
              duoc luat do noi gi ma khong roi man hinh nay. */}
          <RulesButton />
        </div>
      </div>

      {list.data?.qc_stale && list.data.qc_stale_reason === "rules" ? (
        <div className="banner banner-warn" style={{ marginBottom: 14 }}>
          <div>
            <div className="banner-title">{t("qc.staleRules.title")}</div>
            <div className="banner-body">
              {t("qc.staleRules.body", {
                current: list.data.ruleset_version ?? "—",
                applied: list.data.rules_version ?? "—",
              })}
            </div>
          </div>
        </div>
      ) : list.data?.qc_stale ? (
        <div className="banner banner-warn" style={{ marginBottom: 14 }}>
          <div>
            <div className="banner-title">{t("exc.staleTitle")}</div>
            <div className="banner-body">
              {tn("exc.staleBody", {
                runId: <span className="mono">{list.data.run_id}</span>,
              })}
            </div>
          </div>
        </div>
      ) : null}

      <ErrBox error={list.error} />

      <div className="split">
        <div style={{ height: "calc(100vh - 300px)", minHeight: 420 }}>
          {list.isPending ? (
            <Loading what={t("exc.loading")} />
          ) : (
            <AgGridReact<QcException>
              theme={gridTheme}
              localeText={gridLocale}
              rowData={list.data?.rows ?? []}
              columnDefs={cols}
              defaultColDef={{ sortable: true, resizable: true, suppressHeaderMenuButton: true }}
              getRowId={(p) => String(p.data.id)}
              rowSelection={{ mode: "singleRow", checkboxes: false, enableClickSelection: true }}
              onRowClicked={(e: RowClickedEvent<QcException>) => setSelected(e.data?.id ?? null)}
              animateRows={false}
            />
          )}
        </div>

        <Panel id={selected} />
      </div>
    </>
  );
}

// ---------------------------------------------------------- panel dieu tra

function Panel({ id }: { id: number | null }) {
  const { t, tn } = useI18n();
  const { dt, num, pct } = useFmt();
  const qc = useQueryClient();
  const [expected, setExpected] = useState("");
  const [title, setTitle] = useState("");
  const [evidence, setEvidence] = useState("");
  const [blocking, setBlocking] = useState(true);

  const detail = useQuery({
    queryKey: ["exception", id],
    queryFn: () => gw<ExceptionDetail>(`/exceptions/${id}`),
    enabled: id !== null,
  });

  const d = detail.data;

  // Doi dong dang xem thi don sach o nhap. Khong doan ho so dung: gia tri
  // ky vong la thu nguoi dung phai TU khang dinh, vi no se thanh dieu kien
  // nghiem thu ma QC dem ra doi chieu.
  useEffect(() => {
    setExpected("");
    setEvidence("");
    setBlocking(true);
    setTitle(d?.exception.message ?? "");
  }, [id, d?.exception.message]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["exception", id] });
    qc.invalidateQueries({ queryKey: ["tickets"] });
    qc.invalidateQueries({ queryKey: ["gate"] });
    qc.invalidateQueries({ queryKey: ["summary"] });
    qc.invalidateQueries({ queryKey: ["facts"] });
  };

  const open = useMutation({
    mutationFn: () =>
      post("/tickets", {
        year: d!.exception.year, state: d!.exception.state,
        institution_id: d!.exception.institution_id,
        title: title.trim(), expected_value: Number(expected),
        evidence: evidence.trim() || null, blocking,
        from_rule_id: d!.exception.rule_id,
      }),
    onSuccess: invalidate,
  });

  const act = useMutation({
    mutationFn: (v: { action: string; reason: string; blocking?: boolean }) =>
      patch(`/tickets/${d!.ticket!.id}`, v),
    onSuccess: invalidate,
  });

  if (id === null) {
    return (
      <div className="card">
        <h2>{t("exc.panel.title")}</h2>
        <p className="sub" style={{ marginTop: 6 }}>
          {t("exc.panel.empty")}
        </p>
      </div>
    );
  }

  if (detail.isPending) return <div className="card"><Loading what={t("exc.panel.loading")} /></div>;
  if (detail.error) return <div className="card"><ErrBox error={detail.error} /></div>;

  const e = d!.exception;
  const ticket = d!.ticket;
  const song = ticket && (ticket.status === "open" || ticket.status === "awaiting_verify");
  const theo_o = e.institution_id !== null && e.year !== null;

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <Severity value={e.severity} />
        <span className="mono" style={{ fontSize: 12 }}>{e.rule_id}</span>
        <span style={{ flex: 1 }} />
        <span className="mono tone-muted" style={{ fontSize: 11 }}>#{e.id}</span>
      </div>

      <h2 style={{ marginBottom: 4 }}>{e.message}</h2>
      <p className="sub mono" style={{ marginBottom: 12 }}>
        {[e.state, e.institution, e.year].filter(Boolean).join(" · ")}
      </p>

      {/* --- ban da ky gan nhat dat canh lan nap nay --- */}
      <div className="compare" style={{ marginBottom: 12 }}>
        <div>
          <div className="stat-label">{t("exc.lastSigned")}</div>
          {d!.last_signed ? (
            <>
              <div className="big">
                {d!.last_signed.run_id === d!.fact?.run_id ? num(d!.fact?.deposit) : "—"}
              </div>
              <div className="stat-note">
                {d!.last_signed.label} · {dt(d!.last_signed.signed_at)}
                {d!.last_signed.run_id !== d!.fact?.run_id ? t("exc.otherRun") : ""}
              </div>
            </>
          ) : (
            <>
              <div className="big tone-muted">—</div>
              <div className="stat-note">{t("exc.noneSigned")}</div>
            </>
          )}
        </div>
        <div>
          <div className="stat-label">{t("exc.thisRun")}</div>
          <div className="big">{num(d!.fact?.deposit)}</div>
          <div className="stat-note">
            {d!.fact?.prev_year
              ? t("exc.prevYear", {
                  year: d!.fact.prev_year,
                  value: num(d!.fact.prev_deposit),
                })
              : t("exc.noPrevYear")}
            {d!.fact?.deposit_share ? ` · ${pct(d!.fact.deposit_share)}` : ""}
          </div>
        </div>
      </div>

      {e.observed ? (
        <dl className="kv" style={{ marginBottom: 12 }}>
          {Object.entries(e.observed).map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{k}</dt>
              <dd className="mono">{String(v)}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {/* --- da co ticket tren dung o nay --- */}
      {song ? (
        <TicketBox ticket={ticket!} act={act} />
      ) : !theo_o ? (
        <p className="sub" style={{ marginBottom: 12 }}>
          {t("exc.notPerCell")}
        </p>
      ) : !d!.can_open_ticket ? (
        <p className="sub" style={{ marginBottom: 12 }}>
          {t("exc.readOnly")}
        </p>
      ) : (
        <>
          <h2 style={{ marginTop: 14, marginBottom: 6 }}>{t("exc.openTitle")}</h2>
          <p className="sub" style={{ marginBottom: 10 }}>
            {tn("exc.openSub", { acceptance: <b>{t("exc.openSubAcceptance")}</b> })}
          </p>

          <div className="field" style={{ marginBottom: 10 }}>
            <label htmlFor="ev">{t("exc.expectedLabel")}</label>
            <input
              id="ev"
              type="number"
              value={expected}
              onChange={(ev) => setExpected(ev.target.value)}
              style={{ width: 130 }}
            />
            <span className="sub">{t("exc.sourceNow", { n: num(d!.fact?.deposit) })}</span>
          </div>

          <input
            type="text"
            placeholder={t("exc.titlePlaceholder")}
            value={title}
            onChange={(ev) => setTitle(ev.target.value)}
            style={{ width: "100%", marginBottom: 8 }}
          />
          <textarea
            rows={2}
            placeholder={t("exc.evidencePlaceholder")}
            value={evidence}
            onChange={(ev) => setEvidence(ev.target.value)}
            style={{ marginBottom: 8 }}
          />
          <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <input
              type="checkbox"
              checked={blocking}
              onChange={(ev) => setBlocking(ev.target.checked)}
            />
            <span className="sub">{t("exc.blockingLabel")}</span>
          </label>

          <ErrBox error={open.error} />
          <button
            className="btn btn-primary btn-sm"
            disabled={!expected || title.trim().length < 5 || open.isPending}
            onClick={() => open.mutate()}
          >
            {open.isPending ? t("exc.opening") : t("exc.open")}
          </button>
        </>
      )}

      {d!.history.length ? (
        <>
          <h2 style={{ marginTop: 16, marginBottom: 6 }}>{t("exc.trail")}</h2>
          <table className="t">
            <tbody>
              {d!.history.map((h, i) => (
                <tr key={i}>
                  <td className="mono" style={{ fontSize: 11 }}>{dt(h.created_at)}</td>
                  <td>{h.actor}</td>
                  <td><span className="pill">{h.action}</span></td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {h.before ? JSON.stringify(h.before) : ""} → {h.after ? JSON.stringify(h.after) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </div>
  );
}

// --------------------------------------------------------- ticket dang song

function TicketBox({
  ticket,
  act,
}: {
  ticket: NonNullable<ExceptionDetail["ticket"]>;
  act: { mutate: (v: { action: string; reason: string }) => void; isPending: boolean; error: unknown };
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");

  return (
    <div className="banner banner-warn" style={{ marginBottom: 12, display: "block" }}>
      <div className="banner-title">
        {t("exc.box.title", { id: ticket.id })} <Status value={ticket.status} />
        {ticket.blocking ? <span className="pill pill-crit">{t("exc.box.blocking")}</span> : null}
      </div>
      <div className="banner-body" style={{ marginBottom: 8 }}>
        {ticket.title}
        <div className="mono" style={{ fontSize: 11.5, marginTop: 4 }}>
          {t("exc.box.meta", {
            expected: ticket.expected_value,
            observed: ticket.observed_at_open,
          })}
          {ticket.last_checked_run_id
            ? t("exc.box.qcChecked", {
                runId: ticket.last_checked_run_id,
                observed: ticket.last_observed ?? t("exc.box.noRow"),
              })
            : t("exc.box.qcNever")}
        </div>
        {ticket.status === "awaiting_verify" ? (
          <div style={{ marginTop: 6 }}>
            {t("exc.box.awaiting", {
              who: ticket.marked_fixed_by,
              expected: ticket.expected_value,
            })}
          </div>
        ) : null}
      </div>

      <input
        type="text"
        placeholder={t("exc.reasonPlaceholder")}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        style={{ width: "100%", marginBottom: 8 }}
      />
      <ErrBox error={act.error} />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {ticket.status === "open" ? (
          <button
            className="btn btn-sm btn-primary"
            disabled={reason.trim().length < 3 || act.isPending}
            onClick={() => act.mutate({ action: "mark_fixed", reason })}
          >
            {t("exc.markFixed")}
          </button>
        ) : null}
        <button
          className="btn btn-sm"
          disabled={reason.trim().length < 3 || act.isPending}
          onClick={() => act.mutate({ action: "cancel", reason })}
        >
          {t("exc.cancelTicket")}
        </button>
      </div>
    </div>
  );
}
