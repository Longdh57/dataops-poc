"use client";

// Hop thu ngoai le + panel dieu tra.
//
// Mot man hinh, hai nua: trai la danh sach de quet nhanh, phai la cho
// quyet dinh. Bam mot dong ben trai thi ben phai doi — khong dieu huong,
// khong mat vi tri cuon.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColDef, RowClickedEvent } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useEffect, useMemo, useState } from "react";

import { ApiError, gw, patch, qs } from "@/app/lib/api";
import { useFilters } from "@/app/lib/filters";
import { dt, num, pct } from "@/app/lib/format";
import type { ConflictDetail, ExceptionDetail, QcException } from "@/app/lib/types";
import { ErrBox, Loading, Severity } from "@/app/ui/bits";
import { gridTheme } from "@/app/ui/grid";

type ListRes = { total: number; rows: QcException[] };

export default function ExceptionsPage() {
  const { filters } = useFilters();
  const [status, setStatus] = useState("open");
  const [severity, setSeverity] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const list = useQuery({
    queryKey: ["exceptions", filters, status, severity],
    queryFn: () => gw<ListRes>(`/exceptions${qs({ ...filters, status, severity, limit: 500 })}`),
  });

  const cols = useMemo<ColDef<QcException>[]>(
    () => [
      {
        field: "severity", headerName: "Mức", width: 124,
        cellRenderer: (p: { value: string }) => <Severity value={p.value} />,
      },
      { field: "rule_id", headerName: "Luật", width: 190, cellClass: "cell-code" },
      {
        headerName: "Khoá", width: 230, cellClass: "cell-code",
        valueGetter: (p) =>
          [p.data?.state, p.data?.gender, p.data?.year, p.data?.name].filter(Boolean).join(" · "),
      },
      { field: "message", headerName: "Vấn đề", flex: 1, minWidth: 220 },
      {
        field: "observed", headerName: "Số liệu quan sát", width: 250,
        valueFormatter: (p) => (p.value ? JSON.stringify(p.value) : ""),
        cellClass: "cell-obs",
      },
    ],
    [],
  );

  return (
    <>
      <div className="card-head">
        <div>
          <h1>Hộp thư ngoại lệ</h1>
          <p className="sub">
            {list.data ? num(list.data.total) : "…"} ngoại lệ trong phạm vi của bạn. Bấm một dòng
            để mở panel điều tra bên phải.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <div className="field">
            <label htmlFor="st">Trạng thái</label>
            <select id="st" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="open">đang mở</option>
              <option value="applied">đã sửa</option>
              <option value="parked">gác lại</option>
              <option value="sent_back">trả về</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="sv">Mức</label>
            <select id="sv" value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">tất cả</option>
              <option value="critical">nghiêm trọng</option>
              <option value="warning">cảnh báo</option>
            </select>
          </div>
        </div>
      </div>

      <ErrBox error={list.error} />

      <div className="split">
        <div style={{ height: "calc(100vh - 300px)", minHeight: 420 }}>
          {list.isPending ? (
            <Loading what="ngoại lệ" />
          ) : (
            <AgGridReact<QcException>
              theme={gridTheme}
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

        <Panel id={selected} onResolved={() => setSelected(null)} />
      </div>
    </>
  );
}

// ---------------------------------------------------------- panel dieu tra

function Panel({ id, onResolved }: { id: number | null; onResolved: () => void }) {
  const qc = useQueryClient();
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [conflict, setConflict] = useState<ConflictDetail | null>(null);

  const detail = useQuery({
    queryKey: ["exception", id],
    queryFn: () => gw<ExceptionDetail>(`/exceptions/${id}`),
    enabled: id !== null,
  });

  // Doi dong dang xem thi nap lai o nhap bang so DANG HIEU LUC — da sua tay
  // thi lay so da sua, chua thi lay so cua lan nap — roi xoa xung dot cu.
  const live = detail.data?.override?.new_value ?? detail.data?.fact?.number;
  useEffect(() => {
    setConflict(null);
    setReason("");
    setValue(live === undefined ? "" : String(live));
  }, [id, live]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = useMutation({
    mutationFn: (v: { action: string; expected: number }) =>
      patch(`/exceptions/${id}`, {
        action: v.action,
        new_value: v.action === "apply" ? Number(value) : null,
        reason,
        expected_version: v.expected,
      }),
    onError: (e) => {
      // 409 = co nguoi khac vua sua dong nay. API tra ve du ba con so de
      // nguoi dung tu quyet dinh, khong tu dong ghi de.
      if (e instanceof ApiError && e.status === 409 && typeof e.detail === "object") {
        setConflict(e.detail as ConflictDetail);
      }
    },
    onSuccess: () => {
      setConflict(null);
      qc.invalidateQueries({ queryKey: ["exceptions"] });
      qc.invalidateQueries({ queryKey: ["gate"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      qc.invalidateQueries({ queryKey: ["facts"] });
      onResolved();
    },
  });

  if (id === null) {
    return (
      <div className="card">
        <h2>Panel điều tra</h2>
        <p className="sub" style={{ marginTop: 6 }}>
          Chọn một ngoại lệ ở bảng bên trái. Panel sẽ đặt bản đã ký gần nhất cạnh lần nạp này để
          bạn thấy rõ số nào đổi, rồi cho sửa ngay tại đây.
        </p>
      </div>
    );
  }

  if (detail.isPending) return <div className="card"><Loading what="chi tiết" /></div>;
  if (detail.error) return <div className="card"><ErrBox error={detail.error} /></div>;

  const d = detail.data!;
  const e = d.exception;
  const canAct = reason.trim().length >= 3;
  const expected = conflict ? conflict.current_version : d.expected_version;

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
        {[e.state, e.gender, e.year, e.name].filter(Boolean).join(" · ")}
      </p>

      {/* --- ban da ky gan nhat dat canh lan nap nay --- */}
      <div className="compare" style={{ marginBottom: 12 }}>
        <div>
          <div className="stat-label">Bản đã ký gần nhất</div>
          {d.last_signed ? (
            <>
              <div className="big">
                {d.last_signed.run_id === d.fact?.run_id ? num(d.fact?.number) : "—"}
              </div>
              <div className="stat-note">
                {d.last_signed.label} · {dt(d.last_signed.signed_at)}
                {d.last_signed.run_id !== d.fact?.run_id ? " · lần nạp khác" : ""}
              </div>
            </>
          ) : (
            <>
              <div className="big tone-muted">—</div>
              <div className="stat-note">chưa ký bản nào</div>
            </>
          )}
        </div>
        <div>
          <div className="stat-label">Lần nạp này</div>
          <div className="big">{num(d.fact?.number)}</div>
          <div className="stat-note">
            {d.fact?.prev_year
              ? `${d.fact.prev_year}: ${num(d.fact.prev_number)}`
              : "không có số năm trước"}
            {d.fact?.market_share ? ` · ${pct(d.fact.market_share)}` : ""}
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

      {d.override ? (
        <div className="banner banner-warn" style={{ marginBottom: 12 }}>
          <div>
            <div className="banner-title">Ô này đã được sửa tay</div>
            <div className="banner-body">
              {d.override.old_value} → <b>{d.override.new_value}</b> · {d.override.created_by} ·{" "}
              bản {d.override.version} · “{d.override.reason}”
            </div>
          </div>
        </div>
      ) : null}

      {/* --- xung dot khoa lac quan --- */}
      {conflict ? (
        <div className="banner banner-crit" style={{ marginBottom: 12, display: "block" }}>
          <div className="banner-title">Có người khác vừa sửa dòng này</div>
          <div className="banner-body" style={{ marginBottom: 8 }}>
            Bạn đang cầm bản <b>{conflict.expected_version}</b>, trên máy chủ đã là bản{" "}
            <b>{conflict.current_version}</b>. Số của bạn <b>chưa</b> được ghi.
          </div>
          <dl className="kv" style={{ marginBottom: 10 }}>
            <dt>số gốc</dt>
            <dd className="mono">{num(conflict.gia_tri_goc)}</dd>
            <dt>trên máy chủ</dt>
            <dd className="mono"><b>{num(conflict.gia_tri_hien_tai)}</b></dd>
            <dt>bạn muốn ghi</dt>
            <dd className="mono">{num(conflict.gia_tri_ban_muon_ghi)}</dd>
          </dl>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn-sm"
              onClick={() => {
                setConflict(null);
                detail.refetch();
              }}
            >
              Tải lại dòng
            </button>
            <button
              className="btn btn-sm btn-danger"
              disabled={act.isPending}
              onClick={() => act.mutate({ action: "apply", expected: conflict.current_version })}
            >
              Ghi đè có chủ đích
            </button>
          </div>
        </div>
      ) : null}

      <div className="field" style={{ marginBottom: 10 }}>
        <label htmlFor="nv">Số mới</label>
        <input
          id="nv"
          type="number"
          value={value}
          onChange={(ev) => setValue(ev.target.value)}
          style={{ width: 130 }}
        />
        <span className="sub">bản hiện tại: {expected}</span>
      </div>

      <textarea
        rows={2}
        placeholder="Lý do — bắt buộc, sẽ vào audit log"
        value={reason}
        onChange={(ev) => setReason(ev.target.value)}
        style={{ marginBottom: 10 }}
      />

      {act.error && !conflict ? <ErrBox error={act.error} /> : null}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
        <button
          className="btn btn-primary btn-sm"
          disabled={!canAct || !value || act.isPending}
          onClick={() => act.mutate({ action: "apply", expected: d.expected_version })}
        >
          Áp dụng số mới
        </button>
        <button
          className="btn btn-sm"
          disabled={!canAct || act.isPending}
          onClick={() => act.mutate({ action: "park", expected: d.expected_version })}
        >
          Gác lại
        </button>
        <button
          className="btn btn-sm"
          disabled={!canAct || act.isPending}
          onClick={() => act.mutate({ action: "send_back", expected: d.expected_version })}
        >
          Trả về nguồn
        </button>
      </div>
      <p className="sub" style={{ marginTop: 8 }}>
        Ghi override, đóng ngoại lệ và ghi audit nằm trong cùng một transaction — cùng sống cùng chết.
      </p>

      {d.history.length ? (
        <>
          <h2 style={{ marginTop: 16, marginBottom: 6 }}>Dấu vết</h2>
          <table className="t">
            <tbody>
              {d.history.map((h, i) => (
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
