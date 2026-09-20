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

import { patch } from "@/app/lib/api";
import { dt } from "@/app/lib/format";
import { useTickets } from "@/app/lib/queries";
import type { Ticket } from "@/app/lib/types";
import { ErrBox, Loading, Modal, Status } from "@/app/ui/bits";

const LOC = [
  { v: "song", label: "chưa đóng" },
  { v: "open", label: "đang mở" },
  { v: "awaiting_verify", label: "chờ QC xác minh" },
  { v: "closed", label: "đã đóng" },
  { v: "cancelled", label: "đã huỷ" },
];

export default function TicketsPage() {
  const [status, setStatus] = useState("song");
  const q = useTickets(status);
  const [acting, setActing] = useState<{ ticket: Ticket; action: string } | null>(null);

  const rows = q.data?.rows ?? [];

  return (
    <>
      <div className="card-head">
        <div>
          <h1>Ticket gửi team Data</h1>
          <p className="sub">
            Mỗi ticket mang một <b>điều kiện nghiệm thu</b> kiểm được bằng máy. QC đọc số thật ở
            lần nạp kế tiếp và đối chiếu — chỉ nó mới đóng được ticket.
          </p>
        </div>
        <div className="field">
          <label htmlFor="st">Trạng thái</label>
          <select id="st" value={status} onChange={(e) => setStatus(e.target.value)}>
            {LOC.map((o) => (
              <option key={o.v} value={o.v}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      {q.data?.blocking_open ? (
        <div className="banner banner-crit" style={{ marginBottom: 16 }}>
          <div>
            <div className="banner-title">
              {q.data.blocking_open} ticket đang chặn phát hành
            </div>
            <div className="banner-body">
              Không ký và không xuất file được cho tới khi nguồn sửa xong và QC xác minh. Nếu một
              lỗi trong số này không ảnh hưởng bản đang bán, team lead gỡ chặn từng cái — đó là
              một quyết định có tên người, không phải bộ lọc.
            </div>
          </div>
        </div>
      ) : null}

      <ErrBox error={q.error} />

      <div className="card card-pad0">
        {q.isPending ? (
          <div style={{ padding: 14 }}><Loading what="ticket" /></div>
        ) : rows.length ? (
          <table className="t">
            <thead>
              <tr>
                <th>#</th>
                <th>Ô</th>
                <th>Lỗi</th>
                <th className="num">Cần</th>
                <th className="num">Nguồn đang là</th>
                <th>Trạng thái</th>
                <th>Người mở</th>
                <th>QC kiểm gần nhất</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const song = t.status === "open" || t.status === "awaiting_verify";
                return (
                  <tr key={t.id}>
                    <td className="mono">{t.id}</td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {t.state} · {t.gender} · {t.year} · {t.name}
                      {t.from_rule_id ? (
                        <div className="tone-muted" style={{ fontSize: 11 }}>từ {t.from_rule_id}</div>
                      ) : (
                        <div className="tone-muted" style={{ fontSize: 11 }}>người tự phát hiện</div>
                      )}
                    </td>
                    <td>
                      <div style={{ color: "var(--ink)" }}>{t.title}</div>
                      {t.evidence ? (
                        <div className="tone-muted" style={{ fontSize: 11.5 }}>{t.evidence}</div>
                      ) : null}
                    </td>
                    <td className="num mono">{t.expected_value}</td>
                    <td className="num mono">
                      {t.last_observed ?? t.observed_at_open ?? "—"}
                    </td>
                    <td>
                      <Status value={t.status} />
                      {t.blocking && song ? (
                        <div><span className="pill pill-crit">chặn</span></div>
                      ) : null}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      {t.created_by}
                      <div className="tone-muted" style={{ fontSize: 11 }}>{dt(t.created_at)}</div>
                    </td>
                    <td className="mono" style={{ fontSize: 11 }}>
                      {t.last_checked_run_id ? (
                        <>
                          {t.last_checked_run_id}
                          <div className="tone-muted">{dt(t.last_checked_at)}</div>
                        </>
                      ) : t.closed_run_id ? (
                        <>đóng ở {t.closed_run_id}</>
                      ) : (
                        <span className="tone-muted">chưa kiểm</span>
                      )}
                    </td>
                    <td>
                      {song ? (
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {t.status === "open" ? (
                            <button
                              className="btn btn-sm"
                              onClick={() => setActing({ ticket: t, action: "mark_fixed" })}
                            >
                              Đã sửa nguồn
                            </button>
                          ) : null}
                          {q.data?.can_set_blocking ? (
                            <button
                              className="btn btn-sm"
                              onClick={() => setActing({ ticket: t, action: "set_blocking" })}
                            >
                              {t.blocking ? "Gỡ chặn" : "Đặt chặn"}
                            </button>
                          ) : null}
                          <button
                            className="btn btn-sm"
                            onClick={() => setActing({ ticket: t, action: "cancel" })}
                          >
                            Huỷ
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
          <p className="spin" style={{ padding: 14 }}>
            Không có ticket nào ở trạng thái này.
          </p>
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

const TIEU_DE: Record<string, string> = {
  mark_fixed: "Báo đã sửa ở nguồn",
  set_blocking: "Đổi mức chặn phát hành",
  cancel: "Huỷ ticket — báo nhầm",
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

  return (
    <Modal title={`${TIEU_DE[action]} — #${ticket.id}`} onClose={onClose}>
      <p className="sub" style={{ marginBottom: 10 }}>
        {action === "mark_fixed" ? (
          <>
            Ticket chuyển sang <b>chờ QC xác minh</b>. Nó chỉ đóng khi lần nạp kế tiếp đọc được
            đúng <span className="mono">{ticket.expected_value}</span> ở ô{" "}
            <span className="mono">
              {ticket.state}/{ticket.gender}/{ticket.year}/{ticket.name}
            </span>
            . Lệch thì ticket tự bật lại kèm số đọc được.
          </>
        ) : action === "set_blocking" ? (
          ticket.blocking ? (
            <>
              Gỡ chặn nghĩa là <b>vẫn phát hành được</b> dù lỗi này chưa sửa. Lý do bạn ghi sẽ
              nằm trong audit log và ticket vẫn mở cho tới khi nguồn sửa.
            </>
          ) : (
            <>Đặt chặn nghĩa là không ai ký và không ai xuất file được cho tới khi nguồn sửa xong.</>
          )
        ) : (
          <>
            Huỷ dùng khi ticket mở nhầm — dữ liệu thật ra vẫn đúng. Nó không sửa gì ở nguồn và
            không xoá dấu vết.
          </>
        )}
      </p>
      <textarea
        rows={2}
        placeholder="Lý do — bắt buộc, vào audit log"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        style={{ width: "100%", marginBottom: 10 }}
      />
      <ErrBox error={m.error} />
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
        <button className="btn" onClick={onClose}>Thôi</button>
        <button
          className="btn btn-primary"
          disabled={reason.trim().length < 3 || m.isPending}
          onClick={() => m.mutate()}
        >
          {m.isPending ? "Đang gửi…" : "Xác nhận"}
        </button>
      </div>
    </Modal>
  );
}
