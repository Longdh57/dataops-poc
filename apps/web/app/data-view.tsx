const C = {
  ink: "#131A21", ink2: "#3C4853", muted: "#6B7884",
  line: "#D4DCE3", lineSoft: "#E4EAEF",
  surface: "#FFFFFF", surface2: "#EDF1F4",
  accent: "#0F6B7B", accentSoft: "#DCEEF1",
  good: "#1C7A46", goodSoft: "#DDF0E4",
  warn: "#9A5F09", warnSoft: "#F7EBD8",
  crit: "#A32B22", critSoft: "#F7E2E0",
  mono: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

export default function DataView({ users, current, me, version, gate, exceptions, facts }: any) {
  const locked = gate?.locked;

  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: "48px 20px 80px" }}>
      <p style={{ fontFamily: C.mono, fontSize: 11.5, letterSpacing: ".14em",
                  textTransform: "uppercase", color: C.accent, margin: "0 0 10px" }}>
        P3 · Phân quyền & cổng phát hành
      </p>
      <h1 style={{ fontSize: 30, margin: "0 0 20px", letterSpacing: "-.02em" }}>
        Data Operations WebApp
      </h1>

      {/* ---- chọn danh tính ---- */}
      <div style={{ border: `1px solid ${C.line}`, borderRadius: 9, background: C.surface,
                    padding: 14, marginBottom: 20 }}>
        <div style={{ fontSize: 11, fontFamily: C.mono, letterSpacing: ".1em",
                      textTransform: "uppercase", color: C.muted, marginBottom: 9 }}>
          Đăng nhập với tư cách — đổi để thấy phân quyền hoạt động
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
          {users.map((u: any) => {
            const on = u.email === current;
            return (
              <a key={u.email} href={`?as=${encodeURIComponent(u.email)}`}
                 style={{ fontSize: 12.5, padding: "6px 11px", borderRadius: 6,
                          textDecoration: "none", border: `1px solid ${on ? C.accent : C.line}`,
                          background: on ? C.accentSoft : C.surface,
                          color: on ? C.accent : C.ink2, fontWeight: on ? 600 : 400 }}>
                {u.label}
              </a>
            );
          })}
        </div>
        {me && (
          <div style={{ marginTop: 11, fontSize: 12.5, color: C.ink2, fontFamily: C.mono }}>
            {me.email} · vai trò <b>{me.roles?.join(", ")}</b> · phạm vi{" "}
            <b style={{ color: C.accent }}>
              {Array.isArray(me.scope_states) ? me.scope_states.join(", ") : me.scope_states}
            </b>
          </div>
        )}
      </div>

      {/* ---- cổng phát hành ---- */}
      <div style={{ borderLeft: `3px solid ${locked ? C.crit : C.good}`,
                    background: locked ? C.critSoft : C.goodSoft,
                    padding: "13px 16px", borderRadius: "0 8px 8px 0", marginBottom: 22 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: locked ? C.crit : C.good }}>
          {locked ? "Cổng phát hành đang KHOÁ" : "Cổng phát hành sẵn sàng"}
        </div>
        <div style={{ fontSize: 13, color: C.ink2, marginTop: 3 }}>
          {locked
            ? `Còn ${gate.blocking} ngoại lệ nghiêm trọng chưa xử lý — không ai ký hay tải file được.`
            : "Không còn ngoại lệ nghiêm trọng. Team Lead có thể ký."}
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 26 }}>
        <Stat label="Lần nạp" value={version?.run_id ?? "—"} mono />
        <Stat label="Số dòng" value={version?.row_count?.toLocaleString("vi-VN") ?? "—"} />
        <Stat label="Đồng bộ cách đây"
              value={version?.age_seconds != null ? `${version.age_seconds}s` : "—"}
              tone={version?.stale ? "bad" : "good"} />
        <Stat label="Ngoại lệ nghiêm trọng" value={gate?.open_by_severity?.critical ?? 0}
              tone={gate?.open_by_severity?.critical ? "bad" : "good"} />
        <Stat label="Cảnh báo" value={gate?.open_by_severity?.warning ?? 0} tone="warn" />
      </div>

      {/* ---- ngoại lệ ---- */}
      <Section title="Hộp thư ngoại lệ"
               sub={`${exceptions?.total?.toLocaleString("vi-VN") ?? 0} ngoại lệ đang mở trong phạm vi của bạn`}>
        {exceptions?.rows?.length ? (
          <table style={tableStyle}>
            <thead><tr>{["Mức", "Luật", "Khoá", "Số liệu quan sát"].map((h) =>
              <th key={h} style={thStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {exceptions.rows.map((e: any) => (
                <tr key={e.id}>
                  <td style={tdStyle}><Badge severity={e.severity} /></td>
                  <td style={{ ...tdStyle, fontFamily: C.mono, fontSize: 12 }}>{e.rule_id}</td>
                  <td style={{ ...tdStyle, fontFamily: C.mono, fontSize: 12, color: C.ink }}>
                    {[e.state, e.gender, e.year, e.name].filter(Boolean).join(" · ")}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: C.mono, fontSize: 11.5, color: C.muted }}>
                    {JSON.stringify(e.observed)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>Không có ngoại lệ nào trong phạm vi của bạn.</Empty>}
      </Section>

      {/* ---- dữ liệu ---- */}
      <Section title="Dữ liệu trong phạm vi"
               sub={`Phạm vi áp ở tầng server — đổi tham số trên URL không lấy được dữ liệu ngoài phạm vi`}>
        {facts?.rows?.length ? (
          <table style={tableStyle}>
            <thead><tr>
              {["Bang", "Năm", "Giới", "Tên", "Số trẻ", "Thị phần"].map((h, i) =>
                <th key={h} style={{ ...thStyle, textAlign: i >= 4 ? "right" : "left" }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {facts.rows.map((r: any) => (
                <tr key={`${r.state}-${r.year}-${r.gender}-${r.name}`}>
                  <td style={{ ...tdStyle, fontFamily: C.mono, color: C.accent, fontWeight: 600 }}>{r.state}</td>
                  <td style={{ ...tdStyle, fontFamily: C.mono }}>{r.year}</td>
                  <td style={{ ...tdStyle, fontFamily: C.mono }}>{r.gender}</td>
                  <td style={{ ...tdStyle, color: C.ink, fontWeight: 500 }}>
                    {r.name}{r.overridden && <span style={{ ...pillStyle }}>đã sửa</span>}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {r.number.toLocaleString("vi-VN")}
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right", fontFamily: C.mono, fontSize: 12.5 }}>
                    {(r.market_share * 100).toFixed(3)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>Không có dữ liệu trong phạm vi của bạn.</Empty>}
      </Section>

      <p style={{ fontSize: 12, color: C.muted, marginTop: 24, lineHeight: 1.6 }}>
        Bộ chọn danh tính ở trên chỉ tồn tại khi <code>REQUIRE_IAP=false</code>. Bật IAP lên
        thì danh tính đến từ JWT do Google ký và không giả được.
      </p>
    </main>
  );
}

function Badge({ severity }: any) {
  const map: any = {
    critical: [C.crit, C.critSoft, "nghiêm trọng"],
    warning: [C.warn, C.warnSoft, "cảnh báo"],
  };
  const [fg, bg, label] = map[severity] ?? [C.muted, C.surface2, severity];
  return (
    <span style={{ fontFamily: C.mono, fontSize: 10.5, fontWeight: 600, padding: "3px 7px",
                   borderRadius: 4, color: fg, background: bg, whiteSpace: "nowrap" }}>
      {label}
    </span>
  );
}

function Section({ title, sub, children }: any) {
  return (
    <section style={{ marginBottom: 30 }}>
      <h2 style={{ fontSize: 16, margin: "0 0 3px", letterSpacing: "-.01em" }}>{title}</h2>
      <p style={{ margin: "0 0 12px", fontSize: 13, color: C.muted }}>{sub}</p>
      <div style={{ border: `1px solid ${C.line}`, borderRadius: 9,
                    background: C.surface, padding: 14, overflowX: "auto" }}>{children}</div>
    </section>
  );
}

function Stat({ label, value, tone, mono }: any) {
  const color = tone === "good" ? C.good : tone === "bad" ? C.crit
              : tone === "warn" ? C.warn : C.ink;
  return (
    <div style={{ border: `1px solid ${C.line}`, borderRadius: 8, padding: "10px 14px",
                  background: C.surface, minWidth: 120 }}>
      <div style={{ fontSize: 10.5, letterSpacing: ".1em", textTransform: "uppercase",
                    color: C.muted, marginBottom: 4, fontFamily: C.mono }}>{label}</div>
      <div style={{ fontSize: mono ? 12.5 : 17, fontWeight: 600, color,
                    fontFamily: mono ? C.mono : "inherit" }}>{value}</div>
    </div>
  );
}

const Empty = ({ children }: any) => (
  <p style={{ margin: 0, padding: "14px 2px", color: C.muted, fontSize: 13.5 }}>{children}</p>
);

const tableStyle: any = { borderCollapse: "collapse", width: "100%", fontSize: 13.5 };
const thStyle: any = {
  fontFamily: C.mono, fontSize: 10.5, letterSpacing: ".1em", textTransform: "uppercase",
  color: C.muted, fontWeight: 600, padding: "8px 11px", textAlign: "left",
  borderBottom: `1px solid ${C.line}`, whiteSpace: "nowrap",
};
const tdStyle: any = { padding: "9px 11px", borderBottom: `1px solid ${C.lineSoft}`, color: C.ink2 };
const pillStyle: any = {
  fontFamily: C.mono, fontSize: 10, marginLeft: 7, padding: "2px 6px",
  borderRadius: 4, background: C.warnSoft, color: C.warn,
};
