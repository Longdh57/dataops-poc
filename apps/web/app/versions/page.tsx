"use client";

// Trang phien ban: ky ban so lieu va tra loi cau hoi "so nay ho lay o dau".

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
  const [sending, setSending] = useState<SignedVersion | null>(null);

  const sign = useMutation({
    mutationFn: () => post<SignedVersion>("/release", { label: label.trim() }),
    onSuccess: () => {
      setLabel("");
      qc.invalidateQueries({ queryKey: ["versions"] });
      qc.invalidateQueries({ queryKey: ["gate"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    },
  });

  const locked = gate?.locked ?? false;

  return (
    <>
      <div className="card-head">
        <div>
          <h1>Phiên bản đã ký</h1>
          <p className="sub">
            Ký là đóng băng một lần nạp làm bản phát hành. File gửi khách chỉ xuất từ bản đã ký.
          </p>
        </div>
      </div>

      {q.data?.can_sign ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <h2>Ký bản mới</h2>
            {locked ? (
              <span className="pill pill-crit">cổng đang khoá · {num(gate?.blocking)} ngoại lệ</span>
            ) : (
              <span className="pill pill-good">cổng sẵn sàng</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder="Tên bản, ví dụ: Bao cao Q3 2026"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              style={{ flex: 1, minWidth: 260 }}
              disabled={locked}
            />
            <button
              className="btn btn-good"
              disabled={locked || label.trim().length < 3 || sign.isPending}
              onClick={() => sign.mutate()}
            >
              {sign.isPending ? "Đang ký…" : "Ký phát hành"}
            </button>
          </div>
          {locked ? (
            <p className="sub" style={{ marginTop: 9 }}>
              Còn {num(gate?.blocking)} ngoại lệ nghiêm trọng đang mở. Xử lý hết ở hộp thư ngoại lệ
              thì nút này mở — máy chủ cũng chặn, không chỉ giao diện.
            </p>
          ) : null}
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
                <th>Người ký</th>
                <th>Lúc</th>
                <th>Đã gửi cho</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((v) => (
                <tr key={v.id}>
                  <td style={{ color: "var(--ink)", fontWeight: 600 }}>{v.label}</td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {v.run_id}
                    <div className="tone-muted" style={{ fontSize: 11 }}>
                      {v.source_run_ids?.length
                        ? `${v.source_run_ids.length} lần nạp dữ liệu`
                        : "không ghi lại lần nạp — không xuất file được"}
                    </div>
                  </td>
                  <td className="num">{num(v.row_count)}</td>
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
