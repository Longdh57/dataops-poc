"use client";

import type { ReactNode } from "react";

export function Stat({
  label, value, note, tone, small,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "good" | "warn" | "crit";
  small?: boolean;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value${small ? " sm" : ""}${tone ? ` tone-${tone}` : ""}`}>{value}</div>
      {note ? <div className="stat-note">{note}</div> : null}
    </div>
  );
}

export function Severity({ value }: { value: string }) {
  const map: Record<string, [string, string]> = {
    critical: ["pill pill-crit", "nghiêm trọng"],
    warning: ["pill pill-warn", "cảnh báo"],
  };
  const [cls, label] = map[value] ?? ["pill", value];
  return <span className={cls}>{label}</span>;
}

export function Status({ value }: { value: string }) {
  const map: Record<string, [string, string]> = {
    open: ["pill pill-warn", "đang mở"],
    awaiting_verify: ["pill pill-accent", "chờ QC xác minh"],
    closed: ["pill pill-good", "đã đóng"],
    cancelled: ["pill", "huỷ"],
    pending: ["pill pill-warn", "chờ chạy"],
    running: ["pill pill-accent", "đang chạy"],
    done: ["pill pill-good", "xong"],
    error: ["pill pill-crit", "lỗi"],
  };
  const [cls, label] = map[value] ?? ["pill", value];
  return <span className={cls}>{label}</span>;
}

export const Loading = ({ what = "dữ liệu" }: { what?: string }) => (
  <p className="spin">Đang tải {what}…</p>
);

export function ErrBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as { status?: number; detail?: unknown; message?: string };
  const body =
    typeof e.detail === "string"
      ? e.detail
      : e.detail
        ? JSON.stringify(e.detail)
        : (e.message ?? String(error));
  return (
    <div className="err">
      {e.status ? <b>{e.status}</b> : null} {body}
    </div>
  );
}

export function Modal({
  title, children, onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginBottom: 10 }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}
