"use client";

// Luoi du lieu — AG Grid Client-Side Row Model.
//
// Vi sao khong dung Infinite Row Model: API phan trang theo keyset (cursor),
// khong theo offset, nen khong nhay den "dong thu 50.000" duoc. Cach hop
// voi keyset la noi tiep cac slice da tai vao mot mang trong bo nho va de
// AG Grid ao hoa phan hien thi. Cuon den cuoi thi tu goi slice sau.
//
// He qua phai noi ro voi nguoi dung: bam tieu de cot chi sap xep trong so
// dong DA TAI. Muon sap xep toan bo 1,2 trieu dong thi doi o "Sắp xếp toàn
// bộ" — cai do chay o server va nap lai tu dau.

import { useInfiniteQuery } from "@tanstack/react-query";
import type { BodyScrollEndEvent, ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useMemo, useState } from "react";

import { gw, qs } from "@/app/lib/api";
import { useFilters } from "@/app/lib/filters";
import { num, pct } from "@/app/lib/format";
import type { Fact, FactsPage } from "@/app/lib/types";
import { ErrBox, Loading } from "@/app/ui/bits";
import { gridTheme } from "@/app/ui/grid";

const PAGE = 500;

const SORTS = [
  { v: "deposit", label: "deposit" },
  { v: "deposit_share", label: "thị phần" },
  { v: "year", label: "năm" },
  { v: "institution", label: "tổ chức" },
];

export default function DataPage() {
  const { filters } = useFilters();
  const [sort, setSort] = useState("deposit");
  const [desc, setDesc] = useState(true);

  const q = useInfiniteQuery({
    queryKey: ["facts", filters, sort, desc],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      gw<FactsPage>(
        `/facts${qs({ ...filters, sort, desc: String(desc), limit: PAGE, cursor: pageParam })}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const rows = useMemo(() => q.data?.pages.flatMap((p) => p.rows) ?? [], [q.data]);

  const onScrollEnd = useCallback(
    (e: BodyScrollEndEvent<Fact>) => {
      // Con cach cuoi duoi 60 dong thi nap tiep — nguoi dung khong kip thay
      // khoang trong.
      if (q.isFetchingNextPage || !q.hasNextPage) return;
      if (e.api.getLastDisplayedRowIndex() >= rows.length - 60) q.fetchNextPage();
    },
    [q, rows.length],
  );

  const cols = useMemo<ColDef<Fact>[]>(
    () => [
      { field: "state", headerName: "Bang", width: 92, cellClass: "cell-key" },
      { field: "year", headerName: "Năm", width: 88, cellClass: "cell-mono" },
      { field: "institution", headerName: "Tổ chức", flex: 1, minWidth: 200, cellClass: "cell-strong" },
      {
        // So o day LUON la so cua nguon. Nhan "có ticket" chi noi rang o
        // nay dang cho team Data sua — no khong thay so, vi ung dung nay
        // khong sua so.
        field: "deposit", headerName: "Deposit", width: 170, type: "rightAligned",
        valueFormatter: (p) => num(p.value as number),
        cellRenderer: (p: { data?: Fact; value: number }) =>
          p.data?.ticket_id ? (
            <span>
              <span
                className={p.data.ticket_blocking ? "pill pill-crit" : "pill pill-warn"}
                style={{ marginRight: 7 }}
                title={`ticket #${p.data.ticket_id} — nguồn phải sửa thành ${p.data.ticket_expected}`}
              >
                ticket
              </span>
              {num(p.value)}
            </span>
          ) : (
            num(p.value)
          ),
      },
      {
        field: "deposit_share", headerName: "Thị phần", width: 120, type: "rightAligned",
        valueFormatter: (p) => pct(p.value as number),
        cellClass: "cell-code",
      },
      {
        field: "prev_deposit", headerName: "Năm trước", width: 120, type: "rightAligned",
        valueFormatter: (p) => num(p.value as number),
        cellClass: "cell-dim",
      },
      {
        field: "ticket_expected", headerName: "Ticket yêu cầu", width: 150,
        type: "rightAligned", cellClass: "cell-dim",
        valueFormatter: (p) => (p.value ? String(p.value) : ""),
      },
    ],
    [],
  );

  if (q.error) return <ErrBox error={q.error} />;

  return (
    <>
      <div className="card-head">
        <div>
          <h1>Dữ liệu trong phạm vi</h1>
          <p className="sub">
            Phạm vi áp ở tầng server — đổi tham số trên URL không lấy được dữ liệu ngoài phạm vi
            được gán. Đã tải <b>{num(rows.length)}</b> dòng
            {q.hasNextPage ? ", cuộn xuống để nạp tiếp" : " — hết dữ liệu"}.
          </p>
        </div>
        <div className="field">
          <label htmlFor="sort">Sắp xếp toàn bộ</label>
          <select id="sort" value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map((s) => (
              <option key={s.v} value={s.v}>{s.label}</option>
            ))}
          </select>
          <button className="btn btn-sm" onClick={() => setDesc((d) => !d)}>
            {desc ? "giảm dần ↓" : "tăng dần ↑"}
          </button>
        </div>
      </div>

      {q.isPending ? (
        <Loading what="500 dòng đầu" />
      ) : (
        <>
          <div style={{ height: "calc(100vh - 280px)", minHeight: 420 }}>
            <AgGridReact<Fact>
              theme={gridTheme}
              rowData={rows}
              columnDefs={cols}
              defaultColDef={{ sortable: true, resizable: true, suppressHeaderMenuButton: true }}
              getRowId={(p) => `${p.data.year}-${p.data.state}-${p.data.institution_id}`}
              onBodyScrollEnd={onScrollEnd}
              suppressCellFocus
              animateRows={false}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
            <button
              className="btn btn-sm"
              disabled={!q.hasNextPage || q.isFetchingNextPage}
              onClick={() => q.fetchNextPage()}
            >
              {q.isFetchingNextPage
                ? "Đang nạp…"
                : q.hasNextPage
                  ? `Tải thêm ${PAGE} dòng`
                  : "Đã tải hết"}
            </button>
            <p className="sub" style={{ flex: 1, minWidth: 260 }}>
              Bấm tiêu đề cột chỉ sắp xếp trong {num(rows.length)} dòng đã tải. Muốn sắp xếp toàn
              bộ thì đổi ô <b>Sắp xếp toàn bộ</b> ở trên — lần đó chạy ở server.
            </p>
          </div>
        </>
      )}
    </>
  );
}
