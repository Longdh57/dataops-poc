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

import { gw, post } from "@/app/lib/api";
import { dt, num } from "@/app/lib/format";
import { useGate } from "@/app/lib/queries";
import type { SignedVersion } from "@/app/lib/types";
import { ErrBox, Loading, Modal } from "@/app/ui/bits";

type Res = { rows: SignedVersion[]; can_sign: boolean };

export default function VersionsPage() {
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
          <h1>Phiên bản đã ký</h1>
          <p className="sub">
            Ký là đóng băng một lần nạp làm bản phát hành. File gửi khách chỉ xuất từ bản đã ký,
            và mang theo đúng món nợ ghi ở đây.
          </p>
        </div>
      </div>

      {q.data?.can_sign ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <h2>Ký bản mới</h2>
            {locked ? (
              <span className="pill pill-crit">
                {stale ? "QC chưa kiểm lần nạp này" : `${chan.length} ticket đang chặn`}
              </span>
            ) : canNo ? (
              <span className="pill pill-warn">ký được, nhưng còn nợ</span>
            ) : (
              <span className="pill pill-good">sạch</span>
            )}
          </div>

          {/* --- mon no, bay ra truoc khi ai do dung ten --- */}
          <Debt gate={gate} />

          {locked ? (
            <div className="banner banner-crit" style={{ marginBottom: 12, display: "block" }}>
              <div className="banner-title">
                {stale ? "Danh sách vi phạm đang hiển thị là của lần nạp trước" : "Bị chặn bởi ticket"}
              </div>
              <div className="banner-body">
                {stale ? (
                  <>
                    Lần nạp hiện tại là <span className="mono">{gate?.run_id}</span> nhưng QC mới
                    kiểm tới <span className="mono">{gate?.qc_run_id ?? "—"}</span>. Ký lúc này là
                    ký một thứ chưa ai nhìn thấy, nên máy chủ từ chối. QC chạy mỗi 5 phút.
                  </>
                ) : (
                  <>
                    Đây là lỗi đã xác nhận bằng bằng chứng, không phải nghi ngờ của máy — nên
                    không duyệt cho qua được. Sửa ở nguồn rồi chờ QC xác minh, hoặc gỡ chặn từng
                    ticket ở trang Ticket.
                    <ul style={{ margin: "6px 0 0 18px" }}>
                      {chan.slice(0, 8).map((t) => (
                        <li key={t.id}>
                          <span className="mono">#{t.id}</span> · {t.khoa} — {t.title}
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
              placeholder="Tên bản, ví dụ: Bao cao Q3 2026"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              style={{ flex: 1, minWidth: 260 }}
              disabled={locked}
            />
          </div>

          {canNo && !locked ? (
            <div style={{ marginTop: 10 }}>
              <label htmlFor="note" className="stat-label" style={{ display: "block", marginBottom: 4 }}>
                Phiếu duyệt — bắt buộc
              </label>
              <textarea
                id="note"
                rows={3}
                placeholder="Vì sao vẫn ký dù còn nợ. Ví dụ: 3 ô dưới ngưỡng là số thật của bang nhỏ, đã đối chiếu SSA. Ticket #123 không ảnh hưởng bang đang bán."
                value={note}
                onChange={(e) => setNote(e.target.value)}
                style={{ width: "100%" }}
              />
              <p className="sub" style={{ marginTop: 4 }}>
                Câu này đi theo bản ký vĩnh viễn và in vào file gửi khách. Tên bạn nằm cạnh nó.
              </p>
            </div>
          ) : null}

          <div style={{ marginTop: 10 }}>
            <button
              className="btn btn-good"
              disabled={locked || label.trim().length < 3 || !duNote || sign.isPending}
              onClick={() => sign.mutate()}
            >
              {sign.isPending ? "Đang ký…" : canNo ? "Ký kèm phiếu duyệt" : "Ký phát hành"}
            </button>
          </div>

          <div style={{ marginTop: 9 }}>
            <ErrBox error={sign.error} />
          </div>
        </div>
      ) : null}

      <div className="card card-pad0">
        {q.isPending ? (
          <div style={{ padding: 14 }}><Loading what="phiên bản" /></div>
        ) : q.data?.rows.length ? (
          <table className="t">
            <thead>
              <tr>
                <th>Bản</th>
                <th>Lần nạp</th>
                <th className="num">Số dòng</th>
                <th>Nợ lúc ký</th>
                <th>Người ký</th>
                <th>Lúc</th>
                <th>Đã gửi cho</th>
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
                        vân tay {v.checksum.slice(0, 12)}
                      </div>
                    ) : (
                      <div className="tone-muted" style={{ fontSize: 10.5, fontWeight: 400 }}>
                        không có vân tay — ký trước P6
                      </div>
                    )}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {v.run_id}
                    <div className="tone-muted" style={{ fontSize: 11 }}>
                      {v.source_run_ids?.length
                        ? `${v.source_run_ids.length} lần nạp dữ liệu`
                        : "không ghi lại lần nạp — không xuất file được"}
                      {v.rules_version ? ` · luật v${v.rules_version}` : ""}
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
                      <span className="tone-muted">chưa gửi ai</span>
                    )}
                  </td>
                  <td>
                    <button className="btn btn-sm" onClick={() => setSending(v)}>
                      Ghi nhận đã gửi
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="spin" style={{ padding: 14 }}>
            Chưa có bản nào được ký.
          </p>
        )}
      </div>

      {sending ? <SendModal version={sending} onClose={() => setSending(null)} /> : null}
    </>
  );
}

// --------------------------------------------------------- mon no truoc ky

function Debt({ gate }: { gate: ReturnType<typeof useGate>["data"] }) {
  if (!gate) return null;
  const v = gate.violations;
  const truoc = gate.last_signed;

  return (
    <div style={{ marginBottom: 12 }}>
      <div className="compare" style={{ marginBottom: 10 }}>
        <div>
          <div className="stat-label">Vi phạm luật ở lần nạp này</div>
          <div className="big">{num(v.total)}</div>
          <div className="stat-note">
            {v.by_severity.critical ? `${num(v.by_severity.critical)} nghiêm trọng · ` : ""}
            {v.by_severity.warning ? `${num(v.by_severity.warning)} cảnh báo` : "không có cảnh báo"}
          </div>
        </div>
        <div>
          <div className="stat-label">Ticket chưa đóng</div>
          <div className="big">{num(gate.open_tickets)}</div>
          <div className="stat-note">
            {gate.blocking_tickets.length
              ? `${gate.blocking_tickets.length} trong số đó đang chặn`
              : "không cái nào chặn phát hành"}
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
          So với bản ký gần nhất (<b>{truoc.label}</b>):{" "}
          {truoc.violations_fingerprint && truoc.violations_fingerprint === v.fingerprint ? (
            <>đúng cùng một tập vi phạm, không có gì mới.</>
          ) : truoc.violations_fingerprint ? (
            <b className="tone-crit">tập vi phạm đã khác — có cái mới hoặc cái cũ đã hết.</b>
          ) : (
            <>bản trước không ghi vân tay nên không so được.</>
          )}
        </p>
      ) : null}
    </div>
  );
}

