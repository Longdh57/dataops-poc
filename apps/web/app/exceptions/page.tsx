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

import { gw, patch, post, qs } from "@/app/lib/api";
import { useFilters } from "@/app/lib/filters";
import { dt, num, pct } from "@/app/lib/format";
import type { ExceptionDetail, QcException } from "@/app/lib/types";
import { ErrBox, Loading, Severity, Status } from "@/app/ui/bits";
import { gridTheme } from "@/app/ui/grid";

type ListRes = {
  total: number;
  rows: QcException[];
  run_id: string | null;
  qc_stale?: boolean;
  rules_version?: number | null;
};

export default function ExceptionsPage() {
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
          <h1>Vi phạm luật</h1>
          <p className="sub">
            {list.data ? num(list.data.total) : "…"} vi phạm trong phạm vi của bạn, ở lần nạp{" "}
            <span className="mono">{list.data?.run_id ?? "—"}</span>
            {list.data?.rules_version ? ` · bộ luật version ${list.data.rules_version}` : ""}. Đây
            là nghi ngờ của máy, không phải kết luận — bấm một dòng để điều tra.
          </p>
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

      {list.data?.qc_stale ? (
        <div className="banner banner-warn" style={{ marginBottom: 14 }}>
          <div>
            <div className="banner-title">QC chưa kiểm lần nạp mới nhất</div>
            <div className="banner-body">
              Danh sách dưới đây là của lần nạp <span className="mono">{list.data.run_id}</span>,
              không phải lần nạp đang có trong bản sao. Ký lúc này bị máy chủ từ chối — chờ QC
              chạy xong (mỗi 5 phút).
            </div>
          </div>
        </div>
      ) : null}

      <ErrBox error={list.error} />

      <div className="split">
        <div style={{ height: "calc(100vh - 300px)", minHeight: 420 }}>
          {list.isPending ? (
            <Loading what="vi phạm" />
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

        <Panel id={selected} />
      </div>
    </>
  );
}

// ---------------------------------------------------------- panel dieu tra

function Panel({ id }: { id: number | null }) {
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
        gender: d!.exception.gender, name: d!.exception.name,
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
        <h2>Panel điều tra</h2>
        <p className="sub" style={{ marginTop: 6 }}>
          Chọn một vi phạm ở bảng bên trái. Panel sẽ đặt bản đã ký gần nhất cạnh lần nạp này để
          bạn thấy rõ số nào đổi, rồi cho mở ticket nếu số thật sự sai.
        </p>
      </div>
    );
  }

  if (detail.isPending) return <div className="card"><Loading what="chi tiết" /></div>;
  if (detail.error) return <div className="card"><ErrBox error={detail.error} /></div>;

  const e = d!.exception;
  const t = d!.ticket;
  const song = t && (t.status === "open" || t.status === "awaiting_verify");
  const theo_o = e.name !== null && e.year !== null;

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
          {d!.last_signed ? (
            <>
              <div className="big">
                {d!.last_signed.run_id === d!.fact?.run_id ? num(d!.fact?.number) : "—"}
              </div>
              <div className="stat-note">
                {d!.last_signed.label} · {dt(d!.last_signed.signed_at)}
                {d!.last_signed.run_id !== d!.fact?.run_id ? " · lần nạp khác" : ""}
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
          <div className="big">{num(d!.fact?.number)}</div>
          <div className="stat-note">
            {d!.fact?.prev_year
              ? `${d!.fact.prev_year}: ${num(d!.fact.prev_number)}`
              : "không có số năm trước"}
            {d!.fact?.market_share ? ` · ${pct(d!.fact.market_share)}` : ""}
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
        <TicketBox ticket={t!} act={act} />
      ) : !theo_o ? (
        <p className="sub" style={{ marginBottom: 12 }}>
          Vi phạm này gắn với cả một nhóm chứ không gắn vào một ô cụ thể, nên không mở ticket
          theo ô được. Sửa ở nguồn rồi để QC kiểm lại ở lần nạp sau.
        </p>
      ) : !d!.can_open_ticket ? (
        <p className="sub" style={{ marginBottom: 12 }}>
          Vai trò của bạn chỉ xem được. Nhờ analyst hoặc team lead mở ticket.
        </p>
      ) : (
        <>
          <h2 style={{ marginTop: 14, marginBottom: 6 }}>Mở ticket cho team Data</h2>
          <p className="sub" style={{ marginBottom: 10 }}>
            Số đúng ở dưới là <b>điều kiện nghiệm thu</b>: QC sẽ đọc số thật ở lần nạp sau và đối
            chiếu với nó. Chỉ QC mới đóng được ticket này — không ai bấm đóng bằng tay.
          </p>

          <div className="field" style={{ marginBottom: 10 }}>
            <label htmlFor="ev">Số đúng phải là</label>
            <input
              id="ev"
              type="number"
              value={expected}
              onChange={(ev) => setExpected(ev.target.value)}
              style={{ width: 130 }}
            />
            <span className="sub">nguồn đang là {num(d!.fact?.number)}</span>
          </div>

          <input
            type="text"
            placeholder="Lỗi là gì — câu người khác đọc"
            value={title}
            onChange={(ev) => setTitle(ev.target.value)}
            style={{ width: "100%", marginBottom: 8 }}
          />
          <textarea
            rows={2}
            placeholder="Bằng chứng — link, số đối chiếu, ai xác nhận"
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
            <span className="sub">
              Chặn phát hành cho tới khi nguồn sửa xong — bỏ tick nếu lỗi không ảnh hưởng bản
              đang bán.
            </span>
          </label>

          <ErrBox error={open.error} />
          <button
            className="btn btn-primary btn-sm"
            disabled={!expected || title.trim().length < 5 || open.isPending}
            onClick={() => open.mutate()}
          >
            {open.isPending ? "Đang mở…" : "Mở ticket"}
          </button>
        </>
      )}

      {d!.history.length ? (
        <>
          <h2 style={{ marginTop: 16, marginBottom: 6 }}>Dấu vết</h2>
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
  const [reason, setReason] = useState("");

  return (
    <div className="banner banner-warn" style={{ marginBottom: 12, display: "block" }}>
      <div className="banner-title">
        Ô này đã có ticket #{ticket.id} <Status value={ticket.status} />
        {ticket.blocking ? <span className="pill pill-crit">chặn phát hành</span> : null}
      </div>
      <div className="banner-body" style={{ marginBottom: 8 }}>
        {ticket.title}
        <div className="mono" style={{ fontSize: 11.5, marginTop: 4 }}>
          cần = {ticket.expected_value} · lúc mở đọc được {ticket.observed_at_open}
          {ticket.last_checked_run_id
            ? ` · QC kiểm ở ${ticket.last_checked_run_id}: ${ticket.last_observed ?? "không còn dòng"}`
            : " · QC chưa kiểm lần nào"}
        </div>
        {ticket.status === "awaiting_verify" ? (
          <div style={{ marginTop: 6 }}>
            {ticket.marked_fixed_by} báo đã sửa. Ticket đóng khi lần nạp sau đọc được đúng{" "}
            {ticket.expected_value} — không đóng bằng tay.
          </div>
        ) : null}
      </div>

      <input
        type="text"
        placeholder="Lý do — bắt buộc, vào audit log"
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
            Nguồn đã sửa — nhờ QC xác minh
          </button>
        ) : null}
        <button
          className="btn btn-sm"
          disabled={reason.trim().length < 3 || act.isPending}
          onClick={() => act.mutate({ action: "cancel", reason })}
        >
          Báo nhầm — huỷ ticket
        </button>
      </div>
    </div>
  );
}
