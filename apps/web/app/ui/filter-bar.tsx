"use client";

// Thanh loc dung chung cho moi man hinh: ky (nam), khu vuc (bang), va
// to chuc. Gia tri nam tren URL nen moi trang tu doc duoc.

import { useEffect, useState } from "react";

import { useI18n } from "@/app/i18n/context";
import { useFilters } from "@/app/lib/filters";
import { useOptions } from "@/app/lib/queries";

export default function FilterBar() {
  const { t } = useI18n();
  const { filters, setFilters, count } = useFilters();
  const { data: opt } = useOptions();
  const [institution, setInstitution] = useState(filters.institution ?? "");

  // Go phim khong goi API ngay — cho 350ms roi moi day len URL.
  useEffect(() => {
    const timer = setTimeout(() => {
      if ((filters.institution ?? "") !== institution) setFilters({ institution });
    }, 350);
    return () => clearTimeout(timer);
  }, [institution]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setInstitution(filters.institution ?? "");
  }, [filters.institution]);

  return (
    <div className="filterbar">
      <div className="filterbar-inner">
        <div className="field">
          <label htmlFor="f-year">{t("filter.year")}</label>
          <select
            id="f-year"
            value={filters.year ?? ""}
            onChange={(e) => setFilters({ year: e.target.value })}
          >
            <option value="">{t("filter.allYears")}</option>
            {opt?.years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-state">{t("filter.state")}</label>
          <select
            id="f-state"
            value={filters.state ?? ""}
            onChange={(e) => setFilters({ state: e.target.value })}
          >
            <option value="">{t("filter.myScope")}</option>
            {opt?.states.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-institution">{t("filter.institution")}</label>
          <input
            id="f-institution"
            type="text"
            placeholder={t("filter.institutionPlaceholder")}
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            style={{ width: 160 }}
          />
        </div>

        {count > 0 ? (
          <button className="btn btn-sm" onClick={() => setFilters({ state: "", year: "", institution: "" })}>
            {t("filter.clear", { n: count })}
          </button>
        ) : null}
      </div>
    </div>
  );
}
