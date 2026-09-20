"use client";

// Bo loc nam tren URL chu khong trong state cua React: dan link cho dong
// nghiep la ho thay dung man hinh minh dang nhin, va bam Back tra ve dung
// bo loc truoc do.

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

export type Filters = {
  state?: string;
  year?: string;
  gender?: string;
  name?: string;
};

const KEYS: (keyof Filters)[] = ["state", "year", "gender", "name"];

export function useFilters() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filters = useMemo(() => {
    const f: Filters = {};
    for (const k of KEYS) {
      const v = sp.get(k);
      if (v) f[k] = v;
    }
    return f;
  }, [sp]);

  const setFilters = useCallback(
    (patch: Partial<Filters>) => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      const s = next.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [sp, router, pathname],
  );

  const count = KEYS.filter((k) => filters[k]).length;
  return { filters, setFilters, count };
}
