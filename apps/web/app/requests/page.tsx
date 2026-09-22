"use client";

// Trang cho sale: xin file, theo doi trang thai, tai ve khi xong.
//
// Export chay bat dong bo — POST tra 202 kem job_id chu khong giu ket noi
// cho file sinh xong. Trang nay poll 5 giay mot lan khi con job dang chay.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import { gw, post } from "@/app/lib/api";
import { useGate } from "@/app/lib/queries";
import type { ExportCreated, ExportJob } from "@/app/lib/types";
import { ErrBox, Loading, Status } from "@/app/ui/bits";

export default function RequestsPage() {
  const { t } = useI18n();
  const { dt, num } = useFmt();
  const qc = useQueryClient();
  const { data: gate } = useGate();
  const [format, setFormat] = useState("csv");

  const q = useQuery({
    queryKey: ["exports"],
    queryFn: () => gw<{ rows: ExportJob[] }>("/exports"),
    refetchInterval: (query) => {
      const rows = query.state.data?.rows ?? [];
      return rows.some((r) => r.status === "pending" || r.status === "running") ? 5_000 : false;
    },
  });

  const ask = useMutation({
    mutationFn: () => post<ExportCreated>("/exports", { format }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exports"] }),
  });

  const locked = gate?.locked ?? false;

  return (
    <>
      <div className="card-head">
        <div>
          <h1>{t("req.title")}</h1>
          <p className="sub">{t("req.sub")}</p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>{t("req.askTitle")}</h2>
          {locked ? (
            <span className="pill pill-crit">{t("req.gateLocked")}</span>
          ) : (
            <span className="pill pill-good">{t("req.gateReady")}</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div className="field">
            <label htmlFor="fm">{t("req.format")}</label>
            <select id="fm" value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="csv">CSV</option>
              <option value="xlsx">Excel</option>
            </select>
          </div>
          <button className="btn btn-primary" disabled={locked || ask.isPending} onClick={() => ask.mutate()}>
            {ask.isPending ? t("common.sending") : t("req.submit")}
          </button>
          {locked ? (
            <p className="sub" style={{ flex: 1, minWidth: 240 }}>{t("req.lockedNote")}</p>
          ) : null}
        </div>
        <div style={{ marginTop: 9 }}>
          <ErrBox error={ask.error} />
          {ask.data ? (
            <div className={`banner ${ask.data.triggered ? "banner-good" : "banner-warn"}`}>
              <div>
                <div className="banner-title">
                  {ask.data.triggered
                    ? t("req.created.triggered", { id: ask.data.job_id })
                    : t("req.created.queued", { id: ask.data.job_id })}
                </div>
                <div className="banner-body">
                  {t("req.created.body", {
                    label: ask.data.signed_version.label,
                    scope: ask.data.scope
                      ? t("req.created.scope", { states: ask.data.scope.join(", ") })
                      : t("req.created.scopeAll"),
                    note: ask.data.triggered ? "" : t("req.created.note", { note: ask.data.note }),
                  })}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="card card-pad0">
        {q.isPending ? (
          <div style={{ padding: 14 }}><Loading what={t("req.loading")} /></div>
        ) : q.data?.rows.length ? (
          <table className="t">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("req.col.status")}</th>
                <th>{t("req.col.signed")}</th>
                <th>{t("req.col.format")}</th>
                <th>{t("req.col.scope")}</th>
                <th className="num">{t("req.col.rows")}</th>
                <th>{t("req.col.requestedBy")}</th>
                <th>{t("req.col.at")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((j) => (
                <tr key={j.id}>
                  <td className="mono">{j.id}</td>
                  <td>
                    <Status value={j.status} />
                    {j.warning ? (
                      <div className="tone-warn" style={{ fontSize: 11.5, marginTop: 4, maxWidth: 260 }}>
                        {j.warning}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    {j.signed_label ?? <span className="tone-muted">—</span>}
                    <div className="mono tone-muted" style={{ fontSize: 11 }}>{j.run_id}</div>
                  </td>
                  <td><span className="pill">{j.format}</span></td>
                  <td className="mono" style={{ fontSize: 11.5 }}>
                    {j.scope_states?.length ? j.scope_states.join(", ") : t("common.all")}
                  </td>
                  <td className="num">{j.row_count ? num(j.row_count) : "—"}</td>
                  <td>{j.requested_by}</td>
                  <td className="mono" style={{ fontSize: 11.5 }}>{dt(j.created_at)}</td>
                  <td><Download job={j} locked={locked} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="spin" style={{ padding: 14 }}>{t("req.empty")}</p>
        )}
      </div>
    </>
  );
}

function Download({ job, locked }: { job: ExportJob; locked: boolean }) {
  const { t } = useI18n();
  const m = useMutation({
    mutationFn: () => gw<{ url: string }>(`/exports/${job.id}/download`),
    onSuccess: (d) => window.open(d.url, "_blank", "noopener"),
  });

  if (job.status === "error") {
    return <span className="tone-crit" style={{ fontSize: 12 }}>{job.error}</span>;
  }
  if (job.status !== "done") {
    return <span className="tone-muted" style={{ fontSize: 12 }}>{t("req.waiting")}</span>;
  }
  return (
    <>
      <button
        className="btn btn-sm btn-primary"
        disabled={locked || m.isPending}
        onClick={() => m.mutate()}
        title={locked ? t("req.downloadTitleLocked") : t("req.downloadTitle")}
      >
        {m.isPending ? t("req.downloadSigning") : t("req.download")}
      </button>
      {m.error ? <div style={{ marginTop: 6 }}><ErrBox error={m.error} /></div> : null}
    </>
  );
}
