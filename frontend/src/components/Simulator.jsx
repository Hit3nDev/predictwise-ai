import { useEffect, useRef, useState } from "react";
import { simulateOptions, runSimulation, detail } from "../api";
import { formatValue, signedMoney, signedPct, shortDate } from "../format";
import { Readout, Select, Switch, Notice } from "./ui";
import { Icon, ThinkingMark } from "./icons";
import { t, fill } from "../i18n";

/* Rehearse a decision. The next 30 days are replayed 2,000 times from the shop's own last
   12 weeks, as things are and with the levers switched on. Every number comes from the backend;
   this screen only holds the levers and draws the ranges. */

const money = (v) => formatValue(v, "money");

/* ------------------------------------------------------------- fan chart */

export function FanChart({ fan, changed, lang = "en" }) {
  const base = fan.base, scen = fan.scenario;
  const n = base.p50.length;
  const W = 600, H = 220, L = 58, R = 14, T = 22, B = 26;
  const hi = Math.max(...base.p90, ...(changed ? scen.p90 : []), 1);
  const X = (i) => L + (i / (n - 1)) * (W - L - R);
  const Y = (v) => T + (1 - v / hi) * (H - T - B);
  const line = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const band = (lo, up) => `${line(up)} ${[...lo].reverse().map((v, i) => `L${X(n - 1 - i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ")} Z`;

  // consecutive festival days become one shaded span
  const spans = [];
  for (const f of fan.festival_days || []) {
    const last = spans[spans.length - 1];
    if (last && last.name === f.name && f.day === last.to + 1) last.to = f.day;
    else spans.push({ name: f.name, from: f.day, to: f.day });
  }
  const labelAt = [0, Math.floor((n - 1) / 2), n - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t(lang, "simFan")}>
      {[0, 0.5, 1].map((k) => {
        const y = T + k * (H - T - B);
        return (
          <g key={k}>
            <line x1={L} x2={W - R} y1={y} y2={y} strokeDasharray={k === 1 ? undefined : "3 4"} style={{ stroke: "rgb(var(--line))" }} />
            <text x={L - 6} y={y + 4} textAnchor="end" fontSize="10" className="num" style={{ fill: "rgb(var(--mute))" }}>{money(hi * (1 - k))}</text>
          </g>
        );
      })}
      {spans.map((s) => (
        <g key={`${s.name}${s.from}`}>
          <rect x={X(s.from)} y={T} width={Math.max(X(Math.min(s.to + 1, n - 1)) - X(s.from), 2)} height={H - T - B} style={{ fill: "rgb(var(--lime) / .16)" }} />
          <text x={X(s.from) + 4} y={T - 8} fontSize="9.5" letterSpacing="0.08em" style={{ fill: "rgb(var(--mute))", textTransform: "uppercase" }}>{s.name}</text>
        </g>
      ))}
      <path d={band(base.p10, base.p90)} style={{ fill: "rgb(var(--ink) / .09)" }} />
      <path d={line(base.p50)} fill="none" strokeWidth="2" strokeLinejoin="round" style={{ stroke: "rgb(var(--ink))" }} />
      {changed && <path d={band(scen.p10, scen.p90)} style={{ fill: "rgb(var(--cobalt) / .14)" }} />}
      {changed && <path d={line(scen.p50)} fill="none" strokeWidth="2.2" strokeDasharray="6 4" strokeLinejoin="round" style={{ stroke: "rgb(var(--cobalt))" }} />}
      {labelAt.map((i) => (
        <text key={i} x={X(i)} y={H - 7} fontSize="10" textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} className="num" style={{ fill: "rgb(var(--mute))" }}>
          {shortDate(fan.labels[Math.max(i - 1, 0)])}
        </text>
      ))}
    </svg>
  );
}

/* ------------------------------------------------------------- the result */

