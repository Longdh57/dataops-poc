"use client";

// Form them / sua mot luat QC (P10). Nam TRONG hop "Bo luat QC", thay cho
// danh sach — khong mo hop chong hop.
//
// Hai nut co chu dich khac nhau: "Thu SQL" cho nguoi sua THAY luat bat
// duoc gi truoc khi luu; "Luu" thi server chay thu lai lan nua roi moi
// ghi — ket qua thu o client khong duoc tin.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import { ApiError, post, put } from "@/app/lib/api";
import { useOptions } from "@/app/lib/queries";
import type { QcRule, RulePreview, RulesConflict } from "@/app/lib/types";

import { ErrBox } from "./bits";

const SEVERITIES = ["critical", "warning", "info"] as const;

const SQL_TEMPLATE = `SELECT year, state, institution_id, institution,
       jsonb_build_object('deposit', deposit) AS observed
FROM fact_current
WHERE deposit <= 0`;

export default function RuleForm({
  rule, version, onSaved, onCancel, reload,
}: {
  /** null = them luat moi. */
  rule: QcRule | null;
  /** Version bo luat luc mo form — gui kem de server bat hai nguoi sua cung luc. */
  version: number;
  onSaved: (newVersion: number) => void;
  onCancel: () => void;
  /** Tai lai catalog sau 409, tra version moi. */
  reload: () => Promise<number | null>;
}) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data: options } = useOptions();

  const [base, setBase] = useState(version);
  const [id, setId] = useState(rule?.id ?? "");
  const [severity, setSeverity] = useState<string>(rule?.severity ?? "warning");
  const [scope, setScope] = useState<string[]>(rule?.scope ?? []);
  const [message, setMessage] = useState(rule?.message ?? "");
  const [sql, setSql] = useState(rule?.sql ?? SQL_TEMPLATE);
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);

  const preview = useMutation({
    mutationFn: () =>
      post<RulePreview>("/rules/preview", { sql, scope: scope.length ? scope : null }),
  });

  const save = useMutation({
    mutationFn: () => {
      const body = {
        severity, message, sql, enabled,
        scope: scope.length ? scope : null,
        expected_version: base,
      };
      return rule
        ? put<{ version: number }>(`/rules/${encodeURIComponent(rule.id)}`, body)
        : post<{ version: number }>("/rules", { ...body, id: id.trim() });
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["rules"] });
      // Bo luat doi -> cong khoa ("QC chua chay duoi bo luat hien tai")
      qc.invalidateQueries({ queryKey: ["gate"] });
      onSaved(res.version);
    },
  });

  // Bang ngoai pham vi van phai chon duoc: luat la quy tac chung. Nguoi sua
  // luat la team_lead / admin nen thuong thay du moi bang.
  const states = Array.from(new Set([...(options?.states ?? []), ...scope])).sort();
  const toggle = (s: string) =>
    setScope((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const canSave = (rule || id.trim()) && message.trim() && sql.trim() && !save.isPending;

  return (
    <div className="rule-form">
      <div>
        <label className="lbl" htmlFor="rf-id">{t("rules.form.id")}</label>
        <input
          id="rf-id" type="text" className="mono" value={id} disabled={Boolean(rule)}
          placeholder="deposit_share_over_100"
          onChange={(e) => setId(e.target.value.toLowerCase())}
        />
        {!rule ? <div className="hint">{t("rules.form.idHint")}</div> : null}
      </div>

      <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
        <div>
          <label className="lbl" htmlFor="rf-sev">{t("rules.form.severity")}</label>
          <select id="rf-sev" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div style={{ flex: 1, minWidth: 220 }}>
          <span className="lbl">{t("rules.form.scope")}</span>
          <div className="scope-grid">
            {states.map((s) => (
              <label key={s}>
                <input type="checkbox" checked={scope.includes(s)} onChange={() => toggle(s)} />
                <span className="mono">{s}</span>
              </label>
            ))}
          </div>
          <div className="hint">{t("rules.form.scopeHint")}</div>
        </div>
      </div>

      <div>
        <label className="lbl" htmlFor="rf-msg">{t("rules.form.message")}</label>
        <input id="rf-msg" type="text" value={message} onChange={(e) => setMessage(e.target.value)} />
        <div className="hint">{t("rules.form.messageHint")}</div>
      </div>

      <div>
        <label className="lbl" htmlFor="rf-sql">{t("rules.form.sql")}</label>
        <textarea
          id="rf-sql" className="sql" spellCheck={false} value={sql}
          onChange={(e) => setSql(e.target.value)}
        />
        <div className="hint">{t("rules.form.sqlHint")}</div>
      </div>

      <label className="check">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        {t("rules.form.enabled")}
      </label>

      <PreviewResult preview={preview.data} error={preview.error} />

      <SaveError
        error={save.error}
        onReload={async () => {
          const v = await reload();
          if (v !== null) setBase(v);
          save.reset();
        }}
      />

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button type="button" className="btn" onClick={onCancel}>{t("rules.form.back")}</button>
        <button
          type="button" className="btn" disabled={!sql.trim() || preview.isPending}
          onClick={() => preview.mutate()}
        >
          {preview.isPending ? t("rules.form.previewing") : t("rules.form.preview")}
        </button>
        <button
          type="button" className="btn btn-primary" disabled={!canSave}
          onClick={() => save.mutate()}
        >
          {save.isPending ? t("rules.form.saving") : t("rules.form.save")}
        </button>
      </div>
    </div>
  );
}

function PreviewResult({ preview, error }: { preview?: RulePreview; error: unknown }) {
  const { t } = useI18n();
  const { num } = useFmt();
  if (error) return <ErrBox error={error} />;
  if (!preview) return null;

  if (preview.error) {
    return <div className="err">{t("rules.preview.error", { err: preview.error })}</div>;
  }
  if (preview.missing_columns.length) {
    return (
      <div className="err">
        {t("rules.preview.missing", { cols: preview.missing_columns.join(", ") })}
      </div>
    );
  }
  return (
    <div className="preview-box">
      <div className="tone-good" style={{ fontSize: 12.5, fontWeight: 600 }}>
        {t("rules.preview.ok", { n: num(preview.count), ms: preview.ms ?? "—" })}
      </div>
      {preview.rows.length ? (
        <>
          <div className="tone-muted" style={{ fontSize: 11.5, marginTop: 6 }}>
            {t("rules.preview.sample", { n: preview.rows.length })}
          </div>
          <table className="t">
            <tbody>
              {preview.rows.map((r, i) => (
                <tr key={i}>
                  <td className="mono">{r.year ?? "—"}</td>
                  <td className="mono">{r.state ?? "—"}</td>
                  <td>{r.institution ?? "—"}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{JSON.stringify(r.observed)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </div>
  );
}

/** 422 hien tung loi; 409 noi ai vua sua va cho tai lai ma giu form. */
export function SaveError({ error, onReload }: { error: unknown; onReload: () => void }) {
  const { t } = useI18n();
  const { dt } = useFmt();
  if (!error) return null;

  if (error instanceof ApiError && error.status === 409) {
    const d = error.detail as Partial<RulesConflict> | string;
    if (typeof d === "object" && d?.current_version) {
      return (
        <div className="banner banner-warn">
          <div className="banner-body">
            {t("rules.conflict", {
              who: d.updated_by ?? "—", when: dt(d.updated_at), v: d.current_version,
            })}
          </div>
          <button type="button" className="btn btn-sm" onClick={onReload}>
            {t("rules.reload")}
          </button>
        </div>
      );
    }
  }
  if (error instanceof ApiError && error.status === 422) {
    const d = error.detail as { errors?: string[] } | unknown;
    const errors = (d as { errors?: string[] })?.errors;
    if (Array.isArray(errors)) {
      return (
        <div className="err">
          {errors.map((m) => <div key={m}>{m}</div>)}
        </div>
      );
    }
  }
  return <ErrBox error={error} />;
}
