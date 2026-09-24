"use client";

// Form them / sua mot tai khoan. Nam trong Modal cua trang Nguoi dung.
//
// Hai cho form nay co y lam khac voi mot form CRUD binh thuong:
//
// - O chon bang chi hien khi vai tro la analyst. Team lead va admin khong
//   gioi han bang, de o do thi nguoi dung tuong minh dang cap them quyen
//   trong khi server se bo qua.
// - Analyst phai chon it nhat mot bang. Bo trong KHONG phai la "chua cap
//   gi" ma la "khong gioi han" (authz.scope_clause), nen day la cho de cap
//   nham toan quyen nhat. Server chan lan nua bang 422.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { post, put } from "@/app/lib/api";
import { useOptions } from "@/app/lib/queries";
import type { AppUser } from "@/app/lib/types";

import { ErrBox } from "./bits";

// Mo ta ngan tung vai tro. Khong dung khoa dich ghep chuoi: vai tro la du
// lieu tu server, ghep vao se sinh ra khoa khong ton tai luc no doi.
export const ROLE_NOTE: Record<string, MessageKey> = {
  admin: "users.role.admin",
  team_lead: "users.role.team_lead",
  analyst: "users.role.analyst",
};

export default function UserForm({
  user, roles, onSaved, onCancel,
}: {
  /** null = them tai khoan moi. */
  user: AppUser | null;
  roles: string[];
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { data: options } = useOptions();

  const [email, setEmail] = useState(user?.email ?? "");
  const [name, setName] = useState(user?.display_name ?? "");
  // Ban seed cu con vai tro `sale`, khong nam trong danh sach chon duoc
  // nua. Khong im lang doi no: giu nguyen o `role` roi canh bao ben duoi.
  const [role, setRole] = useState(user?.role ?? "analyst");
  const [scope, setScope] = useState<string[]>(user?.scope_states ?? []);
  const [active, setActive] = useState(user?.is_active ?? true);

  const save = useMutation({
    mutationFn: () => {
      const body = {
        display_name: name.trim() || null,
        role,
        scope_states: role === "analyst" ? scope : null,
      };
      return user
        ? put<AppUser>(`/users/${user.id}`, { ...body, is_active: active })
        : post<AppUser>("/users", { ...body, email: email.trim().toLowerCase() });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      // Danh tinh dang dung co the vua bi doi vai tro hoac pham vi.
      qc.invalidateQueries({ queryKey: ["me"] });
      onSaved();
    },
  });

  // Bang da gan cho tai khoan nay phai luon chon duoc, ke ca khi no khong
  // con dong du lieu nao — neu khong thi mo form ra la mat pham vi cu.
  const states = Array.from(new Set([...(options?.states ?? []), ...scope])).sort();
  const toggle = (s: string) =>
    setScope((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const unknownRole = Boolean(user?.role) && !roles.includes(user!.role!);
  const canSave =
    (user || email.trim()) && (role !== "analyst" || scope.length > 0) && !save.isPending;

  return (
    <div className="rule-form">
      <div>
        <label className="lbl" htmlFor="uf-email">{t("users.form.email")}</label>
        <input
          id="uf-email" type="text" className="mono" value={email} disabled={Boolean(user)}
          placeholder="ten@cty.com"
          onChange={(e) => setEmail(e.target.value)}
        />
        <div className="hint">{user ? t("users.form.emailLocked") : t("users.form.emailHint")}</div>
      </div>

      <div>
        <label className="lbl" htmlFor="uf-name">{t("users.form.name")}</label>
        <input id="uf-name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
      </div>

      <div>
        <label className="lbl" htmlFor="uf-role">{t("users.form.role")}</label>
        <select id="uf-role" value={role} onChange={(e) => setRole(e.target.value)}>
          {unknownRole ? <option value={user!.role!}>{user!.role}</option> : null}
          {roles.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <div className="hint">{ROLE_NOTE[role] ? t(ROLE_NOTE[role]) : role}</div>
        {unknownRole ? (
          <div className="hint" style={{ color: "var(--warn)" }}>
            {t("users.form.unknownRole", { role: user!.role! })}
          </div>
        ) : null}
      </div>

      {role === "analyst" ? (
        <div>
          <span className="lbl">{t("users.form.scope")}</span>
          <div className="scope-grid">
            {states.map((s) => (
              <label key={s}>
                <input type="checkbox" checked={scope.includes(s)} onChange={() => toggle(s)} />
                <span className="mono">{s}</span>
              </label>
            ))}
          </div>
          <div className="hint">{t("users.form.scopeHint")}</div>
        </div>
      ) : (
        <div className="hint">{t("users.form.scopeAll")}</div>
      )}

      {user ? (
        <label className="check">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          {t("users.form.active")}
        </label>
      ) : null}

      <ErrBox error={save.error} />

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button type="button" className="btn" onClick={onCancel}>{t("common.cancel")}</button>
        <button
          type="button" className="btn btn-primary" disabled={!canSave}
          onClick={() => save.mutate()}
        >
          {save.isPending ? t("users.form.saving") : t("users.form.save")}
        </button>
      </div>
    </div>
  );
}
