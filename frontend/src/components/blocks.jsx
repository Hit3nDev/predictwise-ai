import { useEffect, useState } from "react";
import { rankRows, getLevers, scoreFile, downloadScored, detail } from "../api";
import { Button, Readout, Tag } from "./ui";
import { Icon } from "./icons";

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
  const area = n > 1 ? `${actual} L${X(n - 1).toFixed(1)},${(H - B).toFixed(1)} L${X(0).toFixed(1)},${(H - B).toFixed(1)} Z` : "";
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
            <line x1={L} x2={W - R} y1={y} y2={y} strokeDasharray={t === 1 ? undefined : "3 4"} style={{ stroke: "rgb(var(--line))" }} />
            <text x={L - 6} y={y + 4} textAnchor="end" fontSize="10" className="num" style={{ fill: "rgb(var(--mute))" }}>
              {formatValue(hi - t * span, unit)}
            </text>
          </g>
        );
      })}
      <defs>
        <linearGradient id="pw-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" style={{ stopColor: "rgb(var(--lime))", stopOpacity: 0.6 }} />
          <stop offset="100%" style={{ stopColor: "rgb(var(--lime))", stopOpacity: 0 }} />
        </linearGradient>
      </defs>
      {area && <path d={area} fill="url(#pw-area)" />}
      {band && <path d={band} style={{ fill: "rgb(var(--cobalt) / .10)" }} />}
      <path d={actual} fill="none" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" style={{ stroke: "rgb(var(--ink))" }} />
      {fPath && <path d={fPath} fill="none" strokeWidth="2" strokeDasharray="5 4" strokeLinecap="round" style={{ stroke: "rgb(var(--cobalt))" }} />}
      {points.map((p, i) => (
        <circle key={i} cx={X(i)} cy={Y(p.value)} r="2.5" style={{ fill: "rgb(var(--ink))" }}>
          <title>{`${p.label}: ${formatValue(p.value, unit)}`}</title>
        </circle>
      ))}
      {forecast.map((p, i) => (
        <circle key={i} cx={X(n + i)} cy={Y(p.value)} r="3.5" style={{ fill: "rgb(var(--cobalt))", stroke: "rgb(var(--sheet))", strokeWidth: 1.5 }}>
          <title>{`${p.label} (forecast): ${formatValue(p.value, unit)} · likely ${formatValue(p.low, unit)} to ${formatValue(p.high, unit)}`}</title>
        </circle>
      ))}
      {[...new Set(labelIdx)].map((i) => (
        <text key={i} x={X(i)} y={H - 7} fontSize="10" textAnchor={i === 0 ? "start" : i === all.length - 1 ? "end" : "middle"}
              className="num" style={{ fill: "rgb(var(--mute))" }}>
          {all[i].label}
        </text>
      ))}
    </svg>
  );
}

function BarChart({ points, unit }) {
  const max = Math.max(...points.map((p) => Math.abs(p.value)), 1);
  return (
    <div className="space-y-2">
      {points.map((p, i) => (
        <div key={p.label} className="grid grid-cols-[minmax(0,9rem)_1fr_4.5rem] items-center gap-3">
          <span className="truncate text-[12.5px]" title={p.label}>{p.label}</span>
          <div className="h-2 overflow-hidden rounded-full bg-bone">
            <div className={`bar-grow h-2 rounded-full ${i === 0 ? "bg-cobalt" : "bg-ink/80"}`} style={{ width: `${(Math.abs(p.value) / max) * 100}%`, animationDelay: `${i * 40}ms` }} />
          </div>
          <span className="num text-right text-[12px] text-mute">{formatValue(p.value, unit)}</span>
        </div>
      ))}
    </div>
  );
}

function Chart({ block }) {
  return (
    <figure className="sheet mt-4 p-4 sm:p-5">
      <figcaption className="eyebrow mb-3">{block.title}</figcaption>
      {block.chart === "line"
        ? <LineChart points={block.points} forecast={block.forecast} unit={block.unit} />
        : <BarChart points={block.points} unit={block.unit} />}
      {block.forecast?.length > 0 && (
        <p className="mt-2 text-[12px] text-mute">
          <span className="text-cobalt">Dashed</span> is the forecast; the shaded band is the range it will probably land in.
        </p>
      )}
    </figure>
  );
}

/* ---------------------------------------------------------------- others */

function Stats({ stats }) {
  return (
    <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
      {stats.map((s) => <Readout key={s.label} value={s.value} label={s.label} />)}
    </div>
  );
}