function No({ version }: { version: SignedVersion }) {
  const vi = version.violations ?? {};
  const tk = version.open_tickets ?? [];
  const tong = Object.values(vi).reduce((a, b) => a + b, 0);

  if (!tong && !tk.length) {
    return <span className="pill pill-good">sạch</span>;
  }
  return (
    <>
      {tong ? (
        <div>
          <span className="pill pill-warn">{num(tong)} vi phạm</span>{" "}
          <span className="tone-muted" style={{ fontSize: 11 }}>
            {Object.keys(vi).join(", ")}
          </span>
        </div>
      ) : null}
      {tk.length ? (
        <div style={{ marginTop: 3 }}>
          <span className="pill pill-accent">ticket {tk.map((t) => `#${t}`).join(", ")}</span>
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
    <Modal title={`Ghi nhận đã gửi — ${version.label}`} onClose={onClose}>
      <p className="sub" style={{ marginBottom: 10 }}>
        Ghi lại đã gửi bản nào cho khách nào ngày nào. Dòng này không xoá được.
      </p>
      <input
        type="text"
        placeholder="Tên khách hàng"
        value={customer}
        onChange={(e) => setCustomer(e.target.value)}
        style={{ width: "100%", marginBottom: 10 }}
      />
      <ErrBox error={m.error} />
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
        <button className="btn" onClick={onClose}>Thôi</button>
        <button
          className="btn btn-primary"
          disabled={customer.trim().length < 2 || m.isPending}
          onClick={() => m.mutate()}
        >
          Ghi nhận
        </button>
      </div>
    </Modal>
  );
}