export function Outcome({ res, lang = "en", compact = false, onOpen }) {
  const b = res.baseline, s = res.scenario, d = res.delta;
  const changed = Object.keys(res.levers || {}).length > 0;
  const tone = (v) => (!changed ? "plain" : v >= 0 ? "good" : "warn");
  const metrics = [["simSales", "sales"], res.has_cost && ["simProfit", "profit"], res.has_credit && ["simCash", "cash"]].filter(Boolean);
  return (
    <div className={compact ? "mt-4" : ""}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Readout value={money(b.sales.p50)} label={`${t(lang, "simAsIs")} · ${fill(t(lang, "simLikely"), { a: money(b.sales.p10), b: money(b.sales.p90) })}`} />
        <Readout value={changed ? money(s.sales.p50) : "–"} label={t(lang, "simWith")} tone={tone(d.sales.p50)} />
        <Readout value={changed ? signedMoney(d.sales.p50) : "–"} label={`${t(lang, "simChange")}${changed ? ` · ${signedPct(d.sales.pct)}` : ""}`} tone={tone(d.sales.p50)} />
      </div>

      {metrics.length > 1 && (
        <div className="sheet mt-3 overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="eyebrow">
                <th className="px-4 py-2 text-left font-normal">{fill(t(lang, "simNext"), { n: res.horizon })}</th>
                <th className="px-4 py-2 text-right font-normal">{t(lang, "simAsIs")}</th>
                <th className="px-4 py-2 text-right font-normal">{t(lang, "simWith")}</th>
                <th className="px-4 py-2 text-right font-normal">{t(lang, "simChange")}</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map(([key, k]) => (
                <tr key={k} className="border-t border-line">
                  <td className="px-4 py-2">{t(lang, key)}</td>
                  <td className="num px-4 py-2 text-right">
                    {money(b[k].p50)}
                    <span className="block text-[10.5px] text-mute">{money(b[k].p10)} – {money(b[k].p90)}</span>
                  </td>
                  <td className="num px-4 py-2 text-right">{changed ? money(s[k].p50) : "–"}</td>
                  <td className={`num px-4 py-2 text-right font-medium ${changed ? (d[k].p50 >= 0 ? "text-cobalt" : "text-signal") : "text-mute"}`}>
                    {changed ? `${signedMoney(d[k].p50)} (${signedPct(d[k].pct)})` : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <figure className="sheet mt-4 p-4">
        <figcaption className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="eyebrow">{t(lang, "simFan")}</span>
          <span className="flex flex-wrap items-center gap-3 text-[11px] text-mute">
            <span className="inline-flex items-center gap-1.5"><span className="h-[3px] w-4 rounded bg-ink" /> {t(lang, "simLegendBase")}</span>
            {changed && <span className="inline-flex items-center gap-1.5"><span className="h-[3px] w-4 rounded bg-cobalt" /> {t(lang, "simLegendScen")}</span>}
            {res.festivals?.map((f) => (
              <span key={f.name} className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-lime/60" /> {f.name} · {shortDate(f.date)}</span>
            ))}
          </span>
        </figcaption>
        <FanChart fan={res.fan} changed={changed} lang={lang} />
      </figure>

      {res.effects?.length > 0 && (
        <div className="mt-4">
          <p className="eyebrow mb-1.5">{t(lang, "simEffects")}</p>
          <ul className="divide-y divide-line">
            {res.effects.map((e) => (
              <li key={e.lever} className="flex items-baseline justify-between gap-3 py-1.5 text-[13px]">
                <span className="truncate">{e.label}</span>
                <span className="num shrink-0">
                  <span className={e.sales >= 0 ? "text-cobalt" : "text-signal"}>{signedMoney(e.sales)}</span>
                  {e.profit != null && (
                    <span className="text-mute"> · {t(lang, "simProfit").toLowerCase()} <span className={e.profit >= 0 ? "text-cobalt" : "text-signal"}>{signedMoney(e.profit)}</span></span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {compact && onOpen && (
        <button onClick={onOpen} className="btn btn-outline mt-4 px-3 py-1.5 text-[12.5px]">
          <Icon name="flask" size={13} /> {t(lang, "simOpen")}
        </button>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- levers */

function Lever({ on, onToggle, label, hint, children }) {
  return (
    <section className={`sheet p-4 transition ${on ? "border-ink/50" : ""}`}>
      <Switch checked={on} onChange={onToggle} label={label} hint={hint} />
      {on && <div className="mt-3 space-y-3 border-t border-line pt-3 animate-rise">{children}</div>}
    </section>
  );
}

function Range({ label, value, min, max, step = 1, onChange, show = (v) => `${v}%` }) {
  return (
    <label className="block">
      <span className="flex items-baseline justify-between gap-3 text-[12.5px]">
        <span className="text-mute">{label}</span>
        <span className="num font-medium">{show(value)}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="range mt-1.5" aria-label={label} />
    </label>
  );
}

function ProductSelect({ products, value, onChange, allLabel, lang }) {
  return (
    <label className="block">
      <span className="eyebrow">{t(lang, "lvProduct")}</span>
      <Select value={value} onChange={(e) => onChange(e.target.value)} className="mt-1">
        {allLabel != null && <option value="">{allLabel}</option>}
        {products.map((p) => (
          <option key={p.name} value={p.name}>{p.name}{p.margin != null ? ` · ${Math.round(p.margin * 100)}%` : ""}</option>
        ))}
      </Select>
    </label>
  );
}

const SENS = ["low", "medium", "high"];

const defaults = (o) => ({
  close_day: { on: false, day: o.defaults.close_day, shift: 50 },
  price: { on: false, product: "", pct: 5, sensitivity: "medium" },
  offer: { on: false, product: o.defaults.offer_product, pct: 10, uplift: 20 },
  drop: { on: false, product: o.defaults.drop_product, loss: 10 },
  no_udhaar: { on: false, lost: 30 },
  winback: { on: false, rate: 20 },
});

const toLevers = (lv) => {
  const out = {};
  if (lv.close_day.on) out.close_day = { day: lv.close_day.day, shift: lv.close_day.shift / 100 };
  if (lv.price.on) out.price = { product: lv.price.product || null, pct: lv.price.pct, sensitivity: lv.price.sensitivity };
  if (lv.offer.on) out.offer = { product: lv.offer.product, pct: lv.offer.pct, uplift: lv.offer.uplift / 100 };
  if (lv.drop.on) out.drop = { product: lv.drop.product, loss: lv.drop.loss / 100 };
  if (lv.no_udhaar.on) out.no_udhaar = { lost: lv.no_udhaar.lost / 100 };
  if (lv.winback.on) out.winback = { rate: lv.winback.rate / 100 };
  return out;
};

export default function Simulator({ dataset, lang }) {
  const [opts, setOpts] = useState(null);
  const [lv, setLv] = useState(null);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const timer = useRef(null);
  const seq = useRef(0);

  useEffect(() => {
    let live = true;
    setOpts(null); setLv(null); setRes(null); setErr("");
    simulateOptions(dataset.id)
      .then((o) => { if (!live) return; setOpts(o); if (o.available) setLv(defaults(o)); })
      .catch((e) => live && setOpts({ available: false, reason: detail(e, "Couldn't read this file.") }));
    return () => { live = false; };
  }, [dataset.id]);

  // Every lever change re-runs the replay, lightly debounced; a stale answer never overwrites a newer one.
  useEffect(() => {
    if (!lv) return undefined;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const my = ++seq.current;
      setBusy(true); setErr("");
      runSimulation(dataset.id, toLevers(lv))
        .then((r) => { if (my === seq.current) setRes(r); })
        .catch((e) => { if (my === seq.current) setErr(detail(e, "Couldn't run that.")); })
        .finally(() => { if (my === seq.current) setBusy(false); });
    }, 250);
    return () => clearTimeout(timer.current);
  }, [lv, dataset.id]);

  const set = (k, patch) => setLv((x) => ({ ...x, [k]: { ...x[k], ...patch } }));

  if (opts && !opts.available) {
    return <div className="mx-auto w-full max-w-[780px] px-5 py-8 sm:px-8"><Notice tone="info">{t(lang, "simNone")}</Notice></div>;
  }

  const busiest = opts ? opts.weekdays.reduce((a, w) => (w.avg > a.avg ? w : a)).index : null;
  const quietest = opts ? opts.weekdays.reduce((a, w) => (w.avg < a.avg ? w : a)).index : null;
  const changed = res && Object.keys(res.levers || {}).length > 0;

  return (
    <div className="mx-auto w-full max-w-[1120px] px-5 py-6 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">{t(lang, "simulate")}</p>
          <h2 className="display mt-2 text-[30px] leading-tight sm:text-[36px]">{t(lang, "simTitle")}</h2>
          <p className="mt-2 max-w-[640px] text-[13.5px] leading-snug text-mute">{t(lang, "simIntro")}</p>
        </div>
        {opts && (
          <p className="eyebrow">
            {fill(t(lang, "simReplays"), { n: opts.sims.toLocaleString("en-IN"), w: Math.round(opts.pool_days / 7) })} · {shortDate(opts.start)} – {shortDate(opts.end)}
          </p>
        )}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[330px_minmax(0,1fr)]">
        <aside className="space-y-3">
          {!opts || !lv ? (
            [0, 1, 2, 3].map((i) => <div key={i} className="shimmer h-16 rounded-[12px]" style={{ animationDelay: `${i * 100}ms` }} />)
          ) : (
            <>
              <Lever on={lv.close_day.on} onToggle={(v) => set("close_day", { on: v })} label={t(lang, "lvClose")} hint={t(lang, "lvCloseHint")}>
                <label className="block">
                  <span className="eyebrow">{t(lang, "lvDay")}</span>
                  <Select value={lv.close_day.day} onChange={(e) => set("close_day", { day: Number(e.target.value) })} className="mt-1">
                    {opts.weekdays.map((w) => (
                      <option key={w.index} value={w.index}>
                        {w.name} · {signedPct(w.vs_avg)}{w.index === busiest ? ` · ${t(lang, "simBusiest")}` : w.index === quietest ? ` · ${t(lang, "simQuietest")}` : ""}
                      </option>
                    ))}
                  </Select>
                </label>
                <Range label={t(lang, "lvShift")} value={lv.close_day.shift} min={0} max={100} step={5} onChange={(v) => set("close_day", { shift: v })} />
              </Lever>

              <Lever on={lv.price.on} onToggle={(v) => set("price", { on: v })} label={t(lang, "lvPrice")} hint={t(lang, "lvPriceHint")}>
                <ProductSelect products={opts.products} value={lv.price.product} onChange={(v) => set("price", { product: v })} allLabel={t(lang, "lvAll")} lang={lang} />
                <Range label={t(lang, "lvPct")} value={lv.price.pct} min={-20} max={20} step={1} onChange={(v) => set("price", { pct: v })} show={(v) => `${v >= 0 ? "+" : "−"}${Math.abs(v)}%`} />
                <div>
                  <span className="eyebrow">{t(lang, "lvSens")}</span>
                  <div className="mt-1.5 flex gap-1.5">
                    {SENS.map((s) => (
                      <button key={s} type="button" aria-pressed={lv.price.sensitivity === s} onClick={() => set("price", { sensitivity: s })}
                        className={`chip px-3 py-1 text-[12px] ${lv.price.sensitivity === s ? "!border-ink !bg-ink !text-sheet" : ""}`}>
                        {t(lang, `sens${s[0].toUpperCase()}${s.slice(1)}`)}
                      </button>
                    ))}
                  </div>
                </div>
              </Lever>

              <Lever on={lv.offer.on} onToggle={(v) => set("offer", { on: v })} label={t(lang, "lvOffer")} hint={t(lang, "lvOfferHint")}>
                <ProductSelect products={opts.products} value={lv.offer.product} onChange={(v) => set("offer", { product: v })} lang={lang} />
                <Range label={t(lang, "lvDiscount")} value={lv.offer.pct} min={5} max={50} step={5} onChange={(v) => set("offer", { pct: v })} />
                <Range label={t(lang, "lvUplift")} value={lv.offer.uplift} min={0} max={100} step={5} onChange={(v) => set("offer", { uplift: v })} show={(v) => `+${v}%`} />
              </Lever>

              <Lever on={lv.drop.on} onToggle={(v) => set("drop", { on: v })} label={t(lang, "lvDrop")} hint={t(lang, "lvDropHint")}>
                <ProductSelect products={opts.products} value={lv.drop.product} onChange={(v) => set("drop", { product: v })} lang={lang} />
                <Range label={t(lang, "lvLoss")} value={lv.drop.loss} min={0} max={50} step={5} onChange={(v) => set("drop", { loss: v })} />
              </Lever>

              {opts.levers.no_udhaar && (
                <Lever on={lv.no_udhaar.on} onToggle={(v) => set("no_udhaar", { on: v })} label={t(lang, "lvUdhaar")} hint={t(lang, "lvUdhaarHint")}>
                  <Range label={t(lang, "lvLost")} value={lv.no_udhaar.lost} min={0} max={100} step={5} onChange={(v) => set("no_udhaar", { lost: v })} />
                </Lever>
              )}

              {opts.levers.winback && (
                <Lever on={lv.winback.on} onToggle={(v) => set("winback", { on: v })} label={t(lang, "lvWinback")} hint={fill(t(lang, "lvWinbackHint"), { n: opts.quiet })}>
                  <Range label={t(lang, "lvRate")} value={lv.winback.rate} min={0} max={100} step={5} onChange={(v) => set("winback", { rate: v })} />
                </Lever>
              )}
            </>
          )}
        </aside>

        <section className="min-w-0">
          <div className="mb-3 flex items-center gap-2.5">
            <span className="eyebrow">{res ? fill(t(lang, "simNext"), { n: res.horizon }) : t(lang, "thinking")}</span>
            <span className="h-px flex-1 bg-line" />
            {busy && <ThinkingMark size={16} />}
          </div>
          {err && <div className="mb-3"><Notice>{err}</Notice></div>}
          {res ? (
            <div className={busy ? "opacity-70 transition" : "transition"}>
              <Outcome res={res} lang={lang} />
              <div className="mt-5 space-y-2 text-[14.5px] leading-[1.6]">
                {lang === "hi" ? (
                  <>
                    <p>{fill(t("hi", "simHiBase"), { n: res.horizon, p50: money(res.baseline.sales.p50), p10: money(res.baseline.sales.p10), p90: money(res.baseline.sales.p90) })}</p>
                    {changed ? (
                      <p>
                        {fill(t("hi", "simHiWith"), { s: money(res.scenario.sales.p50), d: signedMoney(res.delta.sales.p50), pct: signedPct(res.delta.sales.pct) })}
                        {res.has_cost && ` ${fill(t("hi", "simHiProfit"), { d: signedMoney(res.delta.profit.p50), pct: signedPct(res.delta.profit.pct) })}`}
                      </p>
                    ) : <p className="text-mute">{t("hi", "simHiNone")}</p>}
                  </>
                ) : (
                  res.narrative.map((line, i) => <p key={i} className={i === 0 ? "" : "text-ink/85"}>{line}</p>)
                )}
              </div>
              <details className="mt-4 text-[13px]">
                <summary className="eyebrow cursor-pointer hover:text-ink">{t(lang, "simAssumptions")}</summary>
                <ul className="mt-2 space-y-1.5 text-mute">
                  {res.assumptions.map((a, i) => <li key={i} className="flex gap-2"><span className="text-ink/40">—</span><span>{a}</span></li>)}
                </ul>
              </details>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">{[0, 1, 2].map((i) => <div key={i} className="shimmer h-[74px] rounded-[10px]" />)}</div>
              <div className="shimmer h-56 rounded-[12px]" />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
