import { useEffect, useState } from "react";
import { whatIf, fairnessOptions, runFairness, getMonitoring, reportUrl, detail } from "../api";
import { Button, Field, Select, Readout, Tag } from "./ui";

/* The trust layer's interface: why an answer came out the way it did, whether
   the input is something the model knows about, what changes it, and whether
   it treats groups evenly. Each piece takes `plain` — in Simple Mode the same
   facts are worded for a shop owner; in Technical Mode they carry the numbers. */

const pretty = (s) => String(s).replace(/[_\s]+/g, " ").trim();
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const pts = (x) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(0)}`;

const num = (v) =>
  typeof v === "number"
    ? Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : Number(v.toFixed(2)).toLocaleString()
    : String(v);

/* ---------------------------------------------------------------- trust */

const LEVEL = {
  high:   { word: "Familiar input",   tone: "lime" },
  medium: { word: "A few caveats",    tone: "line" },
  low:    { word: "Outside the data", tone: "signal" },
};

export function TrustNote({ trust, plain }) {
  if (!trust) return null;
  const L = LEVEL[trust.level] ?? LEVEL.medium;
  return (
    <div className="mt-4">
      <Tag tone={L.tone}>{L.word}</Tag>
      <p className="mt-2 text-[13.5px] text-mute">{trust.summary}</p>
      {trust.reasons?.length > 0 && (
        <ul className="mt-1.5 space-y-1 text-[13px] text-mute">
          {trust.reasons.map((r, i) => (
            <li key={i} className="pl-3 -indent-3">– {r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* Track record: a range for a number, or how often the model was right when it felt this sure.
   Both come from rows the model never trained on, so they are a fair test, not a boast. */
export function Track({ range, reliability }) {
  if (!range && !reliability) return null;
  const n = (v) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  return (
    <div className="mt-3 border-l-2 border-cobalt pl-3 text-[13.5px] text-mute">
      {range && (
        <p>
          Likely between <span className="num text-ink">{n(range.low)}</span> and <span className="num text-ink">{n(range.high)}</span>.
          {" "}This {range.level}% range held for {Math.round(range.held_out_coverage * 100)}% of {range.n_test} cases the model had never seen.
        </p>
      )}
      {reliability && (
        <p>
          When the model was about this sure, it was right {Math.round(reliability.accuracy * 100)}% of the time
          ({reliability.n} past cases it had never seen).
        </p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------- explanation */

/* Diverging bars around a centre line: cobalt pushes the answer up, red pushes
   it down. Sign is carried by side and colour, not by a legend you must read. */
export function Contributions({ explanation, plain, limit = 6 }) {
  if (!explanation) return null;
  const rows = explanation.contributions.slice(0, limit);
  const max = Math.max(...rows.map((r) => Math.abs(r.contribution)), 1e-9);
  const isProb = explanation.kind === "probability";
  const fmt = (c) => (isProb ? `${pts(c)} pts` : `${c >= 0 ? "+" : "−"}${num(Math.abs(c))}`);

  return (
    <div className="mt-3">
      {plain && explanation.narration && (
        <p className="mb-3 text-[14px] text-mute">{explanation.narration}</p>
      )}
      <div className="space-y-2">
        {rows.map((r) => {
          const w = (Math.abs(r.contribution) / max) * 50;
          const up = r.contribution >= 0;
          return (
            <div key={r.feature} className="grid grid-cols-[minmax(0,9rem)_1fr_4.5rem] items-center gap-3">
              <span className="truncate text-[12.5px]" title={r.feature}>
                {cap(pretty(r.feature))}
                <span className="num text-mute"> {r.value == null ? "blank" : num(r.value)}</span>
              </span>
              <div className="relative h-2.5 rounded-full bg-bone">
                <div className="absolute inset-y-0 left-1/2 w-px bg-ink/30" />
                <div
                  className={`absolute inset-y-0 rounded-full ${up ? "bg-cobalt" : "bg-signal"}`}
                  style={up ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }}
                />
              </div>
              <span className={`num text-right text-[12px] ${up ? "text-cobalt" : "text-signal"}`}>{fmt(r.contribution)}</span>
            </div>
          );
        })}
      </div>
      {!plain && (
        <p className="num mt-3 text-[11.5px] text-mute">
          base {isProb ? `${(explanation.base * 100).toFixed(1)}%` : num(explanation.base)} → output{" "}
          {isProb ? `${(explanation.output * 100).toFixed(1)}%` : num(explanation.output)} · Monte-Carlo Shapley, 40 orderings
        </p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- what-if */

function SweepChart({ data }) {
  const isProb = data.output_kind === "probability";
  const pts_ = data.points;
  const ys = pts_.map((p) => p.output);
  const lo = isProb ? 0 : Math.min(...ys);
  const hi = isProb ? 1 : Math.max(...ys);
  const span = hi - lo || 1;
  const W = 520, H = 150, L = 38, R = 10, T = 10, B = 24;
  const fmtY = (y) => (isProb ? `${Math.round(y * 100)}%` : num(y));

  if (data.kind === "categorical") {
    const sorted = [...pts_].sort((a, b) => b.output - a.output);
    return (
      <div className="space-y-2">
        {sorted.map((p) => {
          const cur = String(p.value) === String(data.current_value);
          return (
            <div key={p.value} className="grid grid-cols-[7rem_1fr_3.5rem] items-center gap-3">
              <span className={`truncate text-[12.5px] ${cur ? "font-medium" : ""}`}>
                {p.value}{cur && <span className="text-mute"> (now)</span>}
              </span>
              <div className="h-2 overflow-hidden rounded-full bg-bone">
                <div className={`h-2 rounded-full ${cur ? "bg-ink" : "bg-cobalt"}`} style={{ width: `${((p.output - lo) / span) * 100}%` }} />
              </div>
              <span className="num text-right text-[12px] text-mute">{fmtY(p.output)}</span>
            </div>
          );
        })}
      </div>
    );
  }

  const xs = pts_.map((p) => Number(p.value));
  const xmin = Math.min(...xs), xmax = Math.max(...xs);
  const X = (x) => L + ((x - xmin) / (xmax - xmin || 1)) * (W - L - R);
  const Y = (y) => T + (1 - (y - lo) / span) * (H - T - B);
  const path = pts_.map((p, i) => `${i ? "L" : "M"}${X(Number(p.value)).toFixed(1)},${Y(p.output).toFixed(1)}`).join(" ");
  const cx = data.current_value == null ? null : X(Number(data.current_value));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
         aria-label={`How the answer changes with ${pretty(data.feature)}`}>
      {[0, 0.5, 1].map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={T + t * (H - T - B)} y2={T + t * (H - T - B)} strokeDasharray={t === 1 ? undefined : "3 4"} style={{ stroke: "rgb(var(--line))" }} />
          <text x={L - 6} y={T + t * (H - T - B) + 4} textAnchor="end" className="num" fontSize="10" style={{ fill: "rgb(var(--mute))" }}>
            {fmtY(hi - t * span)}
          </text>
        </g>
      ))}
      <path d={path} fill="none" strokeWidth="2" strokeLinejoin="round" style={{ stroke: "rgb(var(--ink))" }} />
      {cx != null && (
        <g>
          <line x1={cx} x2={cx} y1={T} y2={H - B} strokeDasharray="3 3" style={{ stroke: "rgb(var(--mute))" }} />
          <circle cx={cx} cy={Y(data.current_output)} r="5" style={{ fill: "rgb(var(--cobalt))", stroke: "rgb(var(--sheet))", strokeWidth: 2 }} />
        </g>
      )}
      <text x={L} y={H - 6} className="num" fontSize="10" style={{ fill: "rgb(var(--mute))" }}>{num(xmin)}</text>
      <text x={W - R} y={H - 6} textAnchor="end" className="num" fontSize="10" style={{ fill: "rgb(var(--mute))" }}>{num(xmax)}</text>
    </svg>
  );
}

export function WhatIf({ modelId, row, features, plain }) {
  const [feature, setFeature] = useState(features[0]);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let live = true;
    setErr("");
    whatIf(modelId, row, feature)
      .then((d) => live && setData(d))
      .catch((e) => live && setErr(detail(e, "Couldn't run that what-if.")));
    return () => { live = false; };
  }, [modelId, feature, JSON.stringify(row)]);

  const isProb = data?.output_kind === "probability";
  const fmt = (y) => (isProb ? `${Math.round(y * 100)}%` : num(y));
  const gain = data ? data.best.output - data.current_output : 0;

  return (
    <div className="mt-3">
      <Field label={plain ? "Change this and see what happens" : "Vary feature"}>
        <Select value={feature} onChange={(e) => setFeature(e.target.value)}>
          {features.map((f) => <option key={f} value={f}>{cap(pretty(f))}</option>)}
        </Select>
      </Field>
      {err && <p className="mt-2 text-[12.5px] text-signal">{err}</p>}
      {data && (
        <div className="mt-3">
          <SweepChart data={data} />
          <p className="mt-2 text-[13.5px] text-mute">
            {Math.abs(gain) < (isProb ? 0.01 : 1e-9)
              ? `Changing ${pretty(feature)} barely moves the answer.`
              : `The best result (${fmt(data.best.output)}) comes at ${pretty(feature)} = ${num(data.best.value)}, ` +
                `${gain > 0 ? "up" : "down"} ${isProb ? `${Math.abs(gain * 100).toFixed(0)} points` : num(Math.abs(gain))} from now.`}
            {isProb && data.target_class != null && (
              <span className="text-mute/70"> Showing the chance of “{data.target_class}”.</span>
            )}
          </p>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------- fairness */

export function FairnessPanel({ modelId, plain }) {
  const [options, setOptions] = useState(null);
  const [group, setGroup] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    setResult(null);
    fairnessOptions(modelId)
      .then((o) => { setOptions(o); setGroup(o[0]?.column ?? ""); })
      .catch((e) => setErr(detail(e, "Couldn't load columns.")));
  }, [modelId]);

  const run = () => {
    setBusy(true); setErr("");
    runFairness(modelId, group).then(setResult).catch((e) => setErr(detail(e, "The audit failed."))).finally(() => setBusy(false));
  };

  const status = {
    pass: ["No large gaps", "lime"],
    review: ["Worth a closer look", "signal"],
    insufficient_data: ["Not enough data", "line"],
  };

  const isCls = result?.task === "classification";
  return (
    <div>
      <div className="grid items-end gap-4 sm:grid-cols-[2fr_auto]">
        <Field label={plain ? "Compare how it treats different…" : "Group column"}>
          <Select value={group} onChange={(e) => { setGroup(e.target.value); setResult(null); }}>
            {options?.map((o) => (
              <option key={o.column} value={o.column}>
                {cap(pretty(o.column))}{o.sensitive ? " · often sensitive" : ""}{o.banded ? " (in bands)" : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Button onClick={run} disabled={!group || busy}>{busy ? "Checking…" : plain ? "Check fairness" : "Run audit"}</Button>
      </div>
      {err && <p className="mt-3 text-[13px] text-signal">{err}</p>}

      {result && (
        <div className="mt-5">
          <Tag tone={status[result.status][1]}>{status[result.status][0]}</Tag>
          <ul className="mt-3 space-y-1.5 text-[14px] text-mute">
            {result.findings.map((f, i) => <li key={i}>{f}</li>)}
          </ul>

          <div className="sheet mt-4 overflow-x-auto">
            <table className="w-full text-left text-[12.5px]">
              <thead className="bg-bone/70">
                <tr>
                  <th className="eyebrow px-3 py-2 font-normal">{cap(pretty(result.group_column))}</th>
                  <th className="eyebrow px-3 py-2 text-right font-normal">People</th>
                  {isCls && result.positive_class != null && <th className="eyebrow px-3 py-2 font-normal">Got “{result.positive_class}”</th>}
                  {isCls ? <th className="eyebrow px-3 py-2 font-normal">Model right</th> : (
                    <><th className="eyebrow px-3 py-2 text-right font-normal">Avg predicted</th><th className="eyebrow px-3 py-2 text-right font-normal">Typical error</th></>
                  )}
                </tr>
              </thead>
              <tbody>
                {result.groups.map((g) => (
                  <tr key={g.group} className={`border-t border-line ${g.reliable ? "" : "text-ink/40"}`}>
                    <td className="px-3 py-2">{g.group}</td>
                    <td className="num px-3 py-2 text-right">{g.n}</td>
                    {isCls && result.positive_class != null && (
                      <td className="px-3 py-2"><Rate v={g.selection_rate} /></td>
                    )}
                    {isCls ? <td className="px-3 py-2"><Rate v={g.accuracy} /></td> : (
                      <><td className="num px-3 py-2 text-right">{num(g.mean_predicted)}</td><td className="num px-3 py-2 text-right">{num(g.mae)}</td></>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!plain && result.disparity_ratio != null && (
            <p className="num mt-2 text-[11.5px] text-mute">
              {isCls ? "min/max selection-rate ratio" : "min/max MAE ratio"} {result.disparity_ratio.toFixed(2)} · four-fifths guideline 0.80 · {result.n_test} held-out rows
            </p>
          )}
          <a
            href={reportUrl(modelId, plain ? "simple" : "technical", result.group_column)}
            target="_blank" rel="noreferrer"
            className="btn btn-outline mt-4 px-3 py-1.5 text-[12.5px]"
          >
            Put this in a report
          </a>
        </div>
      )}
    </div>
  );
}

function Rate({ v }) {
  if (v == null) return <span className="text-ink/30">–</span>;
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-16 overflow-hidden rounded-full bg-bone"><span className="block h-2 rounded-full bg-cobalt" style={{ width: `${v * 100}%` }} /></span>
      <span className="num text-[12px]">{Math.round(v * 100)}%</span>
    </span>
  );
}

/* ------------------------------------------------------------ monitoring */

export function MonitorPanel({ modelId, refreshKey }) {
  const [m, setM] = useState(null);
  useEffect(() => { getMonitoring(modelId).then(setM).catch(() => {}); }, [modelId, refreshKey]);
  if (!m) return null;
  const tone = { healthy: "good", watch: "plain", drifting: "warn", idle: "plain" }[m.status];
  return (
    <div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Readout value={m.total} label="predictions served" />
        <Readout value={m.avg_confidence == null ? "–" : `${(m.avg_confidence * 100).toFixed(0)}%`} label="average confidence" />
        <Readout value={m.trust_counts.low} label="used unfamiliar inputs" tone={m.trust_counts.low ? "warn" : "plain"} />
        <Readout value={m.status} label="input health" tone={tone} />
      </div>
      <p className="mt-4 text-[13.5px] text-mute">{m.note}</p>
      {m.recent.length > 0 && (
        <div className="sheet mt-4 overflow-x-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead className="bg-bone/70">
              <tr>
                <th className="eyebrow px-3 py-2 font-normal">#</th>
                <th className="eyebrow px-3 py-2 font-normal">Input</th>
                <th className="eyebrow px-3 py-2 font-normal">Output</th>
                <th className="eyebrow px-3 py-2 font-normal">Trust</th>
              </tr>
            </thead>
            <tbody>
              {m.recent.map((p) => (
                <tr key={p.id} className="border-t border-line">
                  <td className="num px-3 py-2">{p.id}</td>
                  <td className="num max-w-[22rem] truncate px-3 py-2" title={JSON.stringify(p.input)}>{Object.values(p.input).join(", ")}</td>
                  <td className="num px-3 py-2">{String(p.output.prediction)}</td>
                  <td className={`px-3 py-2 ${p.trust_level === "low" ? "text-signal" : ""}`}>{p.trust_level ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- report */

export function ReportLinks({ modelId }) {
  const link = "btn btn-outline px-3 py-1.5 text-[12.5px]";
  return (
    <div className="flex flex-wrap gap-2">
      <a className={link} href={reportUrl(modelId, "simple")} target="_blank" rel="noreferrer">Plain-language report</a>
      <a className={link} href={reportUrl(modelId, "technical")} target="_blank" rel="noreferrer">Technical report with model card</a>
    </div>
  );
}
