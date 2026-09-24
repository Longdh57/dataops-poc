"use client";

// Nguoi dung & phan quyen.
//
// Quyen nghiep vu cua ung dung nam trong Postgres (app_user + app_role),
// khong nam trong IAM — IAM chi quyet dinh ai vao duoc cong. Truoc man
// hinh nay, them mot nguoi la mo psql go INSERT tay theo docs/runbook.md.
//
// Mot dieu man hinh nay khong giau: pham vi rong = KHONG GIOI HAN. Cot
// "Pham vi" viet han chu "tat ca" chu khong de trong, vi mot o trong rat
// de doc nham thanh "chua cap gi".

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import { ApiError, del } from "@/app/lib/api";
import { useMe, useUsers } from "@/app/lib/queries";
import type { AppUser } from "@/app/lib/types";
import { ErrBox, Loading, Modal } from "@/app/ui/bits";
import UserForm, { ROLE_NOTE } from "@/app/ui/user-form";

export default function UsersPage() {
  const { t } = useI18n();
  const { dt } = useFmt();
  const qc = useQueryClient();
  const { data: me } = useMe();
  const q = useUsers();

  // null = chua mo form; {user: null} = them moi.
  const [editing, setEditing] = useState<{ user: AppUser | null } | null>(null);
  const [removing, setRemoving] = useState<AppUser | null>(null);

  const remove = useMutation({
    mutationFn: (u: AppUser) => del<{ id: number }>(`/users/${u.id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setRemoving(null);
    },
  });

  const rows = q.data?.rows ?? [];
  // Endpoint chi mo cho admin. Vai tro khac vao thang duong dan nay se an
  // 403 — noi thang ra la vi sao, dung de mot bang rong kho hieu.
  const denied = q.error instanceof ApiError && q.error.status === 403;

  return (
    <>
      <div className="card-head">
        <div>
          <h1>{t("users.title")}</h1>
          <p className="sub">{t("users.sub")}</p>
        </div>
        {!denied ? (
          <button className="btn btn-primary" onClick={() => setEditing({ user: null })}>
            {t("users.add")}
          </button>
        ) : null}
      </div>

      {denied ? (
        <div className="banner banner-warn">
          <div className="banner-body">{t("users.adminOnly")}</div>
        </div>
      ) : null}

      {!denied ? <ErrBox error={q.error} /> : null}

      <div className="card card-pad0" style={{ display: denied ? "none" : undefined }}>
        {q.isLoading ? (
          <Loading what={t("users.loading")} />
        ) : (
          <table className="t">
            <thead>
              <tr>
                <th>{t("users.col.name")}</th>
                <th>{t("users.col.email")}</th>
                <th>{t("users.col.role")}</th>
                <th>{t("users.col.scope")}</th>
                <th>{t("users.col.state")}</th>
                <th>{t("users.col.createdAt")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.55 }}>
                  <td>
                    {u.display_name || "—"}
                    {u.email === me?.email ? (
                      <span className="pill" style={{ marginLeft: 6 }}>{t("users.you")}</span>
                    ) : null}
                  </td>
                  <td className="mono">{u.email}</td>
                  <td>
                    <span className="pill pill-accent">{u.role ?? "—"}</span>
                    <div className="hint">
                      {u.role && ROLE_NOTE[u.role] ? t(ROLE_NOTE[u.role]) : ""}
                    </div>
                  </td>
                  <td className="mono">
                    {u.scope_states?.length ? u.scope_states.join(", ") : t("common.all")}
                  </td>
                  <td>
                    {u.is_active ? (
                      <span className="pill pill-good">{t("users.active")}</span>
                    ) : (
                      <span className="pill">{t("users.inactive")}</span>
                    )}
                  </td>
                  <td className="mono" style={{ fontSize: 11.5 }}>{dt(u.created_at)}</td>
                  <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                    <button className="btn btn-sm" onClick={() => setEditing({ user: u })}>
                      {t("users.edit")}
                    </button>{" "}
                    <button
                      className="btn btn-sm btn-danger"
                      disabled={u.email === me?.email}
                      title={u.email === me?.email ? t("users.cantDeleteSelf") : ""}
                      onClick={() => setRemoving(u)}
                    >
                      {t("users.delete")}
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && !q.isLoading ? (
                <tr>
                  <td colSpan={7} className="tone-muted">{t("users.empty")}</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        )}
      </div>

      {editing ? (
        <Modal
          title={editing.user ? t("users.editTitle", { email: editing.user.email }) : t("users.add")}
          onClose={() => setEditing(null)}
        >
          <UserForm
            user={editing.user}
            roles={q.data?.roles ?? []}
            onSaved={() => setEditing(null)}
            onCancel={() => setEditing(null)}
          />
        </Modal>
      ) : null}

      {removing ? (
        <Modal title={t("users.deleteTitle")} onClose={() => setRemoving(null)}>
          <p className="sub">{t("users.deleteWarn", { email: removing.email })}</p>
          <ErrBox error={remove.error} />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
            <button className="btn" onClick={() => setRemoving(null)}>{t("common.cancel")}</button>
            <button
              className="btn btn-danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate(removing)}
            >
              {remove.isPending ? t("common.sending") : t("users.delete")}
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
