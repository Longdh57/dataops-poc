"use client";

// Dashboard: tra loi ba cau hoi trong mot man hinh — du lieu co tuoi
// khong, co bao nhieu cho dang nghi ngo, va co ky duoc khong.

import Link from "next/link";
import {
  Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { num, signed } from "@/app/lib/format";
import { useFilters } from "@/app/lib/filters";
import { useGate, useSummary } from "@/app/lib/queries";
import { ErrBox, Loading, Stat } from "@/app/ui/bits";

export default function DashboardPage() {
  const { filters } = useFilters();
  const { data: s, isPending, error } = useSummary(filters);
  const { data: gate } = useGate();

  if (error) return <ErrBox error={error} />;
  if (isPending || !s) return <Loading what="dashboard" />;

  const crit = s.exceptions.by_severity.critical ?? 0;
  const warn = s.exceptions.by_severity.warning ?? 0;
  const locked = s.gate.locked;

  return (
    <>
      <div className={`banner ${locked ? "banner-crit" : "banner-good"}`} style={{ marginBottom: 18 }}>
        <div>
          <div className="banner-title" style={{ color: locked ? "var(--crit)" : "var(--good)" }}>
            {locked ? "Cổng phát hành đang KHOÁ" : "Cổng phát hành sẵn sàng"}
          </div>
          <div className="banner-body">
            {locked
              ? `Còn ${num(s.gate.blocking)} ngoại lệ nghiêm trọng trên toàn bộ dữ liệu — không ai ký và không ai tải file được.`
              : "Không còn ngoại lệ nghiêm trọng. Team Lead có thể ký phát hành."}
          </div>
        </div>
        <Link className={`btn btn-sm ${locked ? "btn-danger" : "btn-good"}`} href={locked ? "/exceptions" : "/versions"}>
          {locked ? "Mở hộp thư ngoại lệ" : "Sang trang ký"}
        </Link>
      </div>

      <div className="grid-cards" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(156px, 1fr))", marginBottom: 18 }}>
        <Stat label="Dòng trong phạm vi" value={num(s.facts.rows)}
              note={`${s.facts.year_min ?? "—"}–${s.facts.year_max ?? "—"}`} />
        <Stat label="Ngoại lệ nghiêm trọng" value={num(crit)} tone={crit ? "crit" : "good"}
              note="trong phạm vi của bạn" />
        <Stat label="Cảnh báo" value={num(warn)} tone={warn ? "warn" : undefined}
              note="không khoá cổng" />
        <Stat label="Dòng bị gắn cờ" value={num(s.exceptions.flagged_rows)}
              note={`${num(s.exceptions.resolved)} đã xử lý`} />
        <Stat label="Số đã sửa tay" value={num(s.overrides)}
              note={`${num(s.delta.overrides_since)} kể từ bản ký gần nhất`} />
        <Stat label="Tổng số trẻ" value={num(s.facts.total_number)} note="sau khi áp override" />
      </div>

      <div className="split" style={{ marginBottom: 18 }}>
        <div className="card">
          <div className="card-head">
            <h2>Ngoại lệ theo luật</h2>
            <p className="sub">Luật khai báo trong <span className="mono">rules/rules.yaml</span></p>
          </div>
          {s.exceptions.by_rule.length ? (
            <ResponsiveContainer width="100%" height={Math.max(140, s.exceptions.by_rule.length * 44)}>
              <BarChart data={s.exceptions.by_rule} layout="vertical" margin={{ left: 8, right: 16 }}>
                <XAxis type="number" tick={{ fontSize: 11, fill: "#6b7884" }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="rule_id" width={170} tick={{ fontSize: 11, fill: "#3c4853" }}
                       axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: "#edf1f4" }} formatter={(v) => [num(Number(v)), "ngoại lệ"]} />
                <Bar dataKey="n" radius={[0, 4, 4, 0]} barSize={18}>
                  {s.exceptions.by_rule.map((r) => (
                    <Cell key={r.rule_id} fill={r.severity === "critical" ? "#a32b22" : "#9a5f09"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="sub">Không còn ngoại lệ nào đang mở.</p>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Chênh lệch so với bản đã ký</h2>
          </div>
          {s.last_signed ? (
            <>
              <dl className="kv" style={{ marginBottom: 12 }}>
                <dt>bản ký</dt>
                <dd>
                  <b>{s.last_signed.label}</b> · <span className="mono">{s.last_signed.run_id}</span>
                </dd>
                <dt>người ký</dt>
                <dd>{s.last_signed.signed_by}</dd>
                <dt>lần nạp này</dt>
                <dd className="mono">{s.sync?.last_run_id ?? "—"}</dd>
              </dl>
              <div className="compare">
                <div>
                  <div className="stat-label">Số dòng khi ký</div>
                  <div className="big">{num(s.delta.rows_signed)}</div>
                </div>
                <div>
                  <div className="stat-label">Số dòng bây giờ</div>
                  <div className="big">{num(s.delta.rows_now)}</div>
                  <div className={`stat-note ${s.delta.rows_delta ? "tone-warn" : "tone-good"}`}>
                    {signed(s.delta.rows_delta)} dòng
                  </div>
                </div>
              </div>
              <p className="sub" style={{ marginTop: 10 }}>
                {s.delta.run_changed
                  ? "Đã có lần nạp mới sau khi ký — số trên màn hình không còn là số đã ký."
                  : "Vẫn đang ở đúng lần nạp đã ký."}{" "}
                {s.delta.overrides_since > 0
                  ? `${num(s.delta.overrides_since)} ô đã sửa tay kể từ đó.`
                  : "Chưa có ô nào sửa tay kể từ đó."}
              </p>
            </>
          ) : (
            <p className="sub">
              Chưa có bản nào được ký. Xử lý hết ngoại lệ nghiêm trọng rồi sang{" "}
              <Link href="/versions">trang phiên bản</Link> để ký bản đầu tiên.
            </p>
          )}
        </div>
      </div>

      {s.exceptions.by_state.length ? (
        <div className="card">
          <div className="card-head">
            <h2>Ngoại lệ theo khu vực</h2>
            <p className="sub">{gate?.last_signed ? `Bản ký gần nhất: ${gate.last_signed.label}` : "Chưa ký bản nào"}</p>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={s.exceptions.by_state} margin={{ left: 0, right: 8 }}>
              <XAxis dataKey="state" tick={{ fontSize: 11, fill: "#3c4853" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#6b7884" }} axisLine={false} tickLine={false} width={34} />
              <Tooltip cursor={{ fill: "#edf1f4" }} formatter={(v) => [num(Number(v)), "ngoại lệ"]} />
              <Bar dataKey="n" fill="#0f6b7b" radius={[4, 4, 0, 0]} barSize={26} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </>
  );
}
