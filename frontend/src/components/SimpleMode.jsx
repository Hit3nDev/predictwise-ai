import { useEffect, useRef, useState } from "react";
import {
  uploadDataset, cleanDataset, getQuestionTemplates, chatWithDataset, predict, detail,
  listSamples, loadSample, getBriefing, downloadCleaned, llmStatus, getDigest, compareFiles, getToolkit,
} from "../api";
import { TrustNote, Track, Contributions, WhatIf, FairnessPanel, ReportLinks } from "./trust";
import { Blocks, BatchScore, Levers } from "./blocks";
import { LANGS, t } from "../i18n";
import { canListen, canSpeak, listen, speak, stopSpeaking } from "./voice";
import { Icon, LogoMark, ThinkingMark } from "./icons";
import { Switch, Tag } from "./ui";
import Dashboard from "./Dashboard";
import Lookup from "./Lookup";

/* Simple Mode is a conversation over one file. The start screen takes a file or a sample.
   The chat screen is a reading column with a "dossier" rail beside it that holds the file,
   the language, private mode, the shop toolkit and the actions. */

const TICKER = [
  "Who owes me money?", "What should I stock for Diwali?", "Which product earns the most?",
  "How much should I order next week?", "Will this customer buy again?", "Which day is busiest?",
  "What do people buy together?", "What stopped selling?", "Show sales by city as a chart",
  "Which customers should I win back?", "What should I do this week?", "Which rows look unusual?",
];

const SAMPLE_ICONS = { kirana_sales: "store", customers: "users", sweet_shop: "cake", provision_store: "basket" };

const HIGHLIGHTS = [
  { title: "Answers, not dashboards", body: "Profit, udhaar, stock and customers, in plain words." },
  { title: "Every number checked", body: "Calculated from your file by code, with the working shown." },
  { title: "English, Hindi, Hinglish", body: "Type or speak. Share any answer on WhatsApp in one tap." },
];

/* The label above every answer says where it came from. */
const SOURCE = {
  brief:    { key: "srcBrief",    dot: "bg-ink" },
  calc:     { key: "srcCalc",     dot: "bg-cobalt" },
  ai:       { key: "srcAi",       dot: "bg-lime ring-1 ring-ink/70" },
  model:    { key: "srcModel",    dot: "bg-cobalt" },
  fallback: { key: "srcFallback", dot: "bg-signal" },
  note:     { key: "srcNote",     dot: "bg-ink/30" },
};
/* kind "profile" from the offline path is the honest fallback ("I couldn't match that"),
   so it is labelled as such rather than as a calculation. */
const sourceOf = (m) =>
  m.lead ? "brief"
  : m.kind === "prediction" ? "model"
  : m.source === "llm" ? "ai"
  : m.kind === "profile" && m.source === "offline" ? "fallback"
  : m.source ? "calc" : "note";

function Ticker({ items }) {
  const row = (
    <span className="flex">
      {items.map((q) => (
        <span key={q} className="flex items-center gap-6 pr-6">
          <span>{q}</span>
          <span className="text-ink/30">✦</span>
        </span>
      ))}
    </span>
  );
  return (
    <div className="ticker border-b border-line" aria-hidden="true">
      <div className="ticker-track eyebrow py-2.5 !text-[11px] text-ink/60">{row}{row}</div>
    </div>
  );
}

function UserBubble({ children }) {
  return (
    <div className="flex animate-rise justify-end">
      <p className="max-w-[82%] rounded-[18px] rounded-br-[4px] bg-ink px-4 py-2.5 text-[15px] leading-relaxed text-sheet">
        {children}
      </p>
    </div>
  );
}

function Answer({ n, source, lang, children }) {
  const s = SOURCE[source];
  return (
    <article className="animate-rise">
      <header className="mb-3 flex items-center gap-2.5">
        <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
        <span className="eyebrow">{t(lang, s.key)}</span>
        <span className="h-px flex-1 bg-line" />
        <span className="num text-[11px] text-mute">{String(n).padStart(2, "0")}</span>
      </header>
      <div className="text-[15.5px] leading-[1.65]">{children}</div>
    </article>
  );
}

