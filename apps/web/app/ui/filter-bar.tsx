"use client";

// Thanh loc dung chung cho moi man hinh: ky (nam), phan khuc (gioi),
// khu vuc (bang), va ten. Gia tri nam tren URL nen moi trang tu doc duoc.

import { useEffect, useState } from "react";

import { useFilters } from "@/app/lib/filters";
import { useOptions } from "@/app/lib/queries";

export default function FilterBar() {
  const { filters, setFilters, count } = useFilters();
  const { data: opt } = useOptions();
  const [name, setName] = useState(filters.name ?? "");

  // Go phim khong goi API ngay — cho 350ms roi moi day len URL.
  useEffect(() => {
    const t = setTimeout(() => {
      if ((filters.name ?? "") !== name) setFilters({ name });
    }, 350);
    return () => clearTimeout(t);
  }, [name]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setName(filters.name ?? "");
  }, [filters.name]);

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
          <label htmlFor="f-gender">Phân khúc</label>
          <select
            id="f-gender"
            value={filters.gender ?? ""}
            onChange={(e) => setFilters({ gender: e.target.value })}
          >
            <option value="">cả hai</option>
            <option value="F">nữ</option>
            <option value="M">nam</option>
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
          <label htmlFor="f-name">Tên</label>
          <input
            id="f-name"
            type="text"
            placeholder="bắt đầu bằng…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ width: 140 }}
          />
        </div>

        {count > 0 ? (
          <button className="btn btn-sm" onClick={() => setFilters({ state: "", year: "", gender: "", name: "" })}>
            Xoá {count} bộ lọc
          </button>
        ) : null}
      </div>
    </div>
  );
}
