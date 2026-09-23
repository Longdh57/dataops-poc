"use client";

// Nut "Xem bo luat" + hop bo luat QC.
//
// Man hinh nay tra loi cau "luat nay la gi", va tu P10 con la cho SUA
// luat: team_lead / admin them, sua, tat, xoa ngay tai day, co hieu luc o
// lan QC ke tiep. Nguoi khac chi doc — luat la quy tac chung, ai cung can
// doi chieu duoc rule_id tren bang vi pham voi luat that.
//
// Hai cach doc, va giu ca hai co chu dich: DANH SACH de tra cuu nhanh
// tung luat, YAML de doi chieu nguyen van va tai ve lam file seed.
//
// Cung hop nay mo o che do SNAPSHOT tu trang Phien ban: bo luat dung nhu
// luc mot ban ky duoc duyet, chi doc.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import { del, post } from "@/app/lib/api";
import { useRules } from "@/app/lib/queries";
import type { QcRule, RulesCatalog } from "@/app/lib/types";

import { ErrBox, Loading, Modal, Severity } from "./bits";
import RuleForm, { SaveError } from "./rule-form";

export default function RulesButton({ counts }: {
  /** {rule_id: so vi pham o lan nap hien tai} — co thi hien kem moi luat. */
  counts?: Record<string, number>;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" className="btn btn-sm" onClick={() => setOpen(true)}>
        {t("rules.button")}
      </button>
      {open ? <RulesModal counts={counts} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

type Mode =
  | { kind: "list" }
  | { kind: "form"; rule: QcRule | null }
  | { kind: "delete"; rule: QcRule };

export function RulesModal({
  counts, onClose, version,
}: {
  counts?: Record<string, number>;
  onClose: () => void;
  /** Co = xem snapshot mot version cu, chi doc. */
  version?: number | null;
}) {
  const { t } = useI18n();
  const { dt } = useFmt();
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [saved, setSaved] = useState<number | null>(null);
  // Hop chi duoc dung len khi nguoi dung bam nut, nen API cung chi bi goi
  // luc do — bo luat khong nam trong duong tai cua moi trang.
  const { data, isPending, error, refetch } = useRules(version);

  const reload = async () => (await refetch()).data?.version ?? null;

  const title =
    data?.snapshot && data.version !== null
      ? t("rules.snapshotTitle", { v: data.version })
      : mode.kind === "form"
        ? mode.rule
          ? t("rules.form.editTitle", { id: mode.rule.id })
          : t("rules.form.newTitle")
        : mode.kind === "delete"
          ? t("rules.confirmDeleteTitle", { id: mode.rule.id })
          : t("rules.title");

  return (
    <Modal wide title={title} onClose={onClose}>
      {error ? <ErrBox error={error} /> : null}
      {isPending && !error ? <Loading what={t("rules.loading")} /> : null}

      {data && mode.kind === "form" && data.version !== null ? (
        <RuleForm
          rule={mode.rule}
          version={data.version}
          reload={reload}
          onCancel={() => setMode({ kind: "list" })}
          onSaved={(v) => {
            setSaved(v);
            setMode({ kind: "list" });
          }}
        />
      ) : null}

      {data && mode.kind === "delete" ? (
        <DeleteConfirm
          rule={mode.rule}
          version={data.version ?? 0}
          hits={counts?.[mode.rule.id]}
          reload={reload}
          onCancel={() => setMode({ kind: "list" })}
          onDeleted={(v) => {
            setSaved(v);
            setMode({ kind: "list" });
          }}
        />
      ) : null}

      {data && mode.kind === "list" ? (
        <RulesList
          data={data}
          counts={counts}
          saved={saved}
          onAdd={() => { setSaved(null); setMode({ kind: "form", rule: null }); }}
          onEdit={(rule) => { setSaved(null); setMode({ kind: "form", rule }); }}
          onDelete={(rule) => { setSaved(null); setMode({ kind: "delete", rule }); }}
          dt={dt}
        />
      ) : null}

      {mode.kind === "list" ? (
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
          <button type="button" className="btn" onClick={onClose}>{t("common.close")}</button>
        </div>
      ) : null}
    </Modal>
  );
}

function RulesList({
  data, counts, saved, onAdd, onEdit, onDelete, dt,
}: {
  data: RulesCatalog;
  counts?: Record<string, number>;
  saved: number | null;
  onAdd: () => void;
  onEdit: (r: QcRule) => void;
  onDelete: (r: QcRule) => void;
  dt: (iso: string | null | undefined) => string;
}) {
  const { t } = useI18n();
  const [raw, setRaw] = useState(false);
  const qc = useQueryClient();

  const runQc = useMutation({
    mutationFn: () => post<{ job: string }>("/rules/run-qc", {}),
  });

  // Vi pham mang rule_id cua luat da bi xoa sau lan QC do — van hien, kem
  // nhan, chu khong lang le bo di: so nay VAN nam trong danh sach vi pham.
  const known = new Set(data.rules.map((r) => r.id));
  const orphans = counts
    ? Object.entries(counts).filter(([id, n]) => n > 0 && !known.has(id))
    : [];

  function download() {
    const blob = new Blob([data.raw], { type: "text/yaml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.snapshot ? `rules-v${data.version}.yaml` : "rules.yaml";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 10 }}>
        <p className="sub" style={{ flex: 1 }}>
          {t("rules.sub", { n: data.rules.length, v: data.version ?? "—", file: data.source })}
          {/* So vi pham di kem la so TRONG PHAM VI va bo loc dang bat,
              khong phai so toan cuc — noi ro de khong bi doc nham. */}
          {counts && !data.snapshot ? ` · ${t("rules.countsNote")}` : null}
          {!data.snapshot && data.updated_by
            ? ` ${t("rules.editedBy", { who: data.updated_by, when: dt(data.updated_at) })}`
            : null}
        </p>
        {data.can_edit ? (
          <button type="button" className="btn btn-sm btn-primary" onClick={onAdd}>
            {t("rules.add")}
          </button>
        ) : null}
      </div>

      {data.snapshot ? (
        <div className="banner" style={{ marginBottom: 12 }}>
          <div className="banner-body">
            {t("rules.snapshotNote", {
              v: data.version ?? "—", when: dt(data.updated_at), who: data.updated_by ?? "—",
            })}
          </div>
        </div>
      ) : null}

      {saved !== null ? (
        <div className="banner banner-good" style={{ marginBottom: 12 }}>
          <div className="banner-body">{t("rules.saved", { v: saved })}</div>
        </div>
      ) : null}

      {/* Bo luat hien tai khac bo luat QC da chay = danh sach vi pham tren
          man hinh duoc sinh ra duoi mot bo luat KHAC cai dang doc. Im lang
          o day thi nguoi doc doi chieu nham. */}
      {!data.snapshot && !data.in_sync ? (
        <div className="banner banner-warn" style={{ marginBottom: 12 }}>
          <div>
            <div className="banner-body">
              {t("rules.outOfSync", {
                file: data.current_version ?? "—",
                applied: data.applied_version ?? "—",
              })}
            </div>
            {runQc.isSuccess ? (
              <div className="banner-body" style={{ marginTop: 6 }}>{t("rules.runQcNote")}</div>
            ) : null}
            <ErrBox error={runQc.error} />
          </div>
          {data.can_edit ? (
            <button
              type="button" className="btn btn-sm" disabled={runQc.isPending}
              onClick={() => runQc.mutate(undefined, {
                // Banner do tuoi / cong se doi khi QC xong — cho lan poll sau.
                onSuccess: () => qc.invalidateQueries({ queryKey: ["gate"] }),
              })}
            >
              {runQc.isPending ? t("rules.runQcRunning") : t("rules.runQc")}
            </button>
          ) : null}
        </div>
      ) : null}

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div className="langswitch">
          <button type="button" className="langswitch-btn" data-on={raw ? "0" : "1"}
                  onClick={() => setRaw(false)}>
            {t("rules.tab.list")}
          </button>
          <button type="button" className="langswitch-btn" data-on={raw ? "1" : "0"}
                  onClick={() => setRaw(true)}>
            {t("rules.tab.raw")}
          </button>
        </div>
        {raw ? (
          <button type="button" className="btn btn-sm" onClick={download}>
            {t("rules.download")}
          </button>
        ) : null}
      </div>

      {raw ? (
        <pre className="code-block">{data.raw}</pre>
      ) : (
        <div className="rule-list">
          {/* Luat khong co trong bang dem la luat khong bat duoc o nao
              — QC chay HET moi luat dang bat, nen vang mat nghia la 0. */}
          {data.rules.map((r) => (
            <RuleItem
              key={r.id} rule={r} canEdit={data.can_edit}
              n={counts && !data.snapshot ? (counts[r.id] ?? 0) : undefined}
              onEdit={() => onEdit(r)} onDelete={() => onDelete(r)}
            />
          ))}
          {!data.snapshot && orphans.map(([id, n]) => (
            <div key={id} className="rule rule-deleted">
              <div className="rule-head">
                <span className="mono rule-id">{id}</span>
                <span className="pill">{t("rules.deleted")}</span>
                <span className="pill pill-warn">{t("rules.hits", { n, count: n })}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function RuleItem({
  rule, n, canEdit, onEdit, onDelete,
}: {
  rule: QcRule;
  n?: number;
  canEdit: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const off = rule.enabled === false;
  return (
    <div className={`rule${off ? " rule-off" : ""}`}>
      <div className="rule-head">
        <span className="mono rule-id">{rule.id}</span>
        <Severity value={rule.severity} />
        <span className="pill">
          {rule.scope ? t("rules.scope", { states: rule.scope.join(", ") }) : t("rules.scopeAll")}
        </span>
        {off ? <span className="pill">{t("rules.disabled")}</span> : null}
        {/* Khong co so = khong biet, khac han voi biet la 0. Chi hien khi
            nguoi goi truyen bang dem xuong. */}
        {n !== undefined && !off ? (
          <span className={`pill ${n ? "pill-warn" : "pill-good"}`}>
            {n ? t("rules.hits", { n, count: n }) : t("rules.noHits")}
          </span>
        ) : null}
        {canEdit ? (
          <span className="rule-actions">
            <button type="button" className="btn btn-sm" onClick={onEdit}>{t("rules.edit")}</button>
            <button type="button" className="btn btn-sm btn-danger" onClick={onDelete}>
              {t("rules.delete")}
            </button>
          </span>
        ) : null}
      </div>
      <p className="rule-msg">{rule.message}</p>
      <details>
        <summary>{t("rules.showSql")}</summary>
        <pre className="code-block">{rule.sql}</pre>
      </details>
    </div>
  );
}

function DeleteConfirm({
  rule, version, hits, reload, onCancel, onDeleted,
}: {
  rule: QcRule;
  version: number;
  hits?: number;
  reload: () => Promise<number | null>;
  onCancel: () => void;
  onDeleted: (v: number) => void;
}) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [base, setBase] = useState(version);
  const m = useMutation({
    mutationFn: () =>
      del<{ version: number }>(
        `/rules/${encodeURIComponent(rule.id)}?expected_version=${base}`),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["rules"] });
      qc.invalidateQueries({ queryKey: ["gate"] });
      onDeleted(res.version);
    },
  });

  return (
    <>
      <p className="sub" style={{ marginBottom: 12 }}>
        {hits ? `${t("rules.confirmDeleteHits", { n: hits, count: hits })} ` : null}
        {t("rules.confirmDeleteBody")}
      </p>
      <SaveError
        error={m.error}
        onReload={async () => {
          const v = await reload();
          if (v !== null) setBase(v);
          m.reset();
        }}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
        <button type="button" className="btn" onClick={onCancel}>{t("common.cancel")}</button>
        <button
          type="button" className="btn btn-danger" disabled={m.isPending}
          onClick={() => m.mutate()}
        >
          {m.isPending ? t("common.sending") : t("rules.delete")}
        </button>
      </div>
    </>
  );
}
