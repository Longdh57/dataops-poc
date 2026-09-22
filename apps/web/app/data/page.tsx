"use client";

// Luoi du lieu — AG Grid Client-Side Row Model.
//
// Vi sao khong dung Infinite Row Model: API phan trang theo keyset (cursor),
// khong theo offset, nen khong nhay den "dong thu 50.000" duoc. Cach hop
// voi keyset la noi tiep cac slice da tai vao mot mang trong bo nho va de
// AG Grid ao hoa phan hien thi. Cuon den cuoi thi tu goi slice sau.
//
// He qua phai noi ro voi nguoi dung: bam tieu de cot chi sap xep trong so
// dong DA TAI. Muon sap xep toan bo 1,2 trieu dong thi doi o "Sap xep toan
// bo" — cai do chay o server va nap lai tu dau.

import { useInfiniteQuery } from "@tanstack/react-query";
import type { BodyScrollEndEvent, ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useMemo, useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { gw, qs } from "@/app/lib/api";
import { useFilters } from "@/app/lib/filters";
import type { Fact, FactsPage } from "@/app/lib/types";
import { ErrBox, Loading } from "@/app/ui/bits";
import { gridTheme, useGridLocale } from "@/app/ui/grid";

const PAGE = 500;

const SORTS: { v: string; label: MessageKey }[] = [
  { v: "deposit", label: "data.sort.deposit" },
  { v: "deposit_share", label: "data.sort.share" },
  { v: "year", label: "data.sort.year" },
  { v: "institution", label: "data.sort.institution" },
];

export default function DataPage() {
  const { t, tn } = useI18n();
  const { num, pct } = useFmt();
  const gridLocale = useGridLocale();
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
      { field: "state", headerName: t("data.col.state"), width: 92, cellClass: "cell-key" },
      { field: "year", headerName: t("data.col.year"), width: 88, cellClass: "cell-mono" },
      {
        field: "institution", headerName: t("data.col.institution"), flex: 1, minWidth: 200,
        cellClass: "cell-strong",
      },
      {
        // So o day LUON la so cua nguon. Nhan "co ticket" chi noi rang o
        // nay dang cho team Data sua — no khong thay so, vi ung dung nay
        // khong sua so.
        field: "deposit", headerName: t("data.col.deposit"), width: 170, type: "rightAligned",
        valueFormatter: (p) => num(p.value as number),
        cellRenderer: (p: { data?: Fact; value: number }) =>
          p.data?.ticket_id ? (
            <span>
              <span
                className={p.data.ticket_blocking ? "pill pill-crit" : "pill pill-warn"}
                style={{ marginRight: 7 }}
                title={t("data.ticketTitle", {
                  id: p.data.ticket_id,
                  expected: p.data.ticket_expected,
                })}
              >
                {t("data.ticketPill")}
              </span>
              {num(p.value)}
            </span>
          ) : (
            num(p.value)
          ),
      },
      {
        field: "deposit_share", headerName: t("data.col.share"), width: 120, type: "rightAligned",
        valueFormatter: (p) => pct(p.value as number),
        cellClass: "cell-code",
      },
      {
        field: "prev_deposit", headerName: t("data.col.prev"), width: 120, type: "rightAligned",
        valueFormatter: (p) => num(p.value as number),
        cellClass: "cell-dim",
      },
      {
        field: "ticket_expected", headerName: t("data.col.ticketExpected"), width: 150,
        type: "rightAligned", cellClass: "cell-dim",
        valueFormatter: (p) => (p.value ? String(p.value) : ""),
      },
    ],
    [t, num, pct],
  );

  if (q.error) return <ErrBox error={q.error} />;

  return (
    <>
      <div className="card-head">
        <div>
          <h1>{t("data.title")}</h1>
          <p className="sub">
            {tn("data.sub", {
              n: <b>{num(rows.length)}</b>,
              more: q.hasNextPage ? t("data.subMore") : t("data.subEnd"),
            })}
          </p>
        </div>
        <div className="field">
          <label htmlFor="sort">{t("data.sortAll")}</label>
          <select id="sort" value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map((s) => (
              <option key={s.v} value={s.v}>{t(s.label)}</option>
            ))}
          </select>
          <button className="btn btn-sm" onClick={() => setDesc((d) => !d)}>
            {desc ? t("data.desc") : t("data.asc")}
          </button>
        </div>
      </div>

      {q.isPending ? (
        <Loading what={t("data.loading")} />
      ) : (
        <>
          <div style={{ height: "calc(100vh - 280px)", minHeight: 420 }}>
            <AgGridReact<Fact>
              theme={gridTheme}
              localeText={gridLocale}
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
                ? t("data.loadingMore")
                : q.hasNextPage
                  ? t("data.loadMore", { n: PAGE })
                  : t("data.allLoaded")}
            </button>
            <p className="sub" style={{ flex: 1, minWidth: 260 }}>
              {tn("data.sortNote", {
                n: num(rows.length),
                field: <b>{t("data.sortAll")}</b>,
              })}
            </p>
          </div>
        </>
      )}
    </>
  );
}
