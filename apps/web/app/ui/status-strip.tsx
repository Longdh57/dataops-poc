"use client";

// Do tuoi du lieu + hai nut de nham la phien phuc.
//
// "Lam moi bang" doc lai ban sao Postgres — vai chuc mili giay, khong
// cham BigQuery. "Nap lai tu nguon" chay han Sync Job: doc lai BigQuery,
// dung bang staging, doi ten. Hai viec khac han nhau nen hai nut khac han
// nhau ve mau, chu va mot buoc hoi lai.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { post } from "@/app/lib/api";
import { ago, num } from "@/app/lib/format";
import { useMe, useVersion } from "@/app/lib/queries";

import { ErrBox, Modal } from "./bits";

export default function StatusStrip() {
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
          Lần nạp <b style={{ color: "var(--ink)" }}>{v?.run_id ?? "—"}</b>
        </span>
        <span>{num(v?.row_count)} dòng</span>
        <span className={v?.stale ? "tone-crit" : "tone-good"}>
          đồng bộ cách đây {ago(v?.age_seconds)}
          {v?.stale ? " — quá cũ" : ""}
        </span>

        <span style={{ flex: 1 }} />

        <button className="btn btn-sm" onClick={refreshView} title="Đọc lại bản sao Postgres — tức thì, không chạm BigQuery">
          Làm mới bảng
        </button>
        {canRebuild ? (
          <button
            className="btn btn-sm btn-danger"
            onClick={() => setAsking(true)}
            title="Chạy lại Sync Job: đọc lại toàn bộ từ BigQuery"
          >
            Nạp lại từ nguồn
          </button>
        ) : null}
      </div>

      {hasNew ? (
        <div className="banner" style={{ marginBottom: 16 }}>
          <div>
            <div className="banner-title">Có lần nạp mới trên BigQuery</div>
            <div className="banner-body">
              Bản sao vừa đổi sang <span className="mono">{v?.run_id}</span>. Màn hình vẫn giữ
              số của <span className="mono">{baseline}</span> cho tới khi bạn bấm tải lại.
            </div>
          </div>
          <button className="btn btn-primary btn-sm" onClick={refreshView}>
            Tải lại
          </button>
        </div>
      ) : null}

      {asking ? (
        <Modal title="Nạp lại từ nguồn?" onClose={() => setAsking(false)}>
          <p className="sub" style={{ marginBottom: 12 }}>
            Việc này <b>không giống</b> Làm mới bảng. Nó chạy lại Sync Job: đọc toàn bộ bảng
            fact từ BigQuery, ghi ra parquet, nạp vào bảng staging rồi đổi tên. Mất khoảng
            30–60 giây và chỉ cần làm khi nghi bản sao lệch so với nguồn.
          </p>
          <ErrBox error={rebuild.error} />
          <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
            <button className="btn" onClick={() => setAsking(false)}>
              Thôi
            </button>
            <button
              className="btn btn-danger"
              disabled={rebuild.isPending}
              onClick={() => rebuild.mutate()}
            >
              {rebuild.isPending ? "Đang gọi…" : "Chạy Sync Job"}
            </button>
          </div>
        </Modal>
      ) : null}

      {rebuild.isSuccess ? (
        <div className="banner banner-good" style={{ marginBottom: 16 }}>
          <div>
            <div className="banner-title">Sync Job đã được kích hoạt</div>
            <div className="banner-body">
              Khi job xong, banner độ tươi ở trên sẽ báo có lần nạp mới.
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
