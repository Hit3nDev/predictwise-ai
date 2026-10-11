import { useEffect, useState } from "react";
import { rankRows, getLevers, scoreFile, downloadScored, detail } from "../api";
import { Button, Readout } from "./ui";

/* Rich answers: charts, stat strips, customer groups, unusual rows, batch
   scoring. Plain SVG/CSS like the rest of the app, with Indian number
   formatting (₹, thousands, lakh and crore) because that is who this is for. */

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const pretty = (s) => String(s).replace(/[_\s]+/g, " ").trim();

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

/* ---------------------------------------------------------------- charts */

function LineChart({ points, forecast = [], unit }) {
  const all = [...points, ...forecast];
  const W = 560, H = 190, L = 54, R = 12, T = 12, B = 26;
  const ys = all.flatMap((p) => [p.value, p.low ?? p.value, p.high ?? p.value]);
  const lo = Math.min(0, ...ys), hi = Math.max(...ys);
  const span = hi - lo || 1;
  const X = (i) => L + (i / Math.max(all.length - 1, 1)) * (W - L - R);
  const Y = (v) => T + (1 - (v - lo) / span) * (H - T - B);

  const actual = points.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p.value).toFixed(1)}`).join(" ");
  const n = points.length;
  const fPath = forecast.length
    ? [points[n - 1], ...forecast].map((p, i) => `${i ? "L" : "M"}${X(n - 1 + i).toFixed(1)},${Y(p.value).toFixed(1)}`).join(" ")
    : "";
  const band = forecast.length
    ? `M${X(n - 1)},${Y(points[n - 1].value)} ` +
      forecast.map((p, i) => `L${X(n + i).toFixed(1)},${Y(p.high).toFixed(1)}`).join(" ") + " " +
      [...forecast].reverse().map((p, i) => `L${X(n + forecast.length - 1 - i).toFixed(1)},${Y(p.low).toFixed(1)}`).join(" ") + " Z"
    : "";
  const ticks = [0, 0.5, 1];
  const labelIdx = [0, Math.floor((all.length - 1) / 2), all.length - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
      {ticks.map((t) => {
        const y = T + t * (H - T - B);
        return (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y} y2={y} style={{ stroke: "rgb(var(--rule))" }} />
            <text x={L - 6} y={y + 4} textAnchor="end" fontSize="10" className="num" style={{ fill: "rgb(var(--slate) / .5)" }}>
              {formatValue(hi - t * span, unit)}
            </text>
          </g>
        );
      })}
      {band && <path d={band} style={{ fill: "rgb(var(--clay) / .12)" }} />}
      <path d={actual} fill="none" strokeWidth="2" style={{ stroke: "rgb(var(--ink))" }} />
      {fPath && <path d={fPath} fill="none" strokeWidth="2" strokeDasharray="5 4" style={{ stroke: "rgb(var(--clay))" }} />}
      {points.map((p, i) => (
        <circle key={i} cx={X(i)} cy={Y(p.value)} r="2.5" style={{ fill: "rgb(var(--ink))" }}>
          <title>{`${p.label}: ${formatValue(p.value, unit)}`}</title>
        </circle>
      ))}
      {forecast.map((p, i) => (
        <circle key={i} cx={X(n + i)} cy={Y(p.value)} r="3" style={{ fill: "rgb(var(--clay))" }}>
          <title>{`${p.label} (forecast): ${formatValue(p.value, unit)} · likely ${formatValue(p.low, unit)} to ${formatValue(p.high, unit)}`}</title>
        </circle>
      ))}
      {[...new Set(labelIdx)].map((i) => (
        <text key={i} x={X(i)} y={H - 7} fontSize="10" textAnchor={i === 0 ? "start" : i === all.length - 1 ? "end" : "middle"}
              className="num" style={{ fill: "rgb(var(--slate) / .5)" }}>
          {all[i].label}
        </text>
      ))}
    </svg>
  );
}

function BarChart({ points, unit }) {
  const max = Math.max(...points.map((p) => Math.abs(p.value)), 1);
  return (
    <div className="space-y-1.5">
      {points.map((p) => (
        <div key={p.label} className="grid grid-cols-[minmax(0,9rem)_1fr_4.5rem] items-center gap-3">
          <span className="truncate text-[12.5px]" title={p.label}>{p.label}</span>
          <div className="h-3 bg-field"><div className="h-3 bg-ink/70" style={{ width: `${(Math.abs(p.value) / max) * 100}%` }} /></div>
          <span className="num text-right text-[12px] text-slate/60">{formatValue(p.value, unit)}</span>
        </div>
      ))}
    </div>
  );
}

function Chart({ block }) {
  return (
    <figure className="mt-3 border border-rule bg-paper p-3">
      <figcaption className="mb-2 text-[12.5px] text-slate/60">{block.title}</figcaption>
      {block.chart === "line"
        ? <LineChart points={block.points} forecast={block.forecast} unit={block.unit} />
        : <BarChart points={block.points} unit={block.unit} />}
      {block.forecast?.length > 0 && (
        <p className="mt-1.5 text-[11.5px] text-slate/45">
          Dashed line is a forecast; the shaded band is the range it will probably land in.
        </p>
      )}
    </figure>
  );
}

/* ---------------------------------------------------------------- others */

function Stats({ stats }) {
  return (
    <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
      {stats.map((s) => <Readout key={s.label} value={s.value} label={s.label} />)}
    </div>
  );
}

function Segments({ segments }) {
  return (
    <div className="mt-3 space-y-2">
      {segments.map((s) => (
        <div key={s.name} className="border border-rule bg-paper p-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[14px] font-medium">{s.name}</span>
            <span className="num text-[12px] text-slate/55">{s.size} · {Math.round(s.share * 100)}%</span>
          </div>
          <div className="mt-2 h-1.5 bg-field"><div className="h-1.5 bg-ink/70" style={{ width: `${s.share * 100}%` }} /></div>
          <p className="num mt-2 text-[12px] text-slate/60">
            {s.averages.map((a) => `${pretty(a.column)} ${a.display}`).join(" · ")}
          </p>
          {s.outcome && (
            <p className="mt-1 text-[12.5px] text-slate/70">
              {Math.round(s.outcome.rate * 100)}% {pretty(s.outcome.column)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function Anomalies({ rows }) {
  return (
    <div className="mt-3 space-y-2">
      {rows.map((r) => (
        <div key={r.row_number} className="border border-rule bg-paper p-3">
          <p className="text-[13px]"><span className="num text-slate/45">row {r.row_number}</span> · {r.reasons[0]}</p>
          <p className="num mt-1.5 truncate text-[11.5px] text-slate/50">
            {Object.entries(r.values).map(([k, v]) => `${k}: ${v ?? "–"}`).join("  ")}
          </p>
        </div>
      ))}
    </div>
  );
}

export function Blocks({ blocks }) {
  if (!blocks?.length) return null;
  return blocks.map((b, i) => {
    if (b.type === "chart") return <Chart key={i} block={b} />;
    if (b.type === "stats") return <Stats key={i} stats={b.stats} />;
    if (b.type === "segments") return <Segments key={i} segments={b.segments} />;
    if (b.type === "anomalies") return <Anomalies key={i} rows={b.rows} />;
    return null;
  });
}

export { Chart, Stats, Segments, Anomalies };

/* --------------------------------------------------- batch score + levers */

export function BatchScore({ modelId, plain }) {
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const run = () => {
    setBusy(true); setErr(""); setRes(null);
    scoreFile(modelId, file).then(setRes).catch((e) => setErr(detail(e, "Couldn't score that file."))).finally(() => setBusy(false));
  };
  const cols = res?.preview?.[0] ? Object.keys(res.preview[0]) : [];

  return (
    <div className="mt-3">
      <p className="mb-2 text-[12.5px] text-slate/55">
        {plain ? "Upload a sheet of new people or cases with the same columns. You get the answer for every row, with a note on which to double-check."
               : "CSV/Excel with the model's input columns. Adds predicted value, chance, confidence and trust per row (max 5,000 rows)."}
      </p>
      <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => { setFile(e.target.files[0]); setRes(null); }}
             className="block w-full text-[13px] text-slate/70 file:mr-3 file:cursor-pointer file:border file:border-slate/25 file:bg-paper file:px-3 file:py-1.5 file:text-[12px] file:text-slate hover:file:border-ink" />
      <div className="mt-3 flex gap-2">
        <Button onClick={run} disabled={!file || busy}>{busy ? "Scoring…" : "Score file"}</Button>
        {res && <Button variant="outline" onClick={() => downloadScored(modelId, file)}>Download with answers</Button>}
      </div>
      {err && <p className="mt-2 text-[13px] text-clay">{err}</p>}
      {res && (
        <div className="mt-4">
          <p className="text-[13px] text-slate/70">
            {res.summary.rows} rows scored.
            {res.summary.by_prediction && " " + Object.entries(res.summary.by_prediction).map(([k, v]) => `${v} × ${k}`).join(", ") + "."}
            {res.summary.average_prediction != null && ` Average prediction ${formatValue(res.summary.average_prediction)}.`}
            {res.summary.low_trust > 0 && ` ${res.summary.low_trust} used unfamiliar values, so double-check those.`}
          </p>
          <div className="mt-3 max-h-64 overflow-auto border border-rule">
            <table className="w-full text-left text-[12px]">
              <thead className="sticky top-0 bg-field"><tr>{cols.map((c) => <th key={c} className="num whitespace-nowrap px-3 py-1.5 font-medium">{c}</th>)}</tr></thead>
              <tbody>
                {res.preview.map((r, i) => (
                  <tr key={i} className="border-t border-rule/60">
                    {cols.map((c) => <td key={c} className={`num whitespace-nowrap px-3 py-1.5 ${c === "trust" && r[c] === "low" ? "text-clay" : ""}`}>{String(r[c] ?? "–")}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export function Levers({ modelId, row, plain }) {
  const [list, setList] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    getLevers(modelId, row).then((l) => live && setList(l)).catch((e) => live && setErr(detail(e, "Couldn't work that out.")));
    return () => { live = false; };
  }, [modelId, JSON.stringify(row)]);
  const isProb = list?.[0]?.output_kind === "probability";
  const fmt = (v) => (isProb ? `${Math.round(v * 100)}%` : formatValue(v));
  return (
    <div className="mt-3">
      {err && <p className="text-[13px] text-clay">{err}</p>}
      {list && list.length === 0 && <p className="text-[13px] text-slate/60">Nothing you can change would improve this much. It already looks strong.</p>}
      {list && list.length > 0 && (
        <ul className="space-y-2">
          {list.map((l) => (
            <li key={l.feature} className="border border-rule bg-paper px-3 py-2 text-[13px]">
              <span className="font-medium">{cap(pretty(l.feature))}</span>
              {l.current != null && <> from <span className="num">{String(l.current)}</span></>} to <span className="num">{String(l.best_value)}</span>
              <span className="num text-ink"> · {fmt(l.current_output)} → {fmt(l.best_output)}</span>
              {!l.changeable && <span className="text-slate/45"> · hard to change</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RankTable({ modelId }) {
  const [data, setData] = useState(null);
  const [dir, setDir] = useState("most");
  const [err, setErr] = useState("");
  const run = (d) => { setDir(d); rankRows(modelId, 10, d).then(setData).catch((e) => setErr(detail(e, "Couldn't rank."))); };
  const cols = data?.rows?.[0] ? Object.keys(data.rows[0]).filter((c) => c !== "trust") : [];
  return (
    <div>
      <div className="flex gap-2">
        <Button onClick={() => run("most")} variant={dir === "most" && data ? "solid" : "outline"}>Most likely</Button>
        <Button onClick={() => run("least")} variant={dir === "least" && data ? "solid" : "outline"}>Least likely</Button>
      </div>
      {err && <p className="mt-2 text-[13px] text-clay">{err}</p>}
      {data && (
        <>
          <p className="mt-3 text-[13px] text-slate/70">{data.headline}</p>
          <div className="mt-2 overflow-x-auto border border-rule">
            <table className="w-full text-left text-[12px]">
              <thead className="bg-field"><tr>{cols.map((c) => <th key={c} className="num whitespace-nowrap px-3 py-1.5 font-medium">{c}</th>)}</tr></thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i} className="border-t border-rule/60">
                    {cols.map((c) => <td key={c} className="num whitespace-nowrap px-3 py-1.5">{c === "chance" && r[c] != null ? `${Math.round(r[c] * 100)}%` : String(r[c] ?? "–")}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
