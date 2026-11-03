/* Indian number formatting (₹, thousands, lakh and crore), shared by every screen. */

export function formatValue(v, unit) {
  if (v == null || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  const pre = unit === "money" ? "₹" : "";
  if (a >= 1e7) return `${sign}${pre}${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${sign}${pre}${(a / 1e5).toFixed(2)} L`;
  if (a >= 1000) return `${sign}${pre}${Math.round(a).toLocaleString("en-IN")}`;
  return `${sign}${pre}${a >= 10 ? a.toFixed(1).replace(/\.0$/, "") : a.toFixed(2).replace(/0$/, "").replace(/\.$/, "")}`;
}

/** "+₹12,400" / "−₹3,200" */
export const signedMoney = (v) => (v >= 0 ? "+" : "−") + formatValue(Math.abs(v), "money");

/** 0.034 -> "+3%" */
export const signedPct = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(Math.round(v * 100))}%`;

/** "2026-11-08" -> "8 Nov" */
export const shortDate = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};
