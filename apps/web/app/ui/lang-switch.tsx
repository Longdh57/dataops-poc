"use client";

// Doi VI / EN. Hai nut chu khong phai dropdown: chi co hai lua chon, va
// nguoi dung thay ngay minh dang o ngon ngu nao ma khong phai mo ra.

import { LOCALES, LOCALE_NAME } from "@/app/i18n/config";
import { useI18n } from "@/app/i18n/context";

export default function LangSwitch() {
  const { locale, setLocale, t } = useI18n();

  return (
    <div className="langswitch" role="group" aria-label={t("lang.label")}>
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          className="langswitch-btn"
          data-on={l === locale ? "1" : "0"}
          aria-pressed={l === locale}
          title={t("lang.switchTo", { name: LOCALE_NAME[l] })}
          onClick={() => setLocale(l)}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
