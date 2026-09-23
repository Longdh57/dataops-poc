"use client";

// Do tuoi du lieu + nut "Lam moi bang".
//
// "Lam moi bang" chay han Sync Job: doc lai BigQuery, dung bang staging,
// doi ten. Ton 30–60 giay va chi team lead / admin moi thay, nen co mot
// buoc hoi lai truoc khi goi. Banner "co lan nap moi" van co nut Tai lai
// rieng — cai do chi doc lai ban sao Postgres, khong cham BigQuery.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import { post } from "@/app/lib/api";
import { useMe, useVersion } from "@/app/lib/queries";

import { ErrBox, Modal } from "./bits";

export default function StatusStrip() {
  const { t, tn } = useI18n();
  const { ago, num } = useFmt();
  const { data: v } = useVersion();
  const { data: me } = useMe();
  const qc = useQueryClient();

  // Moc so sanh: lan nap dang duoc hien tren man hinh. Poll thay run_id
  // khac moc nay nghia la co du lieu moi — bao chu KHONG tu tai lai, vi
  // nguoi dung co the dang go do dang trong panel dieu tra.
  const [baseline, setBaseline] = useState<string | null>(null);
  useEffect(() => {
    if (v?.run_id && baseline === null) setBaseline(v.run_id);
  }, [v?.run_id, baseline]);

  const [asking, setAsking] = useState(false);
  const rebuild = useMutation({
    mutationFn: () => post<{ job: string; operation: string }>("/rebuild", {}),
    onSuccess: () => setAsking(false),
  });

  const hasNew = Boolean(baseline && v?.run_id && v.run_id !== baseline);
  const canRebuild = me?.roles?.some((r) => r === "team_lead" || r === "admin");

  function refreshView() {
    qc.invalidateQueries();
    if (v?.run_id) setBaseline(v.run_id);
  }

  return (
    <>
      <div
        style={{
          display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
          marginBottom: 14, fontSize: 12.5, color: "var(--muted)",
        }}
      >
        <span className="mono">
          {t("strip.run")} <b style={{ color: "var(--ink)" }}>{v?.run_id ?? "—"}</b>
        </span>
        <span>{t("strip.rows", { n: num(v?.row_count) })}</span>
        <span className={v?.stale ? "tone-crit" : "tone-good"}>
          {t("strip.syncedAgo", { age: ago(v?.age_seconds) })}
          {v?.stale ? t("strip.tooOld") : ""}
        </span>

        <span style={{ flex: 1 }} />

        {canRebuild ? (
          <button
            className="btn btn-sm btn-danger"
            onClick={() => setAsking(true)}
            title={t("strip.rebuildTitle")}
          >
            {t("strip.rebuild")}
          </button>
        ) : null}
      </div>

      {hasNew ? (
        <div className="banner" style={{ marginBottom: 16 }}>
          <div>
            <div className="banner-title">{t("strip.newRunTitle")}</div>
            <div className="banner-body">
              {tn("strip.newRunBody", {
                runId: <span className="mono">{v?.run_id}</span>,
                baseline: <span className="mono">{baseline}</span>,
              })}
            </div>
          </div>
          <button className="btn btn-primary btn-sm" onClick={refreshView}>
            {t("strip.reload")}
          </button>
        </div>
      ) : null}

      {asking ? (
        <Modal title={t("strip.confirmTitle")} onClose={() => setAsking(false)}>
          <p className="sub" style={{ marginBottom: 12 }}>
            {t("strip.confirmBody")}
          </p>
          <ErrBox error={rebuild.error} />
          <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
            <button className="btn" onClick={() => setAsking(false)}>
              {t("common.cancel")}
            </button>
            <button
              className="btn btn-danger"
              disabled={rebuild.isPending}
              onClick={() => rebuild.mutate()}
            >
              {rebuild.isPending ? t("strip.calling") : t("strip.runSyncJob")}
            </button>
          </div>
        </Modal>
      ) : null}

      {rebuild.isSuccess ? (
        <div className="banner banner-good" style={{ marginBottom: 16 }}>
          <div>
            <div className="banner-title">{t("strip.triggeredTitle")}</div>
            <div className="banner-body">{t("strip.triggeredBody")}</div>
          </div>
        </div>
      ) : null}
    </>
  );
}
