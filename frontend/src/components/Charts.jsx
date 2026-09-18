/**
 * Lightweight chart components built with plain SVG/CSS.
 * Deliberately dependency-free so the EDA dashboard works without a
 * charting library; can be swapped for Plotly/Recharts later if needed.
 */

export function BarChart({ data, labelKey, valueKey, suffix = "" }) {
  if (!data?.length) {
    return <p className="text-sm text-slate-400">No data to display.</p>;
  }
  const max = Math.max(...data.map((d) => d[valueKey])) || 1;

  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d[labelKey]} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-xs text-slate-600" title={d[labelKey]}>
            {d[labelKey]}
          </span>
          <div className="h-5 flex-1 rounded bg-slate-100">
            <div
              className="h-5 rounded bg-accent transition-all"
              style={{ width: `${(d[valueKey] / max) * 100}%` }}
            />
          </div>
          <span className="w-16 shrink-0 text-right text-xs tabular-nums text-slate-600">
            {d[valueKey]}
            {suffix}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Histogram({ bins }) {
  if (!bins?.length) return null;
  const max = Math.max(...bins.map((b) => b.count)) || 1;

  return (
    <div className="flex h-32 items-end gap-1">
      {bins.map((b, i) => (
        <div key={i} className="group flex flex-1 flex-col items-center justify-end">
          <span className="mb-1 text-[10px] text-slate-400 opacity-0 group-hover:opacity-100">
            {b.count}
          </span>
          <div
            className="w-full rounded-t bg-accent/80 transition-all group-hover:bg-accent"
            style={{ height: `${(b.count / max) * 100}%`, minHeight: b.count ? "3px" : "0" }}
            title={`${b.label}: ${b.count}`}
          />
        </div>
      ))}
    </div>
  );
}

export function CorrelationHeatmap({ columns, matrix }) {
  if (!columns?.length) {
    return (
      <p className="text-sm text-slate-400">
        Needs at least two numeric columns to compute correlations.
      </p>
    );
  }

  // Blue for positive correlation, red for negative, white near zero.
  const cellColor = (v) => {
    const a = Math.abs(v);
    return v >= 0
      ? `rgba(43, 108, 176, ${a.toFixed(2)})`
      : `rgba(197, 48, 48, ${a.toFixed(2)})`;
  };

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-[11px]">
        <thead>
          <tr>
            <th className="p-1" />
            {columns.map((c) => (
              <th key={c} className="max-w-[70px] truncate p-1 text-left font-medium text-slate-500" title={c}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={columns[i]}>
              <td className="max-w-[90px] truncate p-1 pr-2 font-medium text-slate-500" title={columns[i]}>
                {columns[i]}
              </td>
              {row.map((v, j) => (
                <td
                  key={j}
                  className="h-9 w-14 border border-white text-center tabular-nums"
                  style={{
                    backgroundColor: cellColor(v),
                    color: Math.abs(v) > 0.55 ? "white" : "#334155",
                  }}
                  title={`${columns[i]} vs ${columns[j]}: ${v}`}
                >
                  {v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StatCard({ label, value, tone = "default" }) {
  const tones = {
    default: "bg-white border-slate-200 text-navy",
    warn: "bg-amber-50 border-amber-200 text-amber-800",
    good: "bg-emerald-50 border-emerald-200 text-emerald-800",
  };
  return (
    <div className={`rounded-lg border p-4 ${tones[tone]}`}>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      <p className="mt-0.5 text-xs text-slate-500">{label}</p>
    </div>
  );
}
