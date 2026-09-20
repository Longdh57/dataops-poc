const C = {
  ink: "#131A21", ink2: "#3C4853", muted: "#6B7884",
  line: "#D4DCE3", lineSoft: "#E4EAEF",
  surface: "#FFFFFF", surface2: "#EDF1F4",
  accent: "#0F6B7B", good: "#1C7A46", crit: "#A32B22",
  mono: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

export default function DataView({ version, schema, facts, apiUrl }: any) {
  const ok = version?.status === "ok";

  return (
    <main style={{ maxWidth: 940, margin: "0 auto", padding: "56px 20px 80px" }}>
      <p style={{ fontFamily: C.mono, fontSize: 11.5, letterSpacing: ".14em",
                  textTransform: "uppercase", color: C.accent, margin: "0 0 12px" }}>
        P2 · BigQuery → Cloud SQL
      </p>
      <h1 style={{ fontSize: 32, margin: "0 0 8px", letterSpacing: "-.02em" }}>
        Data Operations WebApp
      </h1>
      <p style={{ color: C.ink2, margin: "0 0 28px", fontSize: 15 }}>
        Dữ liệu tên khai sinh Hoa Kỳ 2009–2021, đồng bộ từ BigQuery sang Postgres.
      </p>

      {/* ---- banner độ tươi ---- */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 28 }}>
        <Stat label="Lần nạp" value={version?.run_id ?? "—"} mono />
        <Stat label="Số dòng" value={version?.row_count?.toLocaleString("vi-VN") ?? "—"} />
        <Stat label="Đồng bộ cách đây"
              value={version?.age_seconds != null ? `${version.age_seconds}s` : "—"}
              tone={version?.stale ? "bad" : "good"} />
        <Stat label="Trạng thái" value={version?.status ?? "—"} tone={ok ? "good" : "bad"} />
      </div>

      {/* ---- schema Postgres ---- */}
      <Section title="Schema trên Postgres" sub="Toàn bộ bảng trong Cloud SQL">
        <table style={tableStyle}>
          <thead><tr>{["Bảng", "Số dòng", "Dung lượng"].map((h, i) =>
            <th key={h} style={{ ...thStyle, textAlign: i === 0 ? "left" : "right" }}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(schema?.tables ?? []).map((t: any) => (
              <tr key={t.table_name}>
                <td style={{ ...tdStyle, fontFamily: C.mono, color: C.ink }}>{t.table_name}</td>
                <td style={{ ...tdStyle, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {Number(t.est_rows).toLocaleString("vi-VN")}
                </td>
                <td style={{ ...tdStyle, textAlign: "right", color: C.muted }}>{t.size}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {/* ---- cấu trúc fact_current ---- */}
      <Section title="Cấu trúc fact_current" sub="Khoá chính là khoá tự nhiên — bảng bị thay nguyên khối mỗi lần sync">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
          {(schema?.fact_current?.columns ?? []).map((c: any) => (
            <span key={c.column_name} style={chipStyle}>
              <b style={{ color: C.ink }}>{c.column_name}</b>
              <span style={{ color: C.muted, marginLeft: 6 }}>{c.data_type}</span>
            </span>
          ))}
        </div>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: C.muted, fontFamily: C.mono }}>
          {(schema?.fact_current?.indexes ?? []).map((i: any) => (
            <li key={i.indexname} style={{ marginBottom: 3 }}>{i.indexname}</li>
          ))}
        </ul>
      </Section>

      {/* ---- dữ liệu thật ---- */}
      <Section title="Dữ liệu — California, nữ, 2021"
               sub={`${facts?.total?.toLocaleString("vi-VN") ?? 0} dòng khớp bộ lọc, hiển thị ${facts?.rows?.length ?? 0}`}>
        <table style={tableStyle}>
          <thead><tr>
            {["Tên", "Số trẻ", "Thị phần", "Năm trước"].map((h, i) =>
              <th key={h} style={{ ...thStyle, textAlign: i === 0 ? "left" : "right" }}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(facts?.rows ?? []).map((r: any) => {
              const delta = r.prev_number ? r.number / r.prev_number - 1 : null;
              return (
                <tr key={`${r.name}-${r.year}`}>
                  <td style={{ ...tdStyle, color: C.ink, fontWeight: 500 }}>{r.name}</td>
                  <td style={{ ...tdStyle, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {r.number.toLocaleString("vi-VN")}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, fontSize: 12.5 }}>
                    {(r.market_share * 100).toFixed(3)}%
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, fontSize: 12.5,
                               color: delta == null ? C.muted : delta >= 0 ? C.good : C.crit }}>
                    {delta == null ? "—" : `${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)}%`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Section>

      <p style={{ marginTop: 28, fontSize: 12.5, color: C.muted, fontFamily: C.mono }}>
        API_URL = {apiUrl}
      </p>
    </main>
  );
}

function Section({ title, sub, children }: any) {
  return (
    <section style={{ marginBottom: 34 }}>
      <h2 style={{ fontSize: 16, margin: "0 0 3px", letterSpacing: "-.01em" }}>{title}</h2>
      <p style={{ margin: "0 0 14px", fontSize: 13, color: C.muted }}>{sub}</p>
      <div style={{ border: `1px solid ${C.line}`, borderRadius: 9,
                    background: C.surface, padding: 16, overflowX: "auto" }}>
        {children}
      </div>
    </section>
  );
}

function Stat({ label, value, tone, mono }: any) {
  const color = tone === "good" ? C.good : tone === "bad" ? C.crit : C.ink;
  return (
    <div style={{ border: `1px solid ${C.line}`, borderRadius: 8, padding: "10px 14px",
                  background: C.surface, minWidth: 130 }}>
      <div style={{ fontSize: 10.5, letterSpacing: ".1em", textTransform: "uppercase",
                    color: C.muted, marginBottom: 4, fontFamily: C.mono }}>{label}</div>
      <div style={{ fontSize: mono ? 13 : 17, fontWeight: 600, color,
                    fontFamily: mono ? C.mono : "inherit" }}>{value}</div>
    </div>
  );
}

const tableStyle: any = { borderCollapse: "collapse", width: "100%", fontSize: 13.5 };
const thStyle: any = {
  fontFamily: C.mono, fontSize: 10.5, letterSpacing: ".1em", textTransform: "uppercase",
  color: C.muted, fontWeight: 600, padding: "8px 12px",
  borderBottom: `1px solid ${C.line}`, whiteSpace: "nowrap",
};
const tdStyle: any = { padding: "9px 12px", borderBottom: `1px solid ${C.lineSoft}`, color: C.ink2 };
const chipStyle: any = {
  fontFamily: C.mono, fontSize: 11.5, padding: "4px 9px",
  border: `1px solid ${C.line}`, borderRadius: 5, background: C.surface2,
};