function Segments({ segments }) {
  return (
    <div className="mt-4 space-y-2.5">
      {segments.map((s) => (
        <div key={s.name} className="sheet p-4">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[14.5px] font-semibold">{s.name}</span>
            <span className="num text-[12px] text-mute">{s.size} · {Math.round(s.share * 100)}%</span>
          </div>
          <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-bone"><div className="bar-grow h-1.5 rounded-full bg-ink" style={{ width: `${s.share * 100}%` }} /></div>
          <p className="num mt-2.5 text-[12px] text-mute">
            {s.averages.map((a) => `${pretty(a.column)} ${a.display}`).join(" · ")}
          </p>
          {s.outcome && (
            <p className="mt-1 text-[13px]">
              <span className="num text-cobalt">{Math.round(s.outcome.rate * 100)}%</span> {pretty(s.outcome.column)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function Anomalies({ rows }) {
  return (
    <div className="mt-4 space-y-2.5">
      {rows.map((r) => (
        <div key={r.row_number} className="sheet p-4">
          <p className="text-[13.5px]"><span className="num text-mute">row {r.row_number}</span> · {r.reasons[0]}</p>
          <p className="num mt-1.5 truncate text-[11.5px] text-mute">
            {Object.entries(r.values).map(([k, v]) => `${k}: ${v ?? "–"}`).join("  ")}
          </p>
        </div>
      ))}
    </div>
  );
}

const TONE = { do: "bg-cobalt", watch: "bg-signal", good: "bg-lime" };

/* A to-do list, most useful first. The coloured edge says what kind of item
   it is: cobalt to act on, red to look at, lime for good news. */
function Playbook({ items }) {
  return (
    <ol className="mt-4 space-y-2.5">
      {items.map((it, i) => (
        <li key={i} className="sheet flex overflow-hidden">
          <span className={`w-1 shrink-0 ${TONE[it.tone] ?? "bg-line"}`} />
          <div className="flex gap-4 px-4 py-3">
            <span className="num pt-1 text-[11px] text-mute">{String(i + 1).padStart(2, "0")}</span>
            <div>
              <p className="text-[14.5px] font-semibold">{it.title}</p>
              <p className="mt-0.5 text-[13.5px] text-mute">{it.detail}</p>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

/* The exact calculations behind an AI answer: the check a chat assistant
   that recalls numbers from memory cannot offer. */
function Work({ steps, label }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4 border-t border-line pt-3">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="group inline-flex items-center gap-2 text-[13.5px] font-medium hover:text-cobalt">
        <span className={`flex h-5 w-5 items-center justify-center rounded-full border border-ink/25 transition group-hover:border-cobalt ${open ? "rotate-90" : ""}`}>
          <Icon name="chevron" size={11} strokeWidth={2.2} />
        </span>
        {label}
      </button>
      {open && (
        <div className="mt-3 animate-rise space-y-2">
          {steps.map((s, i) => (
            <div key={i} className="sheet px-3.5 py-2.5">
              <p className="num break-all text-[12px]">{s.expr}</p>
              <p className="num mt-1 break-all text-[12px] text-cobalt">= {s.result}</p>
            </div>
          ))}
          <p className="eyebrow">Calculated from your file by code, not remembered or guessed.</p>
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
    const url = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = csv || "table.csv"; a.click();
    URL.revokeObjectURL(url);
  };
  const TREND = { rising: "text-cobalt", falling: "text-signal" };
  return (
    <div className="mt-4">
      {caption && <p className="eyebrow mb-2">{caption}</p>}
      <div className="sheet overflow-x-auto">
        <table className="w-full text-left text-[12.5px]">
          <thead className="bg-bone/70">
            <tr>{columns.map((c) => <th key={c} className="eyebrow whitespace-nowrap px-3 py-2 font-normal">{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-line align-top hover:bg-bone/50">
                {columns.map((c) => (
                  <td key={c} className={`px-3 py-2 ${typeof r[c] === "string" && r[c].length > 40 ? "min-w-[14rem]" : ""} ${typeof r[c] === "number" ? "num text-right" : ""} ${c === "Trend" ? TREND[r[c]] ?? "text-mute" : ""}`}>
                    {typeof r[c] === "number" ? r[c].toLocaleString("en-IN") : r[c]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {csv && (
        <button onClick={save} className="eyebrow mt-2 inline-flex items-center gap-1.5 hover:text-ink">
          <Icon name="download" size={12} /> {downloadLabel}
        </button>
      )}
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
    <div className="mt-4 space-y-3">
      {messages.slice(0, all ? messages.length : 4).map((m, i) => (
        <div key={i} className="sheet p-3.5">
          <p className="mb-2 flex items-baseline gap-2 text-[13px]">
            <span className="font-semibold">{m.to}</span>
            {m.phone ? <span className="num text-[12px] text-mute">+{m.phone}</span> : <span className="text-[12px] text-mute">{L.noNumber}</span>}
          </p>
          <textarea
            value={texts[i]}
            onChange={(e) => setTexts((t) => t.map((x, j) => (j === i ? e.target.value : x)))}
            rows={Math.min(8, Math.max(3, texts[i].split("\n").length + 1))}
            className="field-input resize-y bg-bone/60 text-[13.5px] leading-snug"
          />
          <div className="mt-2 flex items-center gap-2">
            <a href={link(m, i)} target="_blank" rel="noopener noreferrer" className="btn btn-solid px-3 py-1.5 text-[12.5px]"><Icon name="share" size={13} /> {L.send}</a>
            <button onClick={() => copy(i)} className="btn btn-ghost px-3 py-1.5 text-[12.5px]"><Icon name="copy" size={13} /> {done === i ? L.copied : L.copy}</button>
          </div>
        </div>
      ))}
      {!all && messages.length > 4 && (
        <button onClick={() => setAll(true)} className="eyebrow hover:text-ink">{L.showAll} ({messages.length})</button>
      )}
    </div>
  );
}

/** Did every number in an AI answer come out of the data? Lime if yes, a warning naming the ones that did not. */
function Verified({ block, text }) {
  const good = block.status === "all";
  return (
    <p
      className={`mt-3 inline-flex items-start gap-2 rounded-[8px] border px-3 py-1.5 text-[12.5px] ${good ? "border-ink/15 bg-lime/40 text-ink" : "border-signal/35 bg-signal/[0.06] text-signal"}`}
      role="status"
    >
      <Icon name={good ? "check" : "info"} size={14} className="mt-0.5 shrink-0" strokeWidth={2.2} />
      <span>{text}</span>
    </p>
  );
}

const STATUS_TONE = {
  "Gone quiet": "signal", "Stopped selling": "signal", Falling: "signal",
  New: "cobalt", Rising: "lime", Best: "lime",
};

function MiniList({ title, items }) {
  return (
    <div>
      <p className="eyebrow mb-1.5">{title}</p>
      <ul className="divide-y divide-line">
        {items.map(([name, value]) => (
          <li key={name} className="flex items-baseline justify-between gap-3 py-1.5 text-[13px]">
            <span className="truncate">{name}</span>
            <span className="num shrink-0 text-mute">{value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One customer or product at a glance: facts, a year of months, companions, and the message to send. */
export function CardBlock({ block: b }) {
  const lists = [
    b.favourites?.length && ["Buys mostly", b.favourites.map((x) => [x.name, x.value])],
    b.bought_with?.length && ["Bought together with", b.bought_with.map((x) => [x.name, x.share])],
    b.top_customers?.length && ["Biggest buyers", b.top_customers.map((x) => [x.name, x.value])],
  ].filter(Boolean);
  return (
    <div className="sheet mt-4 overflow-hidden">
      <div className="flex items-start justify-between gap-4 px-5 py-4">
        <div className="min-w-0">
          <p className="eyebrow">{b.kind === "customer" ? "Customer" : "Product"}</p>
          <p className="display mt-1 truncate text-[26px] leading-tight" style={{ fontVariationSettings: '"SOFT" 30, "WONK" 0' }}>{b.name}</p>
        </div>
        {b.status && <Tag tone={STATUS_TONE[b.status] ?? "line"}>{b.status}</Tag>}
      </div>
      <div className="grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-3 lg:grid-cols-4">
        {b.facts.map((f) => (
          <div key={f.label} className="bg-sheet px-4 py-3">
            <p className="num text-[17px] font-medium leading-none">{f.value}</p>
            <p className="eyebrow mt-1.5">{f.label}</p>
          </div>
        ))}
      </div>
      {b.chart?.points?.length > 1 && (
        <div className="border-t border-line px-5 py-4">
          <p className="eyebrow mb-2">{b.chart.title}</p>
          <LineChart points={b.chart.points} unit={b.chart.unit} />
        </div>
      )}
      {lists.length > 0 && (
        <div className="grid gap-4 border-t border-line px-5 py-4 sm:grid-cols-2">
          {lists.map(([title, items]) => <MiniList key={title} title={title} items={items} />)}
        </div>
      )}
      {b.message && (
        <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-3">
          <a href={b.message.link} target="_blank" rel="noopener noreferrer" className="btn btn-solid px-3 py-1.5 text-[12.5px]">
            <Icon name="share" size={13} /> {b.message.action}
          </a>
          {b.phone ? <span className="num text-[12px] text-mute">+{b.phone}</span> : <span className="text-[12px] text-mute">No number on file</span>}
        </div>
      )}
    </div>
  );
}

export function Blocks({ blocks, workLabel = "How I worked this out", downloadLabel = "Download as CSV", msgLabels, verifyText }) {
  if (!blocks?.length) return null;
  return blocks.map((b, i) => {
    if (b.type === "card") return <CardBlock key={i} block={b} />;
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

export { Chart, Stats, Segments, Anomalies, LineChart, BarChart };

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
      <p className="mb-3 text-[13px] text-mute">
        {plain ? "Upload a sheet of new people or cases with the same columns. You get the answer for every row, with a note on which to double-check."
               : "CSV/Excel with the model's input columns. Adds predicted value, chance, confidence and trust per row (max 5,000 rows)."}
      </p>
      <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => { setFile(e.target.files[0]); setRes(null); }}
             className="block w-full text-[13px] text-mute file:mr-3 file:cursor-pointer file:rounded-[6px] file:border file:border-ink/25 file:bg-sheet file:px-3 file:py-1.5 file:text-[12.5px] file:font-medium file:text-ink hover:file:border-ink" />
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={run} disabled={!file || busy}>{busy ? "Scoring…" : "Score file"}</Button>
        {res && <Button variant="outline" onClick={() => downloadScored(modelId, file)}><Icon name="download" size={14} /> Download with answers</Button>}
      </div>
      {err && <p className="mt-2 text-[13px] text-signal">{err}</p>}
      {res && (
        <div className="mt-4">
          <p className="text-[13.5px] text-mute">
            {res.summary.rows} rows scored.
            {res.summary.by_prediction && " " + Object.entries(res.summary.by_prediction).map(([k, v]) => `${v} × ${k}`).join(", ") + "."}
            {res.summary.average_prediction != null && ` Average prediction ${formatValue(res.summary.average_prediction)}.`}
            {res.summary.low_trust > 0 && ` ${res.summary.low_trust} used unfamiliar values, so double-check those.`}
          </p>
          <div className="sheet mt-3 max-h-64 overflow-auto">
            <table className="w-full text-left text-[12px]">
              <thead className="sticky top-0 bg-bone"><tr>{cols.map((c) => <th key={c} className="eyebrow whitespace-nowrap px-3 py-2 font-normal">{c}</th>)}</tr></thead>
              <tbody>
                {res.preview.map((r, i) => (
                  <tr key={i} className="border-t border-line">
                    {cols.map((c) => <td key={c} className={`num whitespace-nowrap px-3 py-1.5 ${c === "trust" && r[c] === "low" ? "text-signal" : ""}`}>{String(r[c] ?? "–")}</td>)}
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
      {err && <p className="text-[13px] text-signal">{err}</p>}
      {list && list.length === 0 && <p className="text-[13.5px] text-mute">Nothing you can change would improve this much. It already looks strong.</p>}
      {list && list.length > 0 && (
        <ul className="sheet divide-y divide-line">
          {list.map((l) => (
            <li key={l.feature} className="px-4 py-2.5 text-[13.5px]">
              <span className="font-semibold">{cap(pretty(l.feature))}</span>
              {l.current != null && <> from <span className="num">{String(l.current)}</span></>} to <span className="num">{String(l.best_value)}</span>
              <span className="num text-cobalt"> · {fmt(l.current_output)} → {fmt(l.best_output)}</span>
              {!l.changeable && <span className="text-mute"> · hard to change</span>}
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
      {err && <p className="mt-2 text-[13px] text-signal">{err}</p>}
      {data && (
        <>
          <p className="mt-3 text-[13.5px] text-mute">{data.headline}</p>
          <div className="sheet mt-2 overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead className="bg-bone/70"><tr>{cols.map((c) => <th key={c} className="eyebrow whitespace-nowrap px-3 py-2 font-normal">{c}</th>)}</tr></thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i} className="border-t border-line">
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
