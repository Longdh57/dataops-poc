"use client";

// Mot cho duy nhat khai bao queryKey. Trung key = dung chung cache: banner
// do tuoi, badge tren tab va dashboard chi goi /version mot lan.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { gw, qs } from "./api";
import type { Filters } from "./filters";
import type {
  AgentSessionUsage, AgentUsage, Gate, Me, Options, RulesCatalog, Summary, SwitchableUser, Ticket,
  UsersRes, VersionInfo,
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

// Pill tren man hinh Agent va modal chi tiet dung chung mot key — modal
// khong goi API rieng, va nut "lay lai so moi" ghi vao day thi ca hai doi.
const AGENT_USAGE_KEY = ["agent", "usage"];

// Tien to key cua so theo phien. Man hinh Agent invalidate dung tien to
// nay sau moi luot chat — khong liet ke session_id, vi luot dau tien tao
// ra mot session_id ma luc invalidate no moi vua co.
export const AGENT_SESSION_USAGE_KEY = ["agent", "usage", "session"];

/** Chi phi Vertex AI thang nay cho man hinh AI Agent. CHI team_lead/admin
 *  goi duoc — vai tro khac nhan 403 va o chi phi im lang khong hien, nen
 *  `retry: false` de khong goi lai mot loi da biet chac.
 *
 *  Metric ben Google tre vai phut va server con cache 5 phut nua, nen
 *  staleTime dai la dung — goi day hon cung khong ra so moi. */
export const useAgentUsage = () =>
  useQuery({
    queryKey: AGENT_USAGE_KEY,
    queryFn: () => gw<AgentUsage>("/agent/usage"),
    retry: false,
    staleTime: 300_000,
  });

/** Nut "Lay lai so moi" trong modal chi phi cua man hinh Agent.
 *
 *  `force=true` de backend bo qua cache 5 phut cua no; ket qua ghi thang
 *  vao cache React Query nen pill ngoai va modal doi CUNG LUC, khong phai
 *  cho `staleTime` 5 phut o tren het han.
 *
 *  Van khong phai realtime: metric token cua Vertex AI con tre khoang 1-2
 *  phut sau moi lenh goi, nen bam ngay sau khi chat thuong van ra con so
 *  cu — modal noi ro dieu nay de nguoi dung khong tuong nut bi hong. */
/** Token cua phien chat dang mo. Nguon la DB cua chinh ung dung (ghi tu
 *  `usageMetadata` moi luot chat) nen KHONG tre nhu so thang doc tu Cloud
 *  Monitoring — `staleTime: 0` de sau moi cau hoi la thay so moi ngay.
 *
 *  Chua co phien (cuoc tro chuyen moi, chua hoi cau nao) thi khong goi
 *  API: khong co gi de dem. */
export const useAgentSessionUsage = (sessionId: string | null) =>
  useQuery({
    queryKey: [...AGENT_SESSION_USAGE_KEY, sessionId],
    queryFn: () => gw<AgentSessionUsage>(`/agent/usage/session/${sessionId}`),
    enabled: Boolean(sessionId),
    staleTime: 0,
  });

export const useRefreshAgentUsage = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => gw<AgentUsage>(`/agent/usage${qs({ force: "true" })}`),
    onSuccess: (data) => qc.setQueryData(AGENT_USAGE_KEY, data),
  });
};
