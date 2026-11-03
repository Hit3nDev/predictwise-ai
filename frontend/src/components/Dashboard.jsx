import { useEffect, useState } from "react";
import { getPlaybook, getAnomalies, getToolkit, shopTool, getCustomers, getStockPlan } from "../api";
import { LineChart, BarChart, formatValue } from "./blocks";
import { Readout, Tag } from "./ui";
import { Icon } from "./icons";

/* The shop at a glance. Every tile is one of the engines the chat uses, shown without being
   asked; "Ask" on a tile drops the matching question into the chat. Tiles load independently
   and only the ones this file can support appear. */

const pretty = (s) => String(s).replace(/[_\s]+/g, " ").trim();
const pct = (s) => parseFloat(String(s).replace("%", "")) || 0;

function Tile({ title, note, ask, onAsk, children, className = "" }) {
  return (
    <section className={`sheet flex flex-col overflow-hidden ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <span className="text-[13.5px] font-semibold">{title}</span>
        <span className="flex items-center gap-3">
          {note && <span className="eyebrow">{note}</span>}
          {ask && (
            <button onClick={() => onAsk(ask)} className="eyebrow inline-flex items-center gap-1 hover:text-ink">
              Ask <Icon name="arrow" size={11} />
            </button>
          )}
        </span>
      </header>
      <div className="flex-1 p-4">{children}</div>
    </section>
  );
}

function Skeleton({ lines = 3 }) {
  return (
    <div className="space-y-2.5">
      {[...Array(lines)].map((_, i) => <div key={i} className="shimmer h-3.5 rounded-full" style={{ width: `${92 - i * 18}%` }} />)}
    </div>
  );
}

const TONE = { do: "bg-cobalt", watch: "bg-signal", good: "bg-lime" };

function Actions({ items }) {
  return (
    <ol className="space-y-2">
      {items.slice(0, 4).map((it, i) => (
        <li key={i} className="flex gap-3">
          <span className={`mt-1 h-[calc(100%-4px)] w-[3px] shrink-0 self-stretch rounded-full ${TONE[it.tone] ?? "bg-line"}`} />
          <div className="min-w-0">
            <p className="text-[13.5px] font-semibold leading-snug">{it.title}</p>
            <p className="mt-0.5 text-[12.5px] leading-snug text-mute">{it.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Weekdays({ rows }) {
  if (!rows?.length) return null;
  const vals = rows.map((r) => 100 + pct(r["Compared with an average day"]));
  const max = Math.max(...vals);
  const best = vals.indexOf(max);
  return (
    <div className="flex h-28 items-end gap-1.5">
      {rows.map((r, i) => (
        <div key={r.Day} className="flex flex-1 flex-col items-center gap-1.5" title={`${r.Day}: ${r["Average sales"]}`}>
          <span className="num text-[10px] text-mute">{pct(r["Compared with an average day"]) > 0 ? "+" : ""}{Math.round(pct(r["Compared with an average day"]))}%</span>
          <div className={`bar-grow w-full rounded-t-[3px] ${i === best ? "bg-cobalt" : "bg-ink/25"}`} style={{ height: `${(vals[i] / max) * 72}px`, animationDelay: `${i * 40}ms` }} />
          <span className="eyebrow !text-[9.5px]">{r.Day.slice(0, 3)}</span>
        </div>
      ))}
    </div>
  );
}

const GROUP_TONE = { Best: "bg-lime", Regular: "bg-cobalt", New: "bg-ink/60", "At risk": "bg-signal", Lost: "bg-line" };

function Groups({ groups, winback }) {
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-bone">
        {groups.map((g) => (
          <span key={g.Group} className={`${GROUP_TONE[g.Group] ?? "bg-line"} bar-grow`} style={{ width: g["Share of customers"] }} title={`${g.Group}: ${g.Customers} customers, ${g["Share of spend"]} of spend`} />
        ))}
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
        {groups.map((g) => (
          <li key={g.Group} className="flex items-center gap-2 text-[12.5px]">
            <span className={`h-2 w-2 rounded-full ${GROUP_TONE[g.Group] ?? "bg-line"}`} />
            <span className="flex-1 truncate">{g.Group}</span>
            <span className="num text-mute">{g.Customers} · {g["Share of spend"]}</span>
          </li>
        ))}
      </ul>
      {winback?.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="eyebrow mb-1.5">Call first</p>
          {winback.slice(0, 3).map((w) => (
            <p key={w.Customer} className="flex justify-between gap-3 py-0.5 text-[13px]">
              <span className="truncate">{w.Customer}</span>
              <span className="num shrink-0 text-mute">{w["Last visit"]} · {w["Total spent"]}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

const TREND = { rising: "text-cobalt", falling: "text-signal" };

export default function Dashboard({ dataset, brief, onAsk }) {
  const [s, setS] = useState({});

  useEffect(() => {
    let live = true;
    setS({});
    const id = dataset.id;
    const put = (k, v) => live && setS((x) => ({ ...x, [k]: v }));
    const load = (k, p) => p.then((v) => put(k, v)).catch(() => put(k, { error: true }));
    load("playbook", getPlaybook(id));
    load("anomalies", getAnomalies(id));
    getToolkit(id)
      .then((tk) => {
        put("toolkit", tk);
        if (tk.peak?.available) load("peak", shopTool(id, "peak"));
        if (tk.profit?.available) load("profit", shopTool(id, "profit"));
        if (tk.udhaar?.available) load("udhaar", shopTool(id, "udhaar"));
        if (tk.festival?.available) load("festival", shopTool(id, "festival"));
        if (tk.rfm?.available) load("customers", getCustomers(id));
        if (tk.stock?.available) load("stock", getStockPlan(id));
      })
      .catch(() => put("toolkit", {}));
    return () => { live = false; };
  }, [dataset.id]);

  const line = brief?.charts?.find((c) => c.chart === "line");
  const bar = brief?.charts?.find((c) => c.chart === "bar");
  const latest = line && line.points.length >= 2 ? { v: line.points.at(-1).value, p: line.points.at(-2).value, label: line.points.at(-1).label } : null;
  const chg = latest && latest.p ? (latest.v - latest.p) / Math.abs(latest.p) : null;
  const tk = s.toolkit;
  const want = (id) => tk == null || Boolean(tk[id]?.available);

  /* A tile shows a skeleton until its data arrives and disappears if the file cannot support it. */
  const tile = (k, title, ask, render, extra = {}) => {
    const v = s[k];
    if (v && (v.error || v.available === false)) return null;
    return (
      <Tile key={k} title={title} ask={ask} onAsk={onAsk} className={extra.className} note={extra.note}>
        {v ? render(v) : <Skeleton />}
      </Tile>
    );
  };

  return (
    <div className="mx-auto w-full max-w-[1100px] px-5 py-6 sm:px-8">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {brief ? (
          <>
            {brief.stats.slice(0, 4).map((st) => <Readout key={st.label} value={st.value} label={st.label} />)}
            {latest && (
              <Readout
                value={formatValue(latest.v, line.unit)}
                label={`${chg == null ? "" : `${chg >= 0 ? "▲" : "▼"} ${Math.abs(Math.round(chg * 100))}% · `}${latest.label}`}
                tone={chg == null ? "plain" : chg >= 0 ? "good" : "warn"}
              />
            )}
            <Readout value={`${brief.quality.score}/100`} label={`data health · ${brief.quality.label.toLowerCase()}`} tone={brief.quality.score >= 75 ? "good" : "warn"} />
          </>
        ) : (
          [...Array(6)].map((_, i) => <div key={i} className="shimmer h-[74px] rounded-[10px]" />)
        )}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {line && (
          <Tile title={line.title} note={line.forecast?.length ? "with forecast" : undefined} ask={`What will ${pretty(brief.roles?.metric || "sales")} look like next month?`} onAsk={onAsk} className="md:col-span-2">
            <LineChart points={line.points} forecast={line.forecast} unit={line.unit} />
          </Tile>
        )}
        {bar && (
          <Tile title={bar.title} ask={`Which ${pretty(brief.roles?.category || "product")} gives the most ${pretty(brief.roles?.metric || "sales")}?`} onAsk={onAsk}>
            <BarChart points={bar.points.slice(0, 6)} unit={bar.unit} />
          </Tile>
        )}
        {brief && !line && !bar && (
          <Tile title="What is in this file" onAsk={onAsk} ask="What does my data look like?" className="md:col-span-2">
            <ul className="space-y-1.5 text-[13.5px]">{brief.headline.map((h, i) => <li key={i}>{h}</li>)}</ul>
          </Tile>
        )}

        {tile("playbook", "This week", "What should I do this week?", (v) => <Actions items={v.items} />, { className: "md:col-span-2 xl:col-span-1" })}

        {want("peak") && tile("peak", "Busiest days", "Which day is busiest?", (v) => <Weekdays rows={v.blocks?.[0]?.rows} />)}

        {want("udhaar") && tile("udhaar", "Udhaar", "Who owes me money?", (v) => (
          <div>
            <p className="num text-[26px] font-medium leading-none text-signal">{formatValue(v.total, "money")}</p>
            <p className="eyebrow mt-1.5">owed by {v.rows.length}{v.rows.length === 25 ? "+" : ""} customers</p>
            <ul className="mt-3 divide-y divide-line">
              {v.rows.slice(0, 3).map((r) => (
                <li key={r.Customer} className="flex items-baseline justify-between gap-3 py-1.5 text-[13px]">
                  <span className="truncate">{r.Customer}</span>
                  <span className="num shrink-0 text-mute">{r.Owes}</span>
                </li>
              ))}
            </ul>
            <button onClick={() => onAsk("Write a WhatsApp reminder message for my udhaar customers")} className="btn btn-outline mt-3 px-3 py-1.5 text-[12.5px]">
              <Icon name="share" size={13} /> Send reminders
            </button>
          </div>
        ))}

        {want("profit") && tile("profit", "What earns money", "Which products give me the most profit?", (v) => (
          <div>
            <ul className="divide-y divide-line">
              {v.rows.slice(0, 4).map((r) => (
                <li key={r.Product} className="flex items-center justify-between gap-3 py-1.5 text-[13px]">
                  <span className="min-w-0 truncate">{r.Product}{r.Verdict === "Sells a lot but earns little" && <Tag tone="signal" className="ml-2">low margin</Tag>}</span>
                  <span className="num shrink-0 text-mute">{r.Profit} · {r.Margin}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[12.5px] leading-snug text-mute">{v.narrative[0]}</p>
          </div>
        ))}

        {want("festival") && tile("festival", "Next festival", "What should I stock for the next festival?", (v) => (
          <div>
            {v.upcoming?.length > 0 ? (
              <>
                <p className="display text-[24px] leading-none" style={{ fontVariationSettings: '"WONK" 0' }}>{v.upcoming[0][0]}</p>
                <p className="eyebrow mt-1.5">{v.upcoming[0][1]}{v.upcoming[1] ? ` · then ${v.upcoming[1][0]}` : ""}</p>
              </>
            ) : null}
            <p className="mt-3 text-[13px] leading-snug">{v.narrative[0]}</p>
            {v.picks?.[0]?.[1]?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {v.picks[0][1].map((p) => <span key={p} className="rounded-full bg-lime px-2.5 py-0.5 text-[12px] text-[#111111]">{p}</span>)}
              </div>
            )}
          </div>
        ))}

        {want("rfm") && tile("customers", "Customer groups", "Which customers should I win back?", (v) => <Groups groups={v.groups} winback={v.winback} />)}

        {want("stock") && tile("stock", "Order for next week", "How much should I order?", (v) => (
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="eyebrow">
                <th className="pb-1.5 text-left font-normal">Product</th>
                <th className="pb-1.5 text-right font-normal">Likely</th>
                <th className="pb-1.5 text-right font-normal">Order</th>
              </tr>
            </thead>
            <tbody>
              {v.rows.slice(0, 5).map((r) => (
                <tr key={r.Product} className="border-t border-line">
                  <td className="py-1.5 pr-2"><span className="block truncate">{r.Product}</span><span className={`eyebrow !text-[9.5px] ${TREND[r.Trend] ?? ""}`}>{r.Trend}</span></td>
                  <td className="num py-1.5 text-right text-mute">{r["Likely next 7 days"].toLocaleString("en-IN")}</td>
                  <td className="num py-1.5 text-right font-medium">{r["Order about"].toLocaleString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ), { note: "95% service" })}

        {tile("anomalies", "Unusual entries", "Which rows look unusual?", (v) => (
          v.count ? (
            <div>
              <p className="num text-[26px] font-medium leading-none">{v.count}</p>
              <p className="eyebrow mt-1.5">rows worth a second look</p>
              <p className="mt-3 text-[13px] leading-snug text-mute">Row {v.rows[0].row_number}: {v.rows[0].reasons[0]}.</p>
            </div>
          ) : <p className="text-[13px] text-mute">{v.narrative[0]}</p>
        ))}
      </div>
    </div>
  );
}