function RankingBars({ rows }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.value)));
  return (
    <div className="sheet mt-4 divide-y divide-line">
      {rows.map((row, i) => (
        <div key={row.name} className="grid grid-cols-[1.5rem_minmax(0,8rem)_1fr_5rem] items-center gap-3 px-4 py-2.5">
          <span className="num text-[11px] text-mute">{String(i + 1).padStart(2, "0")}</span>
          <span className="truncate text-[13.5px]" title={row.name}>{row.name}</span>
          <div className="h-2 overflow-hidden rounded-full bg-bone">
            <div
              className={`bar-grow h-2 rounded-full ${i === 0 ? "bg-cobalt" : "bg-ink/80"}`}
              style={{ width: `${(Math.abs(row.value) / max) * 100}%`, animationDelay: `${i * 50}ms` }}
            />
          </div>
          <span className="num text-right text-[12.5px] text-mute">{Math.round(row.value).toLocaleString("en-IN")}</span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ rows }) {
  if (!rows?.length) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="sheet mt-4 overflow-x-auto">
      <table className="w-full text-left text-[12.5px]">
        <thead className="bg-bone/70">
          <tr>{cols.map((c) => <th key={c} className="eyebrow whitespace-nowrap px-3 py-2 font-normal">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line hover:bg-bone/50">
              {cols.map((c) => <td key={c} className="num whitespace-nowrap px-3 py-2">{String(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function phraseOutcome(value) {
  const v = String(value).trim().toLowerCase();
  if (["1", "true", "yes"].includes(v)) return "Yes";
  if (["0", "false", "no"].includes(v)) return "No";
  return String(value);
}

function PredictForm({ msg, onPredict, busy, lang }) {
  const [values, setValues] = useState(Object.fromEntries((msg.fields || []).map((f) => [f.name, ""])));
  return (
    <div className="sheet mt-4 p-4 sm:p-5">
      <p className="eyebrow">{t(lang, "tryCase")}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {msg.fields.map((f) => (
          <label key={f.name} className="block">
            <span className="mb-1 block text-[12.5px] font-medium text-mute">
              {f.label}
              {f.type === "number" && f.min != null && <span className="num text-ink/35"> ({f.min}–{f.max})</span>}
            </span>
            {f.type === "select" ? (
              <select
                value={values[f.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                className="sel field-input py-2"
              >
                <option value="">—</option>
                {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input
                value={values[f.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                placeholder={f.typical != null ? String(f.typical) : ""}
                className="field-input num py-2"
              />
            )}
          </label>
        ))}
      </div>
      <button onClick={() => onPredict(msg, values)} disabled={busy} className="btn btn-solid mt-4">
        {busy ? t(lang, "working") : t(lang, "getAnswer")} <Icon name="arrow" size={14} />
      </button>
    </div>
  );
}

/* One-click shop tools. Each is an ordinary question, so the answer lands in the chat
   and can be followed up. Only the tools this file can power are offered. */
const TOOLKIT = [
  { id: "profit",  key: "tkProfit",   q: "Which products give me the most profit?" },
  { id: "udhaar",  key: "tkUdhaar",   q: "Who owes me money?" },
  { id: "stock",   key: "tkStock",    q: "How much should I order?" },
  { id: "festival", key: "tkFestival", q: "What should I stock for the next festival?" },
  { id: "slow",    key: "tkSlow",     q: "What is not selling?" },
  { id: "bundles", key: "tkBundles",  q: "What do customers buy together?" },
  { id: "peak",    key: "tkPeak",     q: "Which day is busiest?" },
  { id: "rfm",     key: "tkWinback",  q: "Which customers should I win back?" },
  { id: "udhaar",  key: "tkMsgUdhaar",   q: "Write a WhatsApp reminder message for my udhaar customers", msg: true },
  { id: "stock",   key: "tkMsgSupplier", q: "Write a WhatsApp order message to my supplier", msg: true },
  { id: "rfm",     key: "tkMsgWinback",  q: "Write a WhatsApp message to bring back my customers", msg: true },
];

function Toolkit({ toolkit, lang, onAsk, shop, setShop }) {
  const tools = TOOLKIT.filter((x) => toolkit?.[x.id]?.available);
  if (!tools.length) return null;
  return (
    <div>
      <p className="eyebrow flex items-center gap-2">
        {t(lang, "toolkit")}
        <span className="num rounded-full bg-lime px-1.5 py-px text-[10px] text-[#111111]">{tools.length}</span>
      </p>
      <ul className="mt-2 border-t border-line">
        {tools.map((x, i) => (
          <li key={x.key}>
            <button onClick={() => onAsk(x.q)} className="group flex w-full items-center gap-3 border-b border-line py-2.5 text-left text-[13px] hover:text-cobalt">
              <span className="num w-4 shrink-0 text-[10.5px] text-mute group-hover:text-cobalt">{String(i + 1).padStart(2, "0")}</span>
              <span className="flex-1 leading-snug">{t(lang, x.key)}</span>
              <Icon name={x.msg ? "share" : "arrow"} size={13} className="shrink-0 -translate-x-1 opacity-0 transition group-hover:translate-x-0 group-hover:opacity-100" />
            </button>
          </li>
        ))}
      </ul>
      <label className="mt-3 block">
        <span className="eyebrow">{t(lang, "shopName")}</span>
        <input value={shop} onChange={(e) => setShop(e.target.value)} maxLength={60} className="field-input mt-1.5 py-2 text-[13px]" />
      </label>
    </div>
  );
}

function Fold({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mt-4 border-t border-line pt-3">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="group inline-flex items-center gap-2 text-[13.5px] font-medium hover:text-cobalt">
        <span className={`flex h-5 w-5 items-center justify-center rounded-full border border-ink/25 transition group-hover:border-cobalt ${open ? "rotate-90" : ""}`}>
          <Icon name="chevron" size={11} strokeWidth={2.2} />
        </span>
        {label}
      </button>
      {open && <div className="animate-rise">{children}</div>}
    </div>
  );
}

function AnswerActions({ msg, lang, speakingId, onSpeak, id }) {
  const [copied, setCopied] = useState(false);
  const playbook = msg.blocks?.find((b) => b.type === "playbook");
  const text = [...msg.narrative, ...(playbook ? playbook.items.map((i, n) => `${n + 1}. ${i.title}. ${i.detail}`) : [])].join(playbook ? "\n" : " ");
  const wa = `https://wa.me/?text=${encodeURIComponent(text + "\n\n(PredictWise)")}`;
  const link = "eyebrow inline-flex items-center gap-1.5 hover:text-ink";
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  return (
    <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
      {canSpeak() && (
        <button className={link} onClick={() => onSpeak(id, text)}>
          <Icon name="sound" size={13} /> {speakingId === id ? t(lang, "stop") : t(lang, "listen")}
        </button>
      )}
      <button className={link} onClick={copy}><Icon name="copy" size={13} /> {copied ? t(lang, "copied") : t(lang, "copy")}</button>
      <a className={link} href={wa} target="_blank" rel="noreferrer"><Icon name="share" size={13} /> {t(lang, "share")}</a>
    </div>
  );
}

function AssistantContent({ msg, onPredict, predicting, lang }) {
  return (
    <div>
      {msg.narrative.map((line, i) => (
        <p key={i} className={i > 0 ? "mt-2" : ""}>{line}</p>
      ))}
      <Blocks
        blocks={msg.blocks} workLabel={t(lang, "work")} downloadLabel={t(lang, "downloadTable")}
        verifyText={(b) => {
          const key = { all: "vAll", partly: "vPart", none: "vNone", nocalc: "vNoCalc" }[b.status];
          return t(lang, key).replace("{n}", b.checked).replace("{m}", b.matched).replace("{list}", b.unmatched.join(", "));
        }}
        msgLabels={{ send: t(lang, "sendWa"), copy: t(lang, "copy"), copied: t(lang, "copied"), noNumber: t(lang, "noNumber"), showAll: t(lang, "showAll") }}
      />
      {msg.kind === "ranking" && msg.ranking && <RankingBars rows={msg.ranking} />}
      {msg.kind === "table" && msg.table && <DataTable rows={msg.table} />}
      {msg.kind === "prediction" && (
        <>
          <TrustNote trust={msg.trust} plain />
          <Track range={msg.range} reliability={msg.reliability} />
          {msg.explanation && (
            <Fold label={t(lang, "why")} defaultOpen>
              <Contributions explanation={msg.explanation} plain limit={5} />
            </Fold>
          )}
          <Fold label={t(lang, "levers")}>
            <Levers modelId={msg.model_id} row={msg.row} plain />
          </Fold>
          <Fold label={t(lang, "whatIf")}>
            <WhatIf modelId={msg.model_id} row={msg.row} features={msg.features} plain />
          </Fold>
        </>
      )}
      {msg.kind === "predictable" && msg.fields?.length > 0 && (
        <>
          <PredictForm msg={msg} onPredict={onPredict} busy={predicting} lang={lang} />
          <Fold label={t(lang, "scoreFile")}>
            <BatchScore modelId={msg.model_id} plain />
          </Fold>
          <Fold label={t(lang, "fair")}>
            <div className="mt-3">
              <FairnessPanel modelId={msg.model_id} plain />
              <div className="mt-4"><ReportLinks modelId={msg.model_id} /></div>
            </div>
          </Fold>
        </>
      )}
    </div>
  );
}

/* The rail beside the conversation: the file, the settings, the shop toolkit, the actions. */
function Dossier({ dataset, datasets, lang, setLang, priv, setPriv, llmOk, toolkit, onAsk, shop, setShop, onShare, onDownload, onCompare, onSwitch }) {
  const others = datasets.filter((x) => x.id !== dataset.id);
  const row = "flex w-full items-center gap-2.5 py-2.5 text-left text-[13px] hover:text-cobalt";
  return (
    <div className="flex flex-col gap-7 p-5">
      <div>
        <p className="eyebrow">{t(lang, "chattingAbout")}</p>
        <p className="mt-1.5 truncate text-[15px] font-semibold" title={dataset.file_name}>{dataset.file_name}</p>
        <p className="num mt-1 text-[11.5px] text-mute">
          {dataset.row_count.toLocaleString("en-IN")} rows · {dataset.column_count} columns{dataset.is_cleaned ? " · cleaned" : ""}
        </p>
        <button onClick={onSwitch} className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] text-mute hover:text-ink">
          <Icon name="swap" size={13} /> {t(lang, "switchFile")}
        </button>
      </div>

      {/* Whether the open-ended assistant is available. Without a key the engines still
          answer counts, trends, forecasts and the toolkit; anything else gets an overview. */}
      <div className={`rounded-[10px] border px-3.5 py-3 ${llmOk ? "border-line" : "border-signal/35 bg-signal/[0.06]"}`}>
        <p className={`eyebrow flex items-center gap-2 ${llmOk ? "" : "!text-signal"}`}>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${llmOk ? "bg-lime" : "bg-signal"}`} />
          {t(lang, llmOk ? "aiOn" : "aiOff")}
        </p>
        {!llmOk && <p className="mt-1.5 text-[12px] leading-snug text-mute">{t(lang, "aiOffHint")}</p>}
      </div>

      <div>
        <p className="eyebrow">{t(lang, "language")}</p>
        <div className="mt-2 grid grid-cols-3 rounded-[8px] border border-line bg-bone p-0.5" role="group" aria-label="Language">
          {LANGS.map((l) => (
            <button
              key={l.id}
              onClick={() => setLang(l.id)}
              aria-pressed={lang === l.id}
              className={`rounded-[6px] py-1.5 text-[12.5px] font-medium ${lang === l.id ? "bg-ink text-sheet" : "text-mute hover:text-ink"}`}
            >
              {l.label}
            </button>
          ))}
        </div>
        {lang !== "en" && !llmOk && !priv && <p className="mt-2 text-[12px] leading-snug text-mute">{t(lang, "hindiNote")}</p>}
      </div>

      <div>
        <Switch checked={priv} onChange={setPriv} label={t(lang, "privateMode")} hint={t(lang, "privateHint")} />
      </div>

      <Toolkit toolkit={toolkit} lang={lang} onAsk={onAsk} shop={shop} setShop={setShop} />

      <div>
        <p className="eyebrow">{t(lang, "actions")}</p>
        <ul className="mt-2 divide-y divide-line border-y border-line">
          <li><button onClick={onShare} className={row}><Icon name="share" size={14} /> {t(lang, "shareSummary")}</button></li>
          <li><button onClick={onDownload} className={row}><Icon name="download" size={14} /> {t(lang, "download")}</button></li>
          {others.length > 0 && (
            <li className="flex items-center gap-2.5 py-2">
              <Icon name="compare" size={14} className="shrink-0" />
              <select value="" onChange={(e) => onCompare(e.target.value)} aria-label={t(lang, "compareWith")} className="sel field-input border-0 bg-transparent px-1 py-1 text-[13px] hover:bg-bone">
                <option value="">{t(lang, "compareWith")}</option>
                {others.map((x) => <option key={x.id} value={x.id}>{x.file_name}</option>)}
              </select>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

/* Ready-made questions, grouped, built from what this file can answer: the roles the
   briefing found (date, amount, category, outcome) and which toolkit tools are available. */
function buildLibrary(roles, toolkit, llmOk) {
  const r = roles || {};
  const tk = toolkit || {};
  const p = (s) => String(s).replace(/[_\s]+/g, " ").trim();
  const metric = r.metric ? p(r.metric) : null;
  const cat = r.category ? p(r.category) : null;
  const outcome = r.outcome ? p(r.outcome) : null;
  const has = (id) => Boolean(tk[id]?.available);
  const groups = [
    { title: "Sales & trends", items: [
      "What should I do this week?",
      r.date && metric && `What will ${metric} look like next month?`,
      r.date && metric && `Show me ${metric} by month as a chart`,
      has("peak") && "Which day is busiest?",
      cat && metric && `Which ${cat} gives the most ${metric}?`,
      cat && metric && `Top 5 ${cat} by ${metric}`,
      metric && `What is the total ${metric}?`,
      metric && `What is the average ${metric}?`,
    ] },
    { title: "Customers", items: [
      has("rfm") && "Which customers should I call first?",
      has("rfm") && "Which customers should I win back?",
      has("udhaar") && "Who owes me money?",
      "Show me my customer groups",
      outcome && "Will this happen again?",
      outcome && `What affects ${outcome}?`,
    ] },
    { title: "Stock & products", items: [
      has("stock") && "How much should I order?",
      has("stock") && "How accurate is the stock plan?",
      has("slow") && "What is not selling?",
      has("bundles") && "What do customers buy together?",
      has("festival") && "What should I stock for the next festival?",
    ] },
    { title: "Money", items: [
      has("profit") && "Which products give me the most profit?",
      has("profit") && "What is my overall profit margin?",
    ] },
    { title: "Messages", items: [
      has("udhaar") && "Write a WhatsApp reminder message for my udhaar customers",
      has("stock") && "Write a WhatsApp order message to my supplier",
      has("rfm") && "Write a WhatsApp message to bring back my customers",
    ] },
    { title: "Data", items: ["Which rows look unusual?", "Is my data clean?", "What does my data look like?"] },
    llmOk && { title: "Ask the AI anything", ai: true, items: [
      r.date && metric && `Compare ${metric} on weekends and weekdays`,
      cat && metric && r.date && `Which ${cat} grew the most in the last month?`,
      cat && metric && `What is the average ${metric} per ${cat}?`,
    ] },
  ];
  return groups.filter(Boolean).map((g) => ({ ...g, items: g.items.filter(Boolean) })).filter((g) => g.items.length);
}

function Library({ groups, lang, onAsk, onClose }) {
  return (
    <div className="mx-auto w-full max-w-[780px] px-5 pb-3 sm:px-8">
      <div className="sheet max-h-[48vh] overflow-y-auto p-4 animate-rise sm:p-5">
        <div className="mb-3 flex items-center justify-between">
          <p className="eyebrow">{t(lang, "library")}</p>
          <button onClick={onClose} className="btn btn-ghost px-2 py-1" aria-label="Close"><Icon name="x" size={14} /></button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {groups.map((g) => (
            <div key={g.title}>
              <p className="mb-2 flex items-center gap-1.5 text-[12.5px] font-semibold">
                {g.ai && <Icon name="spark" size={12} className="text-cobalt" />}{g.title}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {g.items.map((q) => <button key={q} onClick={() => onAsk(q)} className="chip py-1 text-[12.5px]">{q}</button>)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function loadLang() {
  try { return localStorage.getItem("pw-lang") || "en"; } catch { return "en"; }
}

export default function SimpleMode({ dataset, setDataset, datasets, refresh }) {
  const [step, setStep] = useState("upload");
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [samples, setSamples] = useState([]);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [error, setError] = useState("");
  const [lang, setLangState] = useState(loadLang);
  const [priv, setPrivState] = useState(() => { try { return localStorage.getItem("pw-private") === "1"; } catch { return false; } });
  const setPriv = (v) => { setPrivState(v); try { localStorage.setItem("pw-private", v ? "1" : "0"); } catch { /* fine */ } };
  const [llmOk, setLlmOk] = useState(true);
  const [listening, setListening] = useState(false);
  const [speakingId, setSpeakingId] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [toolkit, setToolkit] = useState(null);
  const [briefing, setBriefing] = useState(false);
  const [brief, setBrief] = useState(null);         // the raw briefing, shared with the dashboard
  const [view, setView] = useState("chat");         // chat | dashboard | lookup
  const [library, setLibrary] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [shop, setShopState] = useState(() => { try { return localStorage.getItem("pw-shop") || ""; } catch { return ""; } });
  const setShop = (v) => { setShopState(v); try { localStorage.setItem("pw-shop", v); } catch { /* storage blocked */ } };
  const scrollRef = useRef(null);
  const recRef = useRef(null);
  const inputRef = useRef(null);

  // Press "/" anywhere on the chat screen to start typing.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = e.target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target?.isContentEditable) return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const speech = LANGS.find((l) => l.id === lang)?.speech ?? "en-IN";
  const setLang = (l) => {
    setLangState(l);
    try { localStorage.setItem("pw-lang", l); } catch { /* private mode: fine */ }
  };

  useEffect(() => {
    listSamples().then(setSamples).catch(() => {});
    llmStatus().then((s) => setLlmOk(Boolean(s.configured))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!dataset) return;
    setStep("chat");
    setView("chat");
    setLibrary(false);
    setBrief(null);
    setMessages([]);
    setSuggestions([]);
    getQuestionTemplates(dataset.id).then(setTemplates).catch(() => {});
    setToolkit(null);
    getToolkit(dataset.id).then(setToolkit).catch(() => {});
    // The first thing you see is what the data says, before you ask anything.
    setBriefing(true);
    getBriefing(dataset.id)
      .then((b) => {
        setBrief(b);
        const narrative = [...b.headline];
        if (b.quality.issues.length) narrative.push(b.quality.issues[0]);
        setMessages([{
          role: "assistant", kind: "briefing", source: "analytics", lead: true,
          narrative,
          blocks: [{ type: "stats", stats: b.stats }, ...b.charts.map((c) => ({ type: "chart", ...c }))],
        }]);
        setSuggestions(b.suggested_questions);
      })
      .catch(() => {})
      .finally(() => setBriefing(false));
  }, [dataset]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => { stopSpeaking?.(); recRef.current?.stop?.(); }, []);

  const finishUpload = async (d) => {
    await cleanDataset(d.id, {
      drop_duplicates: true, numeric_strategy: "median",
      categorical_strategy: "mode", outlier_method: "iqr_clip",
    }).catch(() => {});
    setDataset({ ...d, is_cleaned: true });
    refresh();
  };

  const handleUpload = () => {
    if (!file) return;
    setBusy(true); setError("");
    uploadDataset(file).then(finishUpload)
      .catch((e) => setError(detail(e, "Couldn't read that file.")))
      .finally(() => setBusy(false));
  };

  const handleSample = (id) => {
    setBusy(true); setError("");
    loadSample(id).then(finishUpload)
      .catch((e) => setError(detail(e, "Couldn't load the sample.")))
      .finally(() => setBusy(false));
  };

  const send = async (text) => {
    const question = (text ?? input).trim();
    if (!question || busy) return;
    setInput("");
    setError("");
    setDrawer(false);
    setLibrary(false);
    setView("chat");
    setSuggestions([]);
    const history = messages
      .filter((m) => !m.lead)
      .map((m) => ({ role: m.role, content: m.text || m.narrative?.[0] || "" }));
    setMessages((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const r = await chatWithDataset(dataset.id, question === t("hi", "playbookQ") ? t("en", "playbookQ") : question, history, lang, priv, shop);
      setMessages((m) => [...m, { role: "assistant", ...r }]);
    } catch (e) {
      setError(detail(e, "Something went wrong reaching the server."));
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = () => {
    if (listening) { recRef.current?.stop(); return; }
    setError("");
    setListening(true);
    let heard = "";
    recRef.current = listen(speech, {
      onText: (txt) => { heard = txt; setInput(txt); },
      onEnd: () => { setListening(false); if (heard.trim()) send(heard); },
      onError: (e) => { setListening(false); setError(e === "not-allowed" ? "Microphone access was blocked. Allow it in the browser's address bar and try again." : "Couldn't hear that. Try again."); },
    });
  };

  const onSpeak = (id, text) => {
    if (speakingId === id) { stopSpeaking(); setSpeakingId(null); return; }
    setSpeakingId(id);
    speak(text, speech, () => setSpeakingId(null));
  };

  const shareDigest = async () => {
    try {
      const { text } = await getDigest(dataset.id);
      window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
    } catch (e) { setError(detail(e, "Couldn't build the summary.")); }
  };

  const compareWith = async (otherId) => {
    if (!otherId) return;
    const other = datasets.find((x) => String(x.id) === String(otherId));
    setBusy(true); setError(""); setDrawer(false);
    try {
      const r = await compareFiles(dataset.id, otherId);
      const lines = r.available ? [`Compared with ${other?.file_name}:`, ...r.findings] : [r.reason];
      setMessages((m) => [...m, { role: "assistant", narrative: lines, kind: "text" }]);
    } catch (e) { setError(detail(e, "Couldn't compare those files.")); }
    finally { setBusy(false); }
  };

  const handlePredict = async (msg, values) => {
    const row = {};
    for (const [k, v] of Object.entries(values)) {
      if (v === "") continue;
      row[k] = isNaN(Number(v)) ? v : Number(v);
    }
    setPredicting(true);
    try {
      const r = await predict(msg.model_id, [row]);
      const res = r.results[0];
      const value =
        msg.task === "classification"
          ? phraseOutcome(res.prediction)
          : typeof res.prediction === "number"
          ? res.prediction.toLocaleString(undefined, { maximumFractionDigits: 2 })
          : String(res.prediction);
      const lines = [`For that case: ${value}${msg.target ? ` (${msg.target})` : ""}.`];
      if (res.confidence != null && res.trust?.level !== "low") {
        lines.push(`About ${Math.round(res.confidence * 100)} out of 100 similar cases show this.`);
      }
      setMessages((m) => [
        ...m,
        {
          role: "assistant", narrative: lines, kind: "prediction",
          trust: res.trust, explanation: res.explanation, range: res.range, reliability: res.reliability, row,
          model_id: msg.model_id, features: msg.fields.map((f) => f.name), task: msg.task,
        },
      ]);
    } catch (e) {
      setError(detail(e, "Couldn't get a prediction for that."));
    } finally {
      setPredicting(false);
    }
  };

  const chips = [t(lang, "playbookQ"), ...suggestions, ...templates.filter((x) => x.available).map((x) => x.label)];
  const uniqueChips = [...new Set(chips)].slice(0, 9);

  /* ------------------------------------------------------------ start screen */
  if (step === "upload") {
    return (
      <div>
        <Ticker items={TICKER} />
        <div className="mx-auto grid max-w-[1180px] gap-12 px-5 pb-20 pt-12 sm:px-8 lg:grid-cols-[1.08fr_.92fr] lg:gap-16 lg:pt-20">
          {/* Hero */}
          <div className="animate-rise">
            <p className="eyebrow">01 — For shops that keep records</p>
            <h1 className="display mt-5 text-[46px] leading-[1.02] sm:text-[62px] lg:text-[74px]">
              Your shop's records, <em className="hl">answered</em> in plain words.
            </h1>
            <p className="mt-6 max-w-[48ch] text-[17px] leading-relaxed text-mute">{t(lang, "addBody")}</p>
            <ol className="mt-10 divide-y divide-line border-y border-line">
              {HIGHLIGHTS.map((h, i) => (
                <li key={h.title} className="grid grid-cols-[2.25rem_1fr] gap-x-4 gap-y-1 py-4 sm:grid-cols-[2.25rem_15rem_1fr]">
                  <span className="num pt-1 text-[11px] text-mute">0{i + 1}</span>
                  <span className="text-[15px] font-semibold">{h.title}</span>
                  <span className="col-start-2 text-[14px] leading-snug text-mute sm:col-start-3">{h.body}</span>
                </li>
              ))}
            </ol>
            <p className="eyebrow mt-8 flex flex-wrap gap-x-6 gap-y-1">
              <span>₹ · lakh · crore</span><span>Hindi · Hinglish · voice</span><span>Works offline</span><span>Private mode</span>
            </p>
          </div>

          {/* Upload sheet */}
          <div className="sheet animate-rise p-6 sm:p-8" style={{ animationDelay: "90ms" }}>
            <p className="eyebrow">02 — Start here</p>
            <h2 className="mt-2 text-[24px] font-semibold tracking-tight">{t(lang, "addTitle")}</h2>
            <label
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}
              className={`mt-5 flex cursor-pointer flex-col items-center justify-center rounded-[10px] border-[1.5px] border-dashed px-5 py-9 text-center transition ${
                dragging ? "border-ink bg-lime/40" : file ? "border-ink/60 bg-lime/20" : "border-ink/30 bg-bone/70 hover:border-ink hover:bg-lime/25"
              }`}
            >
              <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files[0])} className="sr-only" />
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-lime text-[#111111]">
                <Icon name={file ? "file" : "upload"} size={20} />
              </span>
              {file ? (
                <>
                  <p className="mt-3 max-w-full truncate text-[14px] font-medium">{file.name}</p>
                  <p className="num mt-0.5 text-[11.5px] text-mute">{(file.size / 1024).toFixed(0)} KB · ready to add</p>
                </>
              ) : (
                <>
                  <p className="mt-3 text-[14px] font-medium">Drop a CSV or Excel file here</p>
                  <p className="mt-0.5 text-[12px] text-mute">or click to browse · up to 50 MB</p>
                </>
              )}
            </label>
            <button onClick={handleUpload} disabled={!file || busy} className="btn btn-solid mt-4 w-full py-3.5 text-[15px]">
              {busy ? t(lang, "reading") : t(lang, "addFile")} {!busy && <Icon name="arrow" size={16} />}
            </button>
            {error && <p className="mt-3 rounded-[8px] border border-signal/30 bg-signal/[0.06] px-3 py-2 text-[13px] text-signal">{error}</p>}

            {samples.length > 0 && (
              <div className="mt-8">
                <p className="eyebrow">{t(lang, "trySample")}</p>
                <ul className="mt-3 border-t border-line">
                  {samples.map((s, i) => (
                    <li key={s.id}>
                      <button
                        onClick={() => handleSample(s.id)}
                        disabled={busy}
                        className="group -mx-2 flex w-[calc(100%+1rem)] items-center gap-4 rounded-[8px] border-b border-line px-2 py-3.5 text-left transition hover:bg-lime/25 disabled:opacity-50"
                      >
                        <span className="num w-5 text-[11px] text-mute">0{i + 1}</span>
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-bone text-ink transition group-hover:bg-lime group-hover:text-[#111111]">
                          <Icon name={SAMPLE_ICONS[s.id] || "file"} size={17} />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-[14px] font-medium leading-snug">{s.title}</span>
                          <span className="mt-0.5 block text-[12.5px] leading-snug text-mute">{s.blurb}</span>
                        </span>
                        <Icon name="arrow" size={16} className="shrink-0 -translate-x-1 opacity-0 transition group-hover:translate-x-0 group-hover:opacity-100" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!llmOk && (
              <div className="mt-7 rounded-[10px] border border-signal/35 bg-signal/[0.06] px-4 py-3">
                <p className="eyebrow flex items-center gap-2 !text-signal"><Icon name="key" size={13} /> {t(lang, "aiOff")}</p>
                <p className="mt-1.5 text-[12.5px] leading-snug text-mute">{t(lang, "aiOffHint")}</p>
              </div>
            )}

            {datasets.length > 0 && (
              <div className="mt-7">
                <p className="eyebrow mb-2.5">{t(lang, "earlier")}</p>
                <div className="flex max-h-28 flex-wrap gap-2 overflow-y-auto">
                  {[...new Map(datasets.map((d) => [d.file_name, d])).values()].map((d) => (
                    <button key={d.id} onClick={() => setDataset(d)} className="chip py-1 text-[12.5px]">
                      <Icon name="file" size={13} /> {d.file_name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------- chat */
  const dossier = (
    <Dossier
      dataset={dataset} datasets={datasets} lang={lang} setLang={setLang} priv={priv} setPriv={setPriv} llmOk={llmOk}
      toolkit={toolkit} onAsk={send} shop={shop} setShop={setShop}
      onShare={shareDigest} onDownload={() => downloadCleaned(dataset.id, dataset.file_name)}
      onCompare={compareWith} onSwitch={() => { setDrawer(false); setStep("upload"); }}
    />
  );

  let answerNo = 0;
  const libraryGroups = buildLibrary(brief?.roles, toolkit, llmOk);

  return (
    <div className="mx-auto grid h-[calc(100vh-56px)] w-full max-w-[1280px] lg:grid-cols-[292px_minmax(0,1fr)]">
      <aside className="hidden overflow-y-auto border-r border-line lg:block">{dossier}</aside>

      <section className="flex min-h-0 min-w-0 flex-col">
        <div className="flex items-center gap-3 border-b border-line px-4 py-2.5 lg:hidden">
          <LogoMark size={20} />
          <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium">{dataset.file_name}</span>
          {priv && <Tag tone="lime">{t(lang, "privateMode")}</Tag>}
          <button onClick={() => setDrawer(true)} className="btn btn-outline px-3 py-1.5 text-[12.5px]">
            <Icon name="sliders" size={14} /> {t(lang, "tools")}
          </button>
        </div>

        {/* Three ways in: the conversation, the shop at a glance, one name at a glance. */}
        <div className="flex items-center gap-1 border-b border-line px-3 sm:px-6" role="tablist">
          {[["chat", "send"], ["dashboard", "grid"], ["lookup", "search"]].map(([v, icon]) => (
            <button
              key={v} role="tab" aria-selected={view === v} onClick={() => setView(v)}
              className={`relative inline-flex items-center gap-1.5 px-3 py-2.5 text-[13px] font-medium ${view === v ? "text-ink" : "text-mute hover:text-ink"}`}
            >
              <Icon name={icon} size={13} /> {t(lang, v)}
              {view === v && <span className="absolute inset-x-3 -bottom-px h-[2px] bg-lime" />}
            </button>
          ))}
        </div>

        {view === "dashboard" && (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <Dashboard dataset={dataset} brief={brief} onAsk={send} />
          </div>
        )}
        {view === "lookup" && (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <Lookup dataset={dataset} lang={lang} onAsk={send} />
          </div>
        )}

        <div ref={scrollRef} className={`min-h-0 flex-1 overflow-y-auto ${view === "chat" ? "" : "hidden"}`}>
          <div className="mx-auto w-full max-w-[780px] space-y-8 px-5 py-8 sm:px-8">
            {priv && (
              <p className="hidden items-center gap-2 rounded-[8px] border border-ink/15 bg-lime/30 px-3.5 py-2 text-[12.5px] lg:flex">
                <Icon name="lock" size={13} /> {t(lang, "privateHint")}
              </p>
            )}

            {messages.map((m, i) => {
              if (m.role === "user") return <UserBubble key={i}>{m.text}</UserBubble>;
              answerNo += 1;
              return (
                <Answer key={i} n={answerNo} source={sourceOf(m)} lang={lang}>
                  <AssistantContent msg={m} onPredict={handlePredict} predicting={predicting} lang={lang} />
                  <AnswerActions msg={m} lang={lang} speakingId={speakingId} onSpeak={onSpeak} id={i} />
                </Answer>
              );
            })}

            {messages.length > 0 && !busy && uniqueChips.length > 0 && messages.length <= 1 && (
              <div className="animate-rise">
                <p className="eyebrow mb-3">{t(lang, "tryAsking")}</p>
                <div className="flex flex-wrap gap-2">
                  {uniqueChips.map((q) => (
                    <button key={q} onClick={() => send(q)} className="chip">{q}</button>
                  ))}
                </div>
              </div>
            )}

            {briefing && messages.length === 0 && (
              <article aria-label="Loading the briefing">
                <header className="mb-3 flex items-center gap-2.5">
                  <ThinkingMark size={18} />
                  <span className="eyebrow">{t(lang, "reading")}</span>
                  <span className="h-px flex-1 bg-line" />
                </header>
                <div className="space-y-2.5">
                  {[92, 78, 64].map((w, i) => (
                    <div key={w} className="shimmer h-3.5 rounded-full" style={{ width: `${w}%`, animationDelay: `${i * 150}ms` }} />
                  ))}
                  <div className="grid grid-cols-3 gap-3 pt-3">
                    {[0, 1, 2].map((i) => <div key={i} className="shimmer h-20 rounded-[10px]" style={{ animationDelay: `${i * 120}ms` }} />)}
                  </div>
                </div>
              </article>
            )}

            {busy && (
              <div className="flex animate-rise items-center gap-3">
                <ThinkingMark size={24} />
                <span className="eyebrow">{t(lang, "thinking")}</span>
              </div>
            )}
          </div>
        </div>

        {error && view === "chat" && (
          <div className="mx-auto w-full max-w-[780px] px-5 pb-2 sm:px-8">
            <div className="rounded-[8px] border border-signal/30 bg-signal/[0.06] px-4 py-2.5 text-[13px] text-signal">{error}</div>
          </div>
        )}

        {library && view === "chat" && <Library groups={libraryGroups} lang={lang} onAsk={send} onClose={() => setLibrary(false)} />}

        <div className={`border-t border-line bg-bone/85 px-4 pb-4 pt-3 backdrop-blur-sm sm:px-8 ${view === "chat" ? "" : "hidden"}`}>
          <div className="mx-auto w-full max-w-[780px]">
            <div
              className={`flex items-center gap-1.5 rounded-full border-[1.5px] bg-sheet py-1.5 pl-2 pr-1.5 transition ${
                listening ? "border-signal" : "border-ink/70 focus-within:border-cobalt focus-within:shadow-ring"
              }`}
            >
              <button
                onClick={() => setLibrary(!library)}
                aria-pressed={library}
                title={t(lang, "library")}
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${library ? "bg-lime text-[#111111]" : "text-mute hover:bg-ink/[0.06] hover:text-ink"}`}
              >
                <Icon name="book" size={17} />
              </button>
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder={listening ? t(lang, "listening") : t(lang, "ask")}
                className="bare min-w-0 flex-1 bg-transparent px-2 py-2 text-[15.5px] outline-none placeholder:text-ink/35"
              />
              {canListen() && (
                <button
                  onClick={toggleMic}
                  aria-label={t(lang, "speak")}
                  aria-pressed={listening}
                  title={t(lang, "speak")}
                  className={`flex h-9 w-9 items-center justify-center rounded-full ${listening ? "animate-pulseDot bg-signal text-sheet" : "text-mute hover:bg-ink/[0.06] hover:text-ink"}`}
                >
                  <Icon name="mic" size={17} />
                </button>
              )}
              <button
                onClick={() => send()}
                disabled={!input.trim() || busy}
                aria-label={t(lang, "send")}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-ink text-sheet transition hover:bg-cobalt disabled:bg-ink/10 disabled:text-ink/30"
              >
                <Icon name="up" size={18} strokeWidth={2.2} />
              </button>
            </div>
            <p className="eyebrow mt-2 hidden truncate text-center sm:block">
              <kbd className="rounded border border-line px-1 py-px">/</kbd> to type · {t(lang, "enterHint")} {dataset.file_name}
            </p>
          </div>
        </div>
      </section>

      {drawer && (
        <div className="fixed inset-0 z-30 lg:hidden" role="dialog" aria-modal="true" aria-label={t(lang, "tools")}>
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 right-0 w-[min(22rem,92vw)] animate-slide overflow-y-auto border-l border-line bg-bone shadow-lift">
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <span className="eyebrow">{t(lang, "tools")}</span>
              <button onClick={() => setDrawer(false)} className="btn btn-ghost px-2 py-1" aria-label="Close"><Icon name="x" size={16} /></button>
            </div>
            {dossier}
          </div>
        </div>
      )}
    </div>
  );
}
