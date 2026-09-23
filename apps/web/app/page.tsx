"use client";

// Dashboard: tra loi ba cau hoi trong mot man hinh — du lieu co tuoi
// khong, co bao nhieu cho dang nghi ngo, va co ky duoc khong.

import Link from "next/link";
import {
  Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { useFmt, useI18n } from "@/app/i18n/context";
import { useFilters } from "@/app/lib/filters";
import { useGate, useSummary } from "@/app/lib/queries";
import { ErrBox, Loading, Stat } from "@/app/ui/bits";
import RulesButton from "@/app/ui/rules-panel";

export default function DashboardPage() {
  const { t, tn } = useI18n();
  const { num, signed } = useFmt();
  const { filters } = useFilters();
  const { data: s, isPending, error } = useSummary(filters);
  const { data: gate } = useGate();

  if (error) return <ErrBox error={error} />;
  if (isPending || !s) return <Loading what={t("dash.loading")} />;

  // Dem vi pham theo luat cua lan nap hien tai, de hop bo luat hien kem
  // moi luat "dang bat duoc bao nhieu o".
  const countsByRule = Object.fromEntries(s.exceptions.by_rule.map((r) => [r.rule_id, r.n]));

  const crit = s.exceptions.by_severity.critical ?? 0;
  const warn = s.exceptions.by_severity.warning ?? 0;
  const locked = s.gate.locked;
  const stale = s.gate.qc_stale;
  const staleRules = s.gate.qc_stale_reason === "rules";
  // Ba trang thai chu khong phai hai. "Con no" khong phai la khoa: team
  // lead ky duoc, mien la ky kem phieu duyet co ten.
  const tone = locked ? "crit" : s.gate.needs_approval ? "warn" : "good";

  return (
    <>
      <div className={`banner banner-${tone}`} style={{ marginBottom: 18 }}>
        <div>
          <div className="banner-title" style={{ color: `var(--${tone === "warn" ? "warn" : tone})` }}>
            {locked
              ? stale
                ? staleRules ? t("qc.staleRules.title") : t("dash.gate.stale")
                : t("dash.gate.locked")
              : s.gate.needs_approval
                ? t("dash.gate.debt")
                : t("dash.gate.ready")}
          </div>
          <div className="banner-body">
            {locked
              ? stale
                ? staleRules
                  ? t("qc.staleRules.body", {
                      current: s.gate.ruleset_version ?? "—", applied: s.gate.rules_version ?? "—",
                    })
                  : t("dash.gateBody.stale")
                : t("dash.gateBody.locked", { n: s.gate.blocking })
              : s.gate.needs_approval
                ? t("dash.gateBody.debt", {
                    v: num(s.exceptions.open),
                    t: num(s.tickets.open + s.tickets.awaiting_verify),
                  })
                : t("dash.gateBody.ready")}
          </div>
        </div>
        <Link
          className={`btn btn-sm ${locked ? "btn-danger" : "btn-good"}`}
          href={locked && !stale ? "/tickets" : "/versions"}
        >
          {locked && !stale ? t("dash.viewBlocking") : t("dash.goSign")}
        </Link>
      </div>

      <div className="grid-cards" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(156px, 1fr))", marginBottom: 18 }}>
        <Stat label={t("dash.stat.rows")} value={num(s.facts.rows)}
              note={`${s.facts.year_min ?? "—"}–${s.facts.year_max ?? "—"}`} />
        <Stat label={t("dash.stat.critical")} value={num(crit)} tone={crit ? "warn" : "good"}
              note={t("dash.stat.criticalNote")} />
        <Stat label={t("dash.stat.warning")} value={num(warn)} tone={warn ? "warn" : undefined} />
        <Stat label={t("dash.stat.flagged")} value={num(s.exceptions.flagged_rows)}
              note={t("dash.stat.flaggedNote", { runId: s.exceptions.run_id ?? "—" })} />
        <Stat label={t("dash.stat.blocking")} value={num(s.tickets.blocking)}
              tone={s.tickets.blocking ? "crit" : "good"}
              note={t("dash.stat.blockingNote", { n: num(s.tickets.awaiting_verify) })} />
        <Stat label={t("dash.stat.deposit")}
              value={<>{num(s.facts.total_deposit)} <span className="stat-unit">USD</span></>}
              note={t("dash.stat.depositNote")} />
      </div>

      <div className="split" style={{ marginBottom: 18 }}>
        <div className="card">
          <div className="card-head">
            <div>
              <h2>{t("dash.byRule.title")}</h2>
              <p className="sub">
                {tn("dash.byRule.sub", { file: <span className="mono">qc_rule</span> })}
              </p>
            </div>
            {/* Bieu do chi cho thay rule_id va so luong. Nut nay tra loi
                cau ke tiep — luat do noi gi — ma khong bat mo repo. */}
            <RulesButton counts={countsByRule} />
          </div>
          {s.exceptions.by_rule.length ? (
            <ResponsiveContainer width="100%" height={Math.max(140, s.exceptions.by_rule.length * 44)}>
              <BarChart data={s.exceptions.by_rule} layout="vertical" margin={{ left: 8, right: 16 }}>
                <XAxis type="number" tick={{ fontSize: 11, fill: "#6b7884" }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="rule_id" width={170} tick={{ fontSize: 11, fill: "#3c4853" }}
                       axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: "#edf1f4" }}
                         formatter={(v) => [num(Number(v)), t("dash.chart.exceptions")]} />
                <Bar dataKey="n" radius={[0, 4, 4, 0]} barSize={18}>
                  {s.exceptions.by_rule.map((r) => (
                    <Cell key={r.rule_id} fill={r.severity === "critical" ? "#a32b22" : "#9a5f09"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="sub">{t("dash.byRule.empty")}</p>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <h2>{t("dash.delta.title")}</h2>
            <Link className="btn btn-sm" href="/versions">
              {t("dash.delta.viewVersions")}
            </Link>
          </div>
          {s.last_signed ? (
            <>
              <dl className="kv" style={{ marginBottom: 12 }}>
                <dt>{t("dash.delta.signedVersion")}</dt>
                <dd>
                  <b>{s.last_signed.label}</b> · <span className="mono">{s.last_signed.run_id}</span>
                </dd>
                <dt>{t("dash.delta.signedBy")}</dt>
                <dd>{s.last_signed.signed_by}</dd>
                <dt>{t("dash.delta.thisRun")}</dt>
                <dd className="mono">{s.sync?.last_run_id ?? "—"}</dd>
              </dl>
              <div className="compare">
                <div>
                  <div className="stat-label">{t("dash.delta.rowsAtSign")}</div>
                  <div className="big">{num(s.delta.rows_signed)}</div>
                </div>
                <div>
                  <div className="stat-label">{t("dash.delta.rowsNow")}</div>
                  <div className="big">{num(s.delta.rows_now)}</div>
                  <div className={`stat-note ${s.delta.rows_delta ? "tone-warn" : "tone-good"}`}>
                    {t("dash.delta.rowsUnit", { n: signed(s.delta.rows_delta) })}
                  </div>
                </div>
              </div>
              <p className="sub" style={{ marginTop: 10 }}>
                {s.delta.run_changed ? t("dash.delta.runChanged") : t("dash.delta.runSame")}{" "}
                {s.delta.tickets_since > 0
                  ? t("dash.delta.ticketsSince", {
                      n: num(s.delta.tickets_since),
                      count: s.delta.tickets_since,
                    })
                  : t("dash.delta.noTicketsSince")}{" "}
                {/* Tap vi pham doi ma tong so co the y het — chi van tay
                    phan biet duoc hai truong hop nay. */}
                {s.delta.violations_changed ? t("dash.delta.violationsChanged") : null}
              </p>
            </>
          ) : (
            <p className="sub">
              {tn("dash.delta.empty", {
                link: <Link href="/versions">{t("dash.delta.emptyLink")}</Link>,
              })}
            </p>
          )}
        </div>
      </div>

      {s.exceptions.by_state.length ? (
        <div className="card">
          <div className="card-head">
            <h2>{t("dash.byState.title")}</h2>
            <p className="sub">
              {gate?.last_signed
                ? t("dash.byState.lastSigned", { label: gate.last_signed.label })
                : t("dash.byState.noneSigned")}
            </p>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={s.exceptions.by_state} margin={{ left: 0, right: 8 }}>
              <XAxis dataKey="state" tick={{ fontSize: 11, fill: "#3c4853" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#6b7884" }} axisLine={false} tickLine={false} width={34} />
              <Tooltip cursor={{ fill: "#edf1f4" }}
                       formatter={(v) => [num(Number(v)), t("dash.chart.exceptions")]} />
              <Bar dataKey="n" fill="#0f6b7b" radius={[4, 4, 0, 0]} barSize={26} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </>
  );
}
