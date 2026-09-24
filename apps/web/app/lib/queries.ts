"use client";

// Mot cho duy nhat khai bao queryKey. Trung key = dung chung cache: banner
// do tuoi, badge tren tab va dashboard chi goi /version mot lan.

import { useQuery } from "@tanstack/react-query";

import { gw, qs } from "./api";
import type { Filters } from "./filters";
import type {
  Gate, Me, Options, RulesCatalog, Summary, SwitchableUser, Ticket, UsersRes,
  VersionInfo,
} from "./types";

export const useMe = () =>
  useQuery({ queryKey: ["me"], queryFn: () => gw<Me>("/me"), staleTime: 60_000 });

export const useGate = () =>
  useQuery({ queryKey: ["gate"], queryFn: () => gw<Gate>("/gate") });

/** So vi pham cua lan nap hien tai TRONG PHAM VI nguoi dung — badge tab.
 *  Khong dung /gate vi cong phat hanh la toan cuc, con vi pham thi khong. */
export const useOpenCount = () =>
  useQuery({
    queryKey: ["exceptions", "count"],
    queryFn: () => gw<{ total: number }>("/exceptions?limit=1"),
  });

/** Ticket chua dong trong pham vi — badge tab va trang Ticket dung chung. */
export const useTickets = (status = "song") =>
  useQuery({
    queryKey: ["tickets", status],
    queryFn: () =>
      gw<{ total: number; rows: Ticket[]; blocking_open: number; can_set_blocking: boolean }>(
        `/tickets${qs({ status, limit: 300 })}`,
      ),
  });

export const useOptions = () =>
  useQuery({ queryKey: ["options"], queryFn: () => gw<Options>("/options"), staleTime: 300_000 });

/** Poll moi 30 giay — CHI de biet co lan nap moi, khong tu lam moi bang. */
export const useVersion = () =>
  useQuery({
    queryKey: ["version"],
    queryFn: () => gw<VersionInfo>("/version"),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

export const useSummary = (f: Filters) =>
  useQuery({
    queryKey: ["summary", f],
    queryFn: () => gw<Summary>(`/summary${qs(f)}`),
  });

/** Bo luat QC (bang qc_rule). Chi goi khi hop xem luat duoc mo ra.
 *  `version` = xem snapshot mot version cu (trang Phien ban). Moi lan
 *  ghi luat deu invalidate ["rules"], nen cache dai khong lam ai doc sai. */
export const useRules = (version?: number | null) =>
  useQuery({
    queryKey: ["rules", version ?? "current"],
    queryFn: () => gw<RulesCatalog>(`/rules${qs({ version: version ?? undefined })}`),
    // Snapshot khong bao gio doi. Ban hien tai thi doi khi co nguoi sua.
    staleTime: version ? Infinity : 60_000,
  });

/** Danh sach tai khoan cho man hinh Nguoi dung. CHI ADMIN goi duoc — vai
 *  tro khac nhan 403, va trang hien thang loi do chu khong giau di. */
export const useUsers = () =>
  useQuery({
    queryKey: ["users"],
    queryFn: () => gw<UsersRes>("/users"),
    retry: false,
    staleTime: 60_000,
  });

/** Danh sach cho bo chon danh tinh — duong rieng, mo cho moi vai tro
 *  nhung chi ton tai o che do dev. `enabled` tat han khi IAP da bat, luc
 *  do endpoint tra 404 va bo chon cung dang bi khoa. */
export const useSwitchableUsers = (enabled = true) =>
  useQuery({
    queryKey: ["users", "switchable"],
    queryFn: () => gw<{ rows: SwitchableUser[] }>("/users/switchable"),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
