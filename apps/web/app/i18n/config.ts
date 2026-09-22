// Cau hinh ngon ngu. File nay KHONG co "use client" nen ca layout (server)
// lan cac man hinh (client) deu import duoc mot nguon su that duy nhat.

export const LOCALES = ["vi", "en"] as const;

export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "vi";

/** Ngon ngu nam trong cookie chu khong trong localStorage: layout o phia
 *  server phai doc duoc no de dat <html lang> va render dung ngay tu HTML
 *  dau tien — khong chop mot nhip tieng Viet roi moi doi sang tieng Anh. */
export const LOCALE_COOKIE = "dataops_lang";

export const LOCALE_MAX_AGE = 31_536_000; // 1 nam

/** The BCP-47 dung cho Intl — khac ma ngon ngu ngan o tren. */
export const INTL_TAG: Record<Locale, string> = { vi: "vi-VN", en: "en-US" };

export const LOCALE_NAME: Record<Locale, string> = { vi: "Tiếng Việt", en: "English" };

export function isLocale(v: unknown): v is Locale {
  return typeof v === "string" && (LOCALES as readonly string[]).includes(v);
}

export function toLocale(v: unknown): Locale {
  return isLocale(v) ? v : DEFAULT_LOCALE;
}
