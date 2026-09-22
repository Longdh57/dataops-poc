"use client";

import type { ReactNode } from "react";

import { useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";

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

// Gia tri gui len tu API van la ma tieng Anh (critical, open, …) — chi
// nhan hien ra man hinh moi doi theo ngon ngu. Khong co khoa dich thi
// hien nguyen ma, con hon o trong.
const SEVERITY: Record<string, [string, MessageKey]> = {
  critical: ["pill pill-crit", "severity.critical"],
  warning: ["pill pill-warn", "severity.warning"],
};

export function Severity({ value }: { value: string }) {
  const { t } = useI18n();
  const hit = SEVERITY[value];
  return <span className={hit ? hit[0] : "pill"}>{hit ? t(hit[1]) : value}</span>;
}

const STATUS: Record<string, [string, MessageKey]> = {
  open: ["pill pill-warn", "status.open"],
  awaiting_verify: ["pill pill-accent", "status.awaiting_verify"],
  closed: ["pill pill-good", "status.closed"],
  cancelled: ["pill", "status.cancelled"],
  pending: ["pill pill-warn", "status.pending"],
  running: ["pill pill-accent", "status.running"],
  done: ["pill pill-good", "status.done"],
  error: ["pill pill-crit", "status.error"],
};

export function Status({ value }: { value: string }) {
  const { t } = useI18n();
  const hit = STATUS[value];
  return <span className={hit ? hit[0] : "pill"}>{hit ? t(hit[1]) : value}</span>;
}

export function Loading({ what }: { what?: string }) {
  const { t } = useI18n();
  return <p className="spin">{t("common.loading", { what: what ?? t("common.data") })}</p>;
}

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
  title: ReactNode;
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
