"use client";

// Mot cho duy nhat khai bao queryKey. Trung key = dung chung cache: banner
// do tuoi, badge tren tab va dashboard chi goi /version mot lan.

import { useQuery } from "@tanstack/react-query";

import { gw, qs } from "./api";
import type { Filters } from "./filters";
import type { Gate, Me, Options, Summary, Ticket, VersionInfo } from "./types";

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
