"use client";

// Thanh loc dung chung cho moi man hinh: ky (nam), khu vuc (bang), va
// to chuc. Gia tri nam tren URL nen moi trang tu doc duoc.

import { useEffect, useState } from "react";

import { useFilters } from "@/app/lib/filters";
import { useOptions } from "@/app/lib/queries";

export default function FilterBar() {
  const { filters, setFilters, count } = useFilters();
  const { data: opt } = useOptions();
  const [institution, setInstitution] = useState(filters.institution ?? "");

  // Go phim khong goi API ngay — cho 350ms roi moi day len URL.
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.institution ?? "") !== institution) setFilters({ institution });
    }, 350);
    return () => clearTimeout(t);
  }, [institution]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setInstitution(filters.institution ?? "");
  }, [filters.institution]);

  return (
    <div className="filterbar">
      <div className="filterbar-inner">
        <div className="field">
          <label htmlFor="f-year">Kỳ</label>
          <select
            id="f-year"
            value={filters.year ?? ""}
            onChange={(e) => setFilters({ year: e.target.value })}
          >
            <option value="">tất cả năm</option>
            {opt?.years.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-state">Khu vực</label>
          <select
            id="f-state"
            value={filters.state ?? ""}
            onChange={(e) => setFilters({ state: e.target.value })}
          >
            <option value="">trong phạm vi của tôi</option>
            {opt?.states.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-institution">Tổ chức</label>
          <input
            id="f-institution"
            type="text"
            placeholder="bắt đầu bằng…"
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            style={{ width: 160 }}
          />
        </div>

        {count > 0 ? (
          <button className="btn btn-sm" onClick={() => setFilters({ state: "", year: "", institution: "" })}>
            Xoá {count} bộ lọc
          </button>
        ) : null}
      </div>
    </div>
  );
}
