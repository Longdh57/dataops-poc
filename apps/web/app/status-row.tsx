export default function StatusRow({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "13px 16px",
        background: "#FFFFFF",
        border: "1px solid #D4DCE3",
        borderRadius: 9,
        marginBottom: 10,
      }}
    >
      <span
        aria-hidden
        style={{
          width: 9,
          height: 9,
          borderRadius: "50%",
          background: ok ? "#1C7A46" : "#A32B22",
          flex: "0 0 auto",
        }}
      />
      <strong style={{ fontSize: 14, minWidth: 150 }}>{label}</strong>
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: 12.5,
          color: "#6B7884",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {detail}
      </span>
    </div>
  );
}
