// Loi dich, khong dinh React — layout o phia server va context o phia
// client dung chung mot ham nay.

import type { Locale } from "./config";
import { en } from "./en";
import { vi, type MessageKey } from "./vi";

export type { MessageKey };

export const DICTS: Record<Locale, Record<MessageKey, string>> = { vi, en };

export type Values = Record<string, string | number | null | undefined>;

const PLACEHOLDER = /\{(\w+)\}/g;

/** Chon nhanh so it / so nhieu. Tieng Viet khong chia so nen ban vi hau
 *  nhu khong co dau `||`; ban en thi co. Dem lay tu `count`, hoac tu `n`
 *  khi `n` van con la so (chua qua num()). */
export function plural(tpl: string, vals?: Values): string {
  const i = tpl.indexOf("||");
  if (i < 0) return tpl;
  const raw = vals?.count ?? vals?.n;
  const n = typeof raw === "number" ? raw : Number.NaN;
  return Math.abs(n) === 1 ? tpl.slice(0, i) : tpl.slice(i + 2);
}

/** Template cua mot khoa, da chon so it/nhieu nhung CHUA dien cho trong. */
export function template(locale: Locale, key: MessageKey, vals?: Values): string {
  const dict = DICTS[locale] ?? vi;
  // Thieu khoa o ban dich phu thi roi ve ban goc chu khong hien khoa tho.
  return plural(dict[key] ?? vi[key] ?? key, vals);
}

export function translate(locale: Locale, key: MessageKey, vals?: Values): string {
  const tpl = template(locale, key, vals);
  if (!vals) return tpl;
  return tpl.replace(PLACEHOLDER, (m, name: string) =>
    name in vals ? String(vals[name] ?? "") : m,
  );
}

/** Cat template thanh cac manh quanh `{ten}` — dung khi cho trong phai la
 *  JSX (<b>, <span className="mono">, <Link>) chu khong phai chuoi. */
export function split(tpl: string): ({ text: string } | { slot: string })[] {
  const out: ({ text: string } | { slot: string })[] = [];
  let last = 0;
  for (const m of tpl.matchAll(PLACEHOLDER)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ text: tpl.slice(last, at) });
    out.push({ slot: m[1] });
    last = at + m[0].length;
  }
  if (last < tpl.length) out.push({ text: tpl.slice(last) });
  return out;
}
