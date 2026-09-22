"use client";

// Ngon ngu song trong React context, gia tri dau tien do layout doc tu
// cookie va truyen xuong — nen HTML tu server da dung ngon ngu roi, khong
// chop mot nhip tieng Viet truoc khi client kip doi.
//
// Doi ngon ngu KHONG tai lai trang: chi ghi cookie roi setState. Moi man
// hinh deu la client component nen chung ve lai ngay, va bo loc dang go
// do tren URL khong mat.

import {
  Fragment,
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  DEFAULT_LOCALE,
  INTL_TAG,
  LOCALE_COOKIE,
  LOCALE_MAX_AGE,
  type Locale,
} from "./config";
import { template, translate, split, type MessageKey, type Values } from "./translate";

type Nodes = Record<string, ReactNode>;

type I18n = {
  locale: Locale;
  setLocale: (next: Locale) => void;
  /** Dich ra chuoi. */
  t: (key: MessageKey, vals?: Values) => string;
  /** Dich ra JSX — cho trong nhan ReactNode (<b>, <Link>, <span>…). */
  tn: (key: MessageKey, nodes: Nodes, vals?: Values) => ReactNode;
};

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({
  locale: initial,
  children,
}: {
  locale: Locale;
  children: ReactNode;
}) {
  const [locale, setState] = useState<Locale>(initial);

  const setLocale = useCallback((next: Locale) => {
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=${LOCALE_MAX_AGE}; samesite=lax`;
    document.documentElement.lang = next;
    setState(next);
  }, []);

  const value = useMemo<I18n>(() => {
    const t = (key: MessageKey, vals?: Values) => translate(locale, key, vals);

    const tn = (key: MessageKey, nodes: Nodes, vals?: Values): ReactNode =>
      split(template(locale, key, { ...vals, ...countOf(nodes) })).map((part, i) => (
        <Fragment key={i}>
          {"text" in part
            ? part.text
            : part.slot in nodes
              ? nodes[part.slot]
              : vals && part.slot in vals
                ? String(vals[part.slot] ?? "")
                : `{${part.slot}}`}
        </Fragment>
      ));

    return { locale, setLocale, t, tn };
  }, [locale, setLocale]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** `nodes` co the chua ReactNode nen khong dung de chon so it/nhieu —
 *  chi lay lai `count`/`n` khi chung tinh co la so. */
function countOf(nodes: Nodes): Values {
  const out: Values = {};
  for (const k of ["count", "n"] as const) {
    if (typeof nodes[k] === "number") out[k] = nodes[k];
  }
  return out;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n phai nam trong <I18nProvider>");
  return ctx;
}

/** Dinh dang so va thoi gian theo ngon ngu dang chon. Tach khoi t() vi
 *  cho nao cung goi, va vi `ago` con can tu ngu dich duoc. */
export function useFmt() {
  const { locale, t } = useI18n();

  return useMemo(() => {
    const tag = INTL_TAG[locale] ?? INTL_TAG[DEFAULT_LOCALE];
    const dash = "—";

    const num = (n: number | null | undefined) =>
      n === null || n === undefined ? dash : n.toLocaleString(tag);

    return {
      locale,
      num,
      pct: (x: number | null | undefined, digits = 3) =>
        x === null || x === undefined ? dash : `${(x * 100).toFixed(digits)}%`,
      signed: (n: number | null | undefined) =>
        n === null || n === undefined ? dash : `${n > 0 ? "+" : ""}${n.toLocaleString(tag)}`,
      dt: (iso: string | null | undefined) =>
        iso
          ? new Date(iso).toLocaleString(tag, { dateStyle: "short", timeStyle: "short" })
          : dash,
      /** "12 phút" / "12 minutes" — doc nhanh hon mot moc tuyet doi. */
      ago: (seconds: number | null | undefined) => {
        if (seconds === null || seconds === undefined) return dash;
        if (seconds < 90) return t("ago.seconds", { n: Math.round(seconds) });
        if (seconds < 5400) return t("ago.minutes", { n: Math.round(seconds / 60) });
        if (seconds < 172800) return t("ago.hours", { n: Math.round(seconds / 3600) });
        return t("ago.days", { n: Math.round(seconds / 86400) });
      },
    };
  }, [locale, t]);
}
