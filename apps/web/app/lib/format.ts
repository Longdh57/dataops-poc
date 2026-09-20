export const num = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("vi-VN");

export const pct = (x: number | null | undefined, digits = 3) =>
  x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;

export const signed = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${n > 0 ? "+" : ""}${n.toLocaleString("vi-VN")}`;

export function dt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

/** "12 phút trước" — doc nhanh hon mot moc thoi gian tuyet doi. */
export function ago(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 90) return `${Math.round(seconds)} giây`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} phút`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} giờ`;
  return `${Math.round(seconds / 86400)} ngày`;
}
