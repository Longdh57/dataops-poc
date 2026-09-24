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
//
// Cot QC dau bang: dong nao dang vi pham luat thi co mot cham mau. /facts
// chi tra ve SO LUONG va muc nang nhat — du de ve cham, va khong hon. Bam
// vao cham moi goi /facts/violations de biet la luat gi: cot message cua
// qc_exception lap lai nguyen van o tung dong, keo san ca trang 500 dong
// la tra tien cho thu hau het khong ai mo ra xem.

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type { BodyScrollEndEvent, ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { useFmt, useI18n } from "@/app/i18n/context";
import type { MessageKey } from "@/app/i18n/translate";
import { gw, qs } from "@/app/lib/api";
import { useFilters } from "@/app/lib/filters";
import type { CellViolations, Fact, FactsPage } from "@/app/lib/types";
import { ErrBox, Loading, Modal, Severity } from "@/app/ui/bits";
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
  // Dong dang mo hop vi pham. Giu ca dong chu khong chi khoa: hop can ten
  // to chuc va so deposit de nguoi doc biet minh dang nhin o nao.
  const [cell, setCell] = useState<Fact | null>(null);

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
  const head = q.data?.pages[0];

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
      {
        // Cham thay cho chu: ten luat dai gap may lan be ngang mot cot, ma
        // phan lon dong thi khong vi pham gi. Muon biet luat nao thi bam.
        field: "violations", headerName: t("data.col.qc"), width: 76,
        cellRenderer: (p: { data?: Fact; value: number }) =>
          p.data && p.value ? (
            <button
              type="button"
              className={`qc-dot qc-dot-${p.data.violation_severity ?? "info"}`}
              title={t("data.qcDotTitle", { n: p.value })}
              aria-label={t("data.qcDotTitle", { n: p.value })}
              onClick={() => setCell(p.data ?? null)}
            >
              <span aria-hidden>●</span>
              {p.value > 1 ? <span className="qc-dot-n">{p.value}</span> : null}
            </button>
          ) : null,
      },
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

      {/* Cham vi pham co the la cua lan nap TRUOC — noi ngay, dung de nguoi
          doc tuong cham do dang noi ve con so truoc mat. */}
      {head?.qc_stale ? (
        <div className="banner banner-warn" style={{ marginBottom: 14 }}>
          <div>
            <div className="banner-title">
              {head.qc_stale_reason === "rules"
                ? t("qc.staleRules.title")
                : t("exc.staleTitle")}
            </div>
            <div className="banner-body">
              {head.qc_stale_reason === "rules"
                ? t("data.qcStaleRulesNote", {
                    current: head.ruleset_version ?? "—",
                    applied: head.rules_version ?? "—",
                  })
                : tn("data.qcStaleNote", {
                    runId: <span className="mono">{head.qc_run_id ?? "—"}</span>,
                  })}
            </div>
          </div>
        </div>
      ) : null}

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
              rowClassRules={{
                "row-viol-crit": (p) => p.data?.violation_severity === "critical",
                "row-viol-warn": (p) =>
                  !!p.data?.violations && p.data.violation_severity !== "critical",
              }}
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

      {cell ? <ViolationsBox fact={cell} onClose={() => setCell(null)} /> : null}
    </>
  );
}

// ------------------------------------------------- hop vi pham cua mot dong

function ViolationsBox({ fact, onClose }: { fact: Fact; onClose: () => void }) {
  const { t, tn } = useI18n();
  const { num } = useFmt();

  // Key bat dau bang "facts" co chu y: mo ticket o man hinh Vi pham luat
  // invalidate ["facts"], va hop nay phai theo cung — no cung dang hien
  // trang thai ticket cua o do.
  const d = useQuery({
    queryKey: ["facts", "violations", fact.year, fact.state, fact.institution_id],
    queryFn: () =>
      gw<CellViolations>(
        `/facts/violations${qs({
          year: fact.year, state: fact.state, institution_id: fact.institution_id,
        })}`,
      ),
  });

  const ticket = d.data?.ticket;

  return (
    <Modal wide title={t("data.viol.title")} onClose={onClose}>
      <p className="sub mono" style={{ marginTop: -4, marginBottom: 12 }}>
        {[fact.state, fact.institution, fact.year].filter(Boolean).join(" · ")} ·{" "}
        {num(fact.deposit)}
      </p>

      <ErrBox error={d.error} />
      {d.isPending ? <Loading what={t("data.viol.loading")} /> : null}

      {ticket ? (
        <div className="banner banner-warn" style={{ marginBottom: 12, display: "block" }}>
          <div className="banner-title">
            {t("data.viol.ticket", { id: ticket.id, title: ticket.title })}
          </div>
          <div className="banner-body">
            {t("data.viol.ticketExpected", { expected: ticket.expected_value })}
          </div>
        </div>
      ) : null}

      {d.data && !d.data.rows.length ? (
        <p className="sub">{t("data.viol.empty")}</p>
      ) : null}

      {d.data?.rows.map((v) => (
        <div key={v.id} className="viol-row">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <Severity value={v.severity} />
            <span className="mono" style={{ fontSize: 12 }}>{v.rule_id}</span>
          </div>
          <div style={{ fontSize: 13, marginBottom: v.observed ? 6 : 0 }}>{v.message}</div>
          {v.observed ? (
            <dl className="kv">
              {Object.entries(v.observed).map(([k, val]) => (
                <div key={k} style={{ display: "contents" }}>
                  <dt>{k}</dt>
                  <dd className="mono">{String(val)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ))}

      {d.data ? (
        <p className="sub" style={{ marginTop: 12 }}>
          {tn("data.viol.run", { runId: <span className="mono">{d.data.run_id ?? "—"}</span> })}
          {d.data.rules_version
            ? t("data.viol.rulesVersion", { v: d.data.rules_version })
            : ""}
        </p>
      ) : null}
      <p className="sub" style={{ marginTop: 6 }}>{t("data.viol.groupNote")}</p>

      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginTop: 14 }}>
        {/* Bo loc nam tren URL, nen link nay mo thang man hinh Vi pham luat
            da loc san dung o — khong bat nguoi dung go lai bo loc. */}
        <Link
          className="btn btn-sm"
          href={`/exceptions${qs({
            state: fact.state, year: fact.year, institution: fact.institution,
          })}`}
        >
          {t("data.viol.goto")}
        </Link>
        <button type="button" className="btn" onClick={onClose}>{t("common.close")}</button>
      </div>
    </Modal>
  );
}
