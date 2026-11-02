/**
 * Data displays.
 *
 * Plain SVG/CSS, no charting dependency. Color is used to carry meaning —
 * the correlation scale runs clay (negative) through white to ink (positive),
 * so hue encodes the sign rather than decorating the cell.
 */

export function MissingBars({ rows }) {
  if (!rows.length) {
    return <p className="text-[13px] text-ink">No missing values — every column is complete.</p>;
  }
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.column} className="flex items-center gap-3">
          <span className="num w-32 shrink-0 truncate text-[12px]" title={r.column}>
            {r.column}
          </span>
          <div className="h-3 flex-1 bg-field">
            <div className="h-3 bg-clay/70" style={{ width: `${Math.min(r.missing_pct, 100)}%` }} />
          </div>
          <span className="num w-20 text-right text-[12px] text-slate/60">
            {r.missing} · {r.missing_pct}%
          </span>
        </div>
      ))}
    </div>
  );
}

export function Histogram({ bins }) {
  const max = Math.max(...bins.map((b) => b.count), 1);
  return (
    <div className="flex h-20 items-end gap-px">
      {bins.map((b, i) => (
        <div
          key={i}
          className="flex-1 bg-slate/25"
          style={{ height: `${(b.count / max) * 100}%`, minHeight: b.count ? "2px" : 0 }}
          title={`${b.label}: ${b.count}`}
        />
      ))}
    </div>
  );
}

export function Heatmap({ columns, matrix }) {
  if (!columns.length) {
    return (
      <p className="text-[13px] text-slate/45">
        Needs at least two numeric columns to compute correlations.
      </p>
    );
  }
  const color = (v) =>
    v >= 0
      ? `rgba(47,125,110,${Math.abs(v).toFixed(2)})`
      : `rgba(168,67,47,${Math.abs(v).toFixed(2)})`;

  return (
    <div className="overflow-x-auto">
      <table className="num border-separate border-spacing-px text-[11px]">
        <thead>
          <tr>
            <th />
            {columns.map((c) => (
              <th
                key={c}
                className="max-w-[64px] truncate px-1 pb-1 text-left font-normal text-slate/50"
                title={c}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={columns[i]}>
              <td className="max-w-[90px] truncate pr-2 text-right text-slate/50" title={columns[i]}>
                {columns[i]}
              </td>
              {row.map((v, j) => (
                <td
                  key={j}
                  className="h-8 w-14 text-center"
                  style={{
                    background: color(v),
                    color: Math.abs(v) > 0.6 ? "#fff" : "rgba(16,19,26,.7)",
                  }}
                  title={`${columns[i]} × ${columns[j]}: ${v}`}
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

export function ImportanceBars({ items }) {
  if (!items.length) {
    return <p className="text-[13px] text-slate/45">Importance could not be computed.</p>;
  }
  const max = Math.max(...items.map((i) => Math.abs(i.importance)), 0.0001);
  return (
    <div className="space-y-1.5">
      {items.map((f) => (
        <div key={f.feature} className="flex items-center gap-3">
          <span className="num w-32 shrink-0 truncate text-[12px]" title={f.feature}>
            {f.feature}
          </span>
          <div className="h-3 flex-1 bg-field">
            <div
              className="h-3 bg-ink/70"
              style={{ width: `${(Math.abs(f.importance) / max) * 100}%` }}
            />
          </div>
          <span className="num w-16 text-right text-[12px] text-slate/60">
            {f.importance.toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function DataTable({ rows, maxHeight = "auto" }) {
  if (!rows?.length) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="overflow-auto" style={{ maxHeight }}>
      <table className="w-full text-left text-[12px]">
        <thead className="sticky top-0 bg-field">
          <tr>
            {cols.map((c) => (
              <th key={c} className="num whitespace-nowrap px-4 py-2 font-medium text-slate/55">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-rule/60">
              {cols.map((c) => (
                <td key={c} className="num whitespace-nowrap px-4 py-1.5">
                  {String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
