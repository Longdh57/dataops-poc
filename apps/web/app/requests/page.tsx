"use client";

// Trang cho sale: xin file, theo doi trang thai, tai ve khi xong.
//
// Export chay bat dong bo — POST tra 202 kem job_id chu khong giu ket noi
// cho file sinh xong. Trang nay poll 5 giay mot lan khi con job dang chay.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { gw, post } from "@/app/lib/api";
import { dt, num } from "@/app/lib/format";
import { useGate } from "@/app/lib/queries";
import type { ExportCreated, ExportJob } from "@/app/lib/types";
import { ErrBox, Loading, Status } from "@/app/ui/bits";

export default function RequestsPage() {
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
          <h1>Yêu cầu dữ liệu</h1>
          <p className="sub">
            File gửi khách xuất thẳng từ BigQuery — nguồn sự thật — nhưng chỉ lấy những lần nạp
            nằm trong bản đã ký, và chỉ những bang trong phạm vi của bạn. Các ô sửa tay được áp
            lên trên, thị phần tính lại cho nhóm bị sửa.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>Xin một bản file</h2>
          {locked ? (
            <span className="pill pill-crit">cổng đang khoá</span>
          ) : (
            <span className="pill pill-good">cổng sẵn sàng</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div className="field">
            <label htmlFor="fm">Định dạng</label>
            <select id="fm" value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="csv">CSV</option>
              <option value="xlsx">Excel</option>
            </select>
          </div>
          <button className="btn btn-primary" disabled={locked || ask.isPending} onClick={() => ask.mutate()}>
            {ask.isPending ? "Đang gửi…" : "Gửi yêu cầu"}
          </button>
          {locked ? (
            <p className="sub" style={{ flex: 1, minWidth: 240 }}>
              Cổng phát hành đang khoá nên không xin file được. Máy chủ trả 409 kể cả khi bạn gọi
              thẳng API.
            </p>
          ) : null}
        </div>
        <div style={{ marginTop: 9 }}>
          <ErrBox error={ask.error} />
          {ask.data ? (
            <div className={`banner ${ask.data.triggered ? "banner-good" : "banner-warn"}`}>
              <div>
                <div className="banner-title">
                  {ask.data.triggered
                    ? `Đã nhận yêu cầu #${ask.data.job_id} và kích hoạt Export Job`
                    : `Đã xếp hàng yêu cầu #${ask.data.job_id}`}
                </div>
                <div className="banner-body">
                  Xuất từ bản ký <b>{ask.data.signed_version.label}</b>
                  {ask.data.scope ? ` · phạm vi ${ask.data.scope.join(", ")}` : " · toàn bộ phạm vi"}
                  {ask.data.triggered ? "" : ` — ${ask.data.note}`}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="card card-pad0">
        {q.isPending ? (
          <div style={{ padding: 14 }}><Loading what="yêu cầu" /></div>
        ) : q.data?.rows.length ? (
          <table className="t">
            <thead>
              <tr>
                <th>#</th>
                <th>Trạng thái</th>
                <th>Bản ký</th>
                <th>Định dạng</th>
                <th>Phạm vi</th>
                <th className="num">Số dòng</th>
                <th>Người yêu cầu</th>
                <th>Lúc gửi</th>
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
                    {j.scope_states?.length ? j.scope_states.join(", ") : "tất cả"}
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
          <p className="spin" style={{ padding: 14 }}>
            Chưa có yêu cầu nào.
          </p>
        )}
      </div>
    </>
  );
}

function Download({ job, locked }: { job: ExportJob; locked: boolean }) {
  const m = useMutation({
    mutationFn: () => gw<{ url: string }>(`/exports/${job.id}/download`),
    onSuccess: (d) => window.open(d.url, "_blank", "noopener"),
  });

  if (job.status === "error") {
    return <span className="tone-crit" style={{ fontSize: 12 }}>{job.error}</span>;
  }
  if (job.status !== "done") {
    return <span className="tone-muted" style={{ fontSize: 12 }}>đang chờ job chạy</span>;
  }
  return (
    <>
      <button
        className="btn btn-sm btn-primary"
        disabled={locked || m.isPending}
        onClick={() => m.mutate()}
        title={locked ? "Cổng phát hành đang khoá" : "Link ký sẵn, hết hạn sau 15 phút"}
      >
        {m.isPending ? "Đang ký link…" : "Tải file"}
      </button>
      {m.error ? <div style={{ marginTop: 6 }}><ErrBox error={m.error} /></div> : null}
    </>
  );
}
