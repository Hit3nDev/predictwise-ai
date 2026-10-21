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

const TONE = {
  do:    { bar: "bg-ink",      word: "text-ink" },
  watch: { bar: "bg-clay",     word: "text-clay" },
  good:  { bar: "bg-slate/40", word: "text-slate/70" },
};

/* A to-do list, most useful first. The coloured edge says what kind of item
   it is: green to act on, clay to look at, grey for good news. */
function Playbook({ items }) {
  return (
    <ul className="mt-3 space-y-2">
      {items.map((it, i) => (
        <li key={i} className="flex border border-rule bg-paper">
          <span className={`w-1 shrink-0 ${TONE[it.tone]?.bar ?? "bg-rule"}`} />
          <div className="px-3 py-2.5">
            <p className="text-[14px] font-medium">{it.title}</p>
            <p className="mt-0.5 text-[13px] text-slate/65">{it.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

/* The exact calculations behind an AI answer: the check a chat assistant
   that recalls numbers from memory cannot offer. */
function Work({ steps, label }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 border-t border-rule pt-2.5">
      <button onClick={() => setOpen(!open)} className="text-[13px] text-ink hover:underline underline-offset-2">
        {label} <span className="num text-slate/40">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {steps.map((s, i) => (
            <div key={i} className="border border-rule bg-field px-3 py-2">
              <p className="num break-all text-[12px]">{s.expr}</p>
              <p className="num mt-1 break-all text-[12px] text-ink">= {s.result}</p>
            </div>
          ))}
          <p className="text-[11.5px] text-slate/45">Calculated from your file by code, not remembered or guessed.</p>
        </div>
      )}
    </div>
  );
}

const csvCell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

/* A plain table of results (order list, customer groups, call list) that can be
   taken away as a spreadsheet file: the shopkeeper's actual next step. */
function TableBlock({ block, downloadLabel }) {
  const { columns, rows, caption, csv } = block;
  const save = () => {
    const text = [columns.map(csvCell).join(","), ...rows.map((r) => columns.map((c) => csvCell(r[c])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob(["\ufeff" + text], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = csv || "table.csv"; a.click();
    URL.revokeObjectURL(url);
  };
  const TREND = { rising: "text-ink", falling: "text-clay" };
  return (
    <div className="mt-3">
      {caption && <p className="mb-1.5 text-[12.5px] text-slate/60">{caption}</p>}
      <div className="overflow-x-auto border border-rule">
        <table className="w-full text-left text-[12.5px]">
          <thead className="bg-field text-slate/55">
            <tr>{columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-rule/60 align-top">
                {columns.map((c) => (
                  <td key={c} className={`px-3 py-2 ${typeof r[c] === "string" && r[c].length > 40 ? "min-w-[14rem]" : ""} ${typeof r[c] === "number" ? "num text-right" : ""} ${c === "Trend" ? TREND[r[c]] ?? "text-slate/60" : ""}`}>
                    {typeof r[c] === "number" ? r[c].toLocaleString("en-IN") : r[c]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {csv && <button onClick={save} className="mt-1.5 text-[12.5px] text-ink hover:underline underline-offset-2">{downloadLabel}</button>}
    </div>
  );
}

const MSG_DEFAULTS = { send: "Send on WhatsApp", copy: "Copy", copied: "Copied", noNumber: "No number on file. WhatsApp will let you pick the contact.", showAll: "Show all" };

/** Ready-to-send texts. Each one can be edited before it opens in WhatsApp. */
function Messages({ messages, labels }) {
  const L = { ...MSG_DEFAULTS, ...labels };
  const [texts, setTexts] = useState(() => messages.map((m) => m.text));
  const [done, setDone] = useState(null);
  const [all, setAll] = useState(false);
  const link = (m, i) => `https://wa.me/${m.phone || ""}?text=${encodeURIComponent(texts[i])}`;
  const copy = async (i) => {
    try { await navigator.clipboard.writeText(texts[i]); setDone(i); setTimeout(() => setDone(null), 1500); } catch { /* clipboard blocked */ }
  };
  return (
    <div className="mt-3 space-y-2.5">
      {messages.slice(0, all ? messages.length : 4).map((m, i) => (
        <div key={i} className="border border-rule bg-field/50 p-3">
          <p className="mb-1.5 text-[12.5px] text-slate/60">
            <span className="text-slate">{m.to}</span>
            {m.phone ? <span className="num ml-2">+{m.phone}</span> : <span className="ml-2 text-slate/45">{L.noNumber}</span>}
          </p>
          <textarea
            value={texts[i]}
            onChange={(e) => setTexts((t) => t.map((x, j) => (j === i ? e.target.value : x)))}
            rows={Math.min(8, Math.max(3, texts[i].split("\n").length + 1))}
            className="w-full resize-y border border-rule bg-paper px-2.5 py-2 text-[13px] leading-snug"
          />
          <div className="mt-1.5 flex gap-4 text-[12.5px]">
            <a href={link(m, i)} target="_blank" rel="noopener noreferrer" className="font-medium text-ink hover:underline underline-offset-2">{L.send}</a>
            <button onClick={() => copy(i)} className="text-slate/60 hover:text-ink">{done === i ? L.copied : L.copy}</button>
          </div>
        </div>
      ))}
      {!all && messages.length > 4 && (
        <button onClick={() => setAll(true)} className="text-[12.5px] text-ink hover:underline underline-offset-2">{L.showAll} ({messages.length})</button>
      )}
    </div>
  );
}

/** Did every number in an AI answer come out of the data? Green if yes, a warning naming the ones that did not. */
function Verified({ block, text }) {
  const good = block.status === "all";
  return (
    <p className={`mt-2 border-l-2 px-2.5 py-1 text-[12.5px] ${good ? "border-ink/50 text-slate/70" : "border-clay text-clay"}`} role="status">
      <span aria-hidden="true">{good ? "✓ " : "! "}</span>{text}
    </p>
  );
}

export function Blocks({ blocks, workLabel = "How I worked this out", downloadLabel = "Download as CSV", msgLabels, verifyText }) {
  if (!blocks?.length) return null;
  return blocks.map((b, i) => {
    if (b.type === "table") return <TableBlock key={i} block={b} downloadLabel={downloadLabel} />;
    if (b.type === "verified") return <Verified key={i} block={b} text={verifyText ? verifyText(b) : `${b.matched} of ${b.checked} figures traced to your data`} />;
    if (b.type === "messages") return <Messages key={i} messages={b.messages} labels={msgLabels} />;
    if (b.type === "playbook") return <Playbook key={i} items={b.items} />;
    if (b.type === "work") return <Work key={i} steps={b.steps} label={workLabel} />;
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
