import { useEffect, useState } from "react";
import { whatIf, fairnessOptions, runFairness, getMonitoring, reportUrl, detail } from "../api";
import { Panel, Button, Field, Select, Readout, Notice } from "./ui";

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
  high:   { word: "Familiar input",   tone: "text-ink border-ink/40" },
  medium: { word: "A few caveats",    tone: "text-slate/70 border-slate/30" },
  low:    { word: "Outside the data", tone: "text-clay border-clay/50" },
};

export function TrustNote({ trust, plain }) {
  if (!trust) return null;
  const L = LEVEL[trust.level] ?? LEVEL.medium;
  return (
    <div className="mt-3">
      <span className={`inline-block border px-2 py-0.5 text-[12px] ${L.tone}`}>{L.word}</span>
      <p className="mt-1.5 text-[13px] text-slate/65">{trust.summary}</p>
      {trust.reasons?.length > 0 && (
        <ul className="mt-1.5 space-y-1 text-[12.5px] text-slate/60">
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
    <div className="mt-3 border-l-2 border-ink/30 pl-3 text-[13px] text-slate/70">
      {range && (
        <p>
          Likely between <span className="num text-slate">{n(range.low)}</span> and <span className="num text-slate">{n(range.high)}</span>.
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

/* Diverging bars around a centre line: ink pushes the answer up, clay pushes
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
        <p className="mb-3 text-[13.5px] text-slate/75">{explanation.narration}</p>
      )}
      <div className="space-y-1.5">
        {rows.map((r) => {
          const w = (Math.abs(r.contribution) / max) * 50;
          const up = r.contribution >= 0;
          return (
            <div key={r.feature} className="grid grid-cols-[minmax(0,9rem)_1fr_4.5rem] items-center gap-3">
              <span className="truncate text-[12.5px]" title={r.feature}>
                {cap(pretty(r.feature))}
                <span className="num text-slate/40"> {r.value == null ? "blank" : num(r.value)}</span>
              </span>
              <div className="relative h-3 bg-field">
                <div className="absolute inset-y-0 left-1/2 w-px bg-slate/30" />
                <div
                  className={`absolute inset-y-0 ${up ? "bg-ink/75" : "bg-clay/75"}`}
                  style={up ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }}
                />
              </div>
              <span className={`num text-right text-[12px] ${up ? "text-ink" : "text-clay"}`}>{fmt(r.contribution)}</span>
            </div>
          );
        })}
      </div>
      {!plain && (
        <p className="num mt-3 text-[11.5px] text-slate/45">
          base {isProb ? `${(explanation.base * 100).toFixed(1)}%` : num(explanation.base)} → output{" "}
          {isProb ? `${(explanation.output * 100).toFixed(1)}%` : num(explanation.output)} · Monte-Carlo Shapley, 40 orderings
        </p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- what-if */

function SweepChart({ data, plain }) {
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
      <div className="space-y-1.5">
        {sorted.map((p) => {
          const cur = String(p.value) === String(data.current_value);
          return (
            <div key={p.value} className="grid grid-cols-[7rem_1fr_3.5rem] items-center gap-3">
              <span className={`truncate text-[12.5px] ${cur ? "font-medium" : ""}`}>
                {p.value}{cur && <span className="text-slate/40"> (now)</span>}
              </span>
              <div className="h-3 bg-field">
                <div className={`h-3 ${cur ? "bg-slate/60" : "bg-ink/65"}`} style={{ width: `${((p.output - lo) / span) * 100}%` }} />
              </div>
              <span className="num text-right text-[12px] text-slate/60">{fmtY(p.output)}</span>
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
          <line x1={L} x2={W - R} y1={T + t * (H - T - B)} y2={T + t * (H - T - B)} style={{ stroke: "rgb(var(--rule))" }} />
          <text x={L - 6} y={T + t * (H - T - B) + 4} textAnchor="end" className="num" fontSize="10" style={{ fill: "rgb(var(--slate) / .5)" }}>
            {fmtY(hi - t * span)}
          </text>
        </g>
      ))}
      <path d={path} fill="none" strokeWidth="2" style={{ stroke: "rgb(var(--ink))" }} />
      {cx != null && (
        <g>
          <line x1={cx} x2={cx} y1={T} y2={H - B} strokeDasharray="3 3" style={{ stroke: "rgb(var(--slate) / .5)" }} />
          <circle cx={cx} cy={Y(data.current_output)} r="4.5" style={{ fill: "rgb(var(--clay))" }} />
        </g>
      )}
      <text x={L} y={H - 6} className="num" fontSize="10" style={{ fill: "rgb(var(--slate) / .5)" }}>{num(xmin)}</text>
      <text x={W - R} y={H - 6} textAnchor="end" className="num" fontSize="10" style={{ fill: "rgb(var(--slate) / .5)" }}>{num(xmax)}</text>
    </svg>
  );
}

export function WhatIf({ modelId, row, features, target, plain }) {
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
      {err && <p className="mt-2 text-[12.5px] text-clay">{err}</p>}
      {data && (
        <div className="mt-3">
          <SweepChart data={data} plain={plain} />
          <p className="mt-2 text-[13px] text-slate/70">
            {Math.abs(gain) < (isProb ? 0.01 : 1e-9)
              ? `Changing ${pretty(feature)} barely moves the answer.`
              : `The best result (${fmt(data.best.output)}) comes at ${pretty(feature)} = ${num(data.best.value)}, ` +
                `${gain > 0 ? "up" : "down"} ${isProb ? `${Math.abs(gain * 100).toFixed(0)} points` : num(Math.abs(gain))} from now.`}
            {isProb && data.target_class != null && (
              <span className="text-slate/45"> Showing the chance of “{data.target_class}”.</span>
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
    pass: ["No large gaps", "text-ink border-ink/40"],
    review: ["Worth a closer look", "text-clay border-clay/50"],
    insufficient_data: ["Not enough data", "text-slate/60 border-slate/30"],
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
      {err && <p className="mt-3 text-[13px] text-clay">{err}</p>}

      {result && (
        <div className="mt-5">
          <span className={`inline-block border px-2 py-0.5 text-[12px] ${status[result.status][1]}`}>{status[result.status][0]}</span>
          <ul className="mt-3 space-y-1.5 text-[13.5px] text-slate/75">
            {result.findings.map((f, i) => <li key={i}>{f}</li>)}
          </ul>

          <div className="mt-4 overflow-x-auto border border-rule">
            <table className="w-full text-left text-[12.5px]">
              <thead className="bg-field text-slate/55">
                <tr>
                  <th className="px-3 py-2 font-medium">{cap(pretty(result.group_column))}</th>
                  <th className="px-3 py-2 text-right font-medium">People</th>
                  {isCls && result.positive_class != null && <th className="px-3 py-2 font-medium">Got “{result.positive_class}”</th>}
                  {isCls ? <th className="px-3 py-2 font-medium">Model right</th> : (
                    <><th className="px-3 py-2 text-right font-medium">Avg predicted</th><th className="px-3 py-2 text-right font-medium">Typical error</th></>
                  )}
                </tr>
              </thead>
              <tbody>
                {result.groups.map((g) => (
                  <tr key={g.group} className={`border-t border-rule/60 ${g.reliable ? "" : "text-slate/40"}`}>
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
            <p className="num mt-2 text-[11.5px] text-slate/45">
              {isCls ? "min/max selection-rate ratio" : "min/max MAE ratio"} {result.disparity_ratio.toFixed(2)} · four-fifths guideline 0.80 · {result.n_test} held-out rows
            </p>
          )}
          <a
            href={reportUrl(modelId, plain ? "simple" : "technical", result.group_column)}
            target="_blank" rel="noreferrer"
            className="mt-4 inline-block text-[13px] text-ink underline underline-offset-2"
          >
            Put this in a report
          </a>
        </div>
      )}
    </div>
  );
}

function Rate({ v }) {
  if (v == null) return <span className="text-slate/30">–</span>;
  return (
    <span className="flex items-center gap-2">
      <span className="h-2 w-16 bg-field"><span className="block h-2 bg-ink/70" style={{ width: `${v * 100}%` }} /></span>
      <span className="num text-[12px]">{Math.round(v * 100)}%</span>
    </span>
  );
}

/* ------------------------------------------------------------ monitoring */

export function MonitorPanel({ modelId, refreshKey }) {
  const [m, setM] = useState(null);
  useEffect(() => { getMonitoring(modelId).then(setM).catch(() => {}); }, [modelId, refreshKey]);
  if (!m) return null;
  const tone = { healthy: "ink", watch: "plain", drifting: "clay", idle: "plain" }[m.status];
  return (
    <div>
      <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
        <Readout value={m.total} label="predictions served" />
        <Readout value={m.avg_confidence == null ? "–" : `${(m.avg_confidence * 100).toFixed(0)}%`} label="average confidence" />
        <Readout value={m.trust_counts.low} label="used unfamiliar inputs" tone={m.trust_counts.low ? "clay" : "plain"} />
        <Readout value={m.status} label="input health" tone={tone} />
      </div>
      <p className="mt-4 text-[13px] text-slate/65">{m.note}</p>
      {m.recent.length > 0 && (
        <div className="mt-4 overflow-x-auto border border-rule">
          <table className="w-full text-left text-[12px]">
            <thead className="bg-field text-slate/55">
              <tr><th className="px-3 py-1.5 font-medium">#</th><th className="px-3 py-1.5 font-medium">Input</th><th className="px-3 py-1.5 font-medium">Output</th><th className="px-3 py-1.5 font-medium">Trust</th></tr>
            </thead>
            <tbody>
              {m.recent.map((p) => (
                <tr key={p.id} className="border-t border-rule/60">
                  <td className="num px-3 py-1.5">{p.id}</td>
                  <td className="num max-w-[22rem] truncate px-3 py-1.5" title={JSON.stringify(p.input)}>{Object.values(p.input).join(", ")}</td>
                  <td className="num px-3 py-1.5">{String(p.output.prediction)}</td>
                  <td className={`px-3 py-1.5 ${p.trust_level === "low" ? "text-clay" : ""}`}>{p.trust_level ?? "–"}</td>
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
  const link = "text-[13px] text-ink underline underline-offset-2";
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1">
      <a className={link} href={reportUrl(modelId, "simple")} target="_blank" rel="noreferrer">Plain-language report</a>
      <a className={link} href={reportUrl(modelId, "technical")} target="_blank" rel="noreferrer">Technical report with model card</a>
    </div>
  );
}
