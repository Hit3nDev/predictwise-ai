import { useEffect, useRef, useState } from "react";
import {
  uploadDataset, cleanDataset, getQuestionTemplates, chatWithDataset, predict, detail,
  listSamples, loadSample, getBriefing, downloadCleaned, llmStatus, getDigest, compareFiles, getToolkit,
} from "../api";
import { TrustNote, Track, Contributions, WhatIf, FairnessPanel, ReportLinks } from "./trust";
import { Blocks, BatchScore, Levers } from "./blocks";
import { LANGS, t } from "../i18n";
import { canListen, canSpeak, listen, speak, stopSpeaking } from "./voice";

/* A real chat over the dataset. Template cards are just quick-start prompts
   shown once, before the first message — after that it's a normal
   conversation: type anything, get an answer, keep going. */

function Bubble({ role, children }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] px-4 py-3 text-[15px] leading-relaxed ${
          isUser ? "bg-ink text-white" : "border border-rule bg-paper text-slate"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

function RankingBars({ rows }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.value)));
  return (
    <div className="mt-3 space-y-2">
      {rows.map((row, i) => (
        <div key={row.name} className="flex items-center gap-3">
          <span className="w-5 text-[11px] text-slate/40">{i + 1}</span>
          <span className="w-24 shrink-0 truncate text-[13px]">{row.name}</span>
          <div className="h-3 flex-1 bg-field">
            <div className="h-3 bg-ink/70" style={{ width: `${(Math.abs(row.value) / max) * 100}%` }} />
          </div>
          <span className="num w-16 text-right text-[12px] text-slate/55">
            {Math.round(row.value).toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ rows }) {
  if (!rows?.length) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="mt-3 overflow-x-auto border border-rule">
      <table className="w-full text-left text-[12px]">
        <thead className="bg-field">
          <tr>{cols.map((c) => <th key={c} className="num whitespace-nowrap px-3 py-1.5 font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-rule/60">
              {cols.map((c) => <td key={c} className="num whitespace-nowrap px-3 py-1.5">{String(r[c])}</td>)}
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
    <div className="mt-4 border-t border-rule pt-3">
      <p className="mb-2 text-[12px] text-slate/50">{t(lang, "tryCase")}</p>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {msg.fields.map((f) => (
          <div key={f.name}>
            <label className="mb-1 block text-[12px] text-slate/55">
              {f.label}
              {f.type === "number" && f.min != null && (
                <span className="text-slate/35"> ({f.min}–{f.max})</span>
              )}
            </label>
            {f.type === "select" ? (
              <select
                value={values[f.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                className="sel w-full border border-rule bg-paper px-2.5 py-1.5 text-[13px]"
              >
                <option value="">—</option>
                {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input
                value={values[f.name] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                placeholder={f.typical != null ? String(f.typical) : ""}
                className="w-full border border-rule bg-paper px-2.5 py-1.5 text-[13px]"
              />
            )}
          </div>
        ))}
      </div>
      <button
        onClick={() => onPredict(msg, values)}
        disabled={busy}
        className="mt-3 bg-ink px-4 py-2 text-[13px] font-medium text-white hover:bg-slate disabled:bg-rule disabled:text-slate/40"
      >
        {busy ? t(lang, "working") : t(lang, "getAnswer")}
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

function ToolkitBar({ toolkit, lang, onAsk, shop, setShop, open, setOpen }) {
  const tools = TOOLKIT.filter((x) => toolkit?.[x.id]?.available);
  if (!tools.length) return null;
  return (
    <div className="border-b border-rule px-5 py-2">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="text-[13px] font-medium text-ink hover:underline underline-offset-2">
        {t(lang, "toolkit")} <span className="num text-slate/40">{tools.length} {open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="mt-2 pb-1">
          <div className="flex flex-wrap gap-1.5">
            {tools.map((x) => (
              <button
                key={x.key} onClick={() => onAsk(x.q)}
                className={`border px-2.5 py-1 text-left text-[12.5px] hover:border-ink hover:text-ink ${x.msg ? "border-ink/30 bg-ink/[0.04]" : "border-rule bg-paper"}`}
              >
                {t(lang, x.key)}
              </button>
            ))}
          </div>
          <label className="mt-2 block text-[11.5px] text-slate/50">
            {t(lang, "shopName")}
            <input
              value={shop} onChange={(e) => setShop(e.target.value)} maxLength={60}
              className="mt-0.5 block w-full max-w-xs border border-rule bg-paper px-2 py-1 text-[13px] text-slate"
            />
          </label>
        </div>
      )}
    </div>
  );
}

function Fold({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mt-3 border-t border-rule pt-2.5">
      <button onClick={() => setOpen(!open)} className="text-[13px] text-ink hover:underline underline-offset-2">
        {label} <span className="num text-slate/40">{open ? "−" : "+"}</span>
      </button>
      {open && children}
    </div>
  );
}

function Toolbar({ msg, lang, speakingId, onSpeak, id }) {
  const playbook = msg.blocks?.find((b) => b.type === "playbook");
  const text = [...msg.narrative, ...(playbook ? playbook.items.map((i, n) => `${n + 1}. ${i.title}. ${i.detail}`) : [])].join(playbook ? "\n" : " ");
  const wa = `https://wa.me/?text=${encodeURIComponent(text + "\n\n(PredictWise)")}`;
  const link = "text-[12px] text-slate/45 hover:text-ink";
  return (
    <div className="mt-3 flex gap-4">
      {canSpeak() && (
        <button className={link} onClick={() => onSpeak(id, text)}>
          {speakingId === id ? t(lang, "stop") : t(lang, "listen")}
        </button>
      )}
      <a className={link} href={wa} target="_blank" rel="noreferrer">{t(lang, "share")}</a>
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

function loadLang() {
  try { return localStorage.getItem("pw-lang") || "en"; } catch { return "en"; }
}

export default function SimpleMode({ dataset, setDataset, datasets, refresh }) {
  const [step, setStep] = useState("upload");
  const [file, setFile] = useState(null);
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
  const [tkOpen, setTkOpen] = useState(true);
  const [shop, setShopState] = useState(() => { try { return localStorage.getItem("pw-shop") || ""; } catch { return ""; } });
  const setShop = (v) => { setShopState(v); try { localStorage.setItem("pw-shop", v); } catch { /* storage blocked */ } };
  const scrollRef = useRef(null);
  const recRef = useRef(null);

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
    setMessages([]);
    setSuggestions([]);
    getQuestionTemplates(dataset.id).then(setTemplates).catch(() => {});
    setToolkit(null);
    setTkOpen(true);
    getToolkit(dataset.id).then(setToolkit).catch(() => {});
    // The first thing you see is what the data says, before you ask anything.
    getBriefing(dataset.id)
      .then((b) => {
        const narrative = [...b.headline];
        if (b.quality.issues.length) narrative.push(b.quality.issues[0]);
        setMessages([{
          role: "assistant", kind: "briefing", source: "analytics", lead: true,
          narrative,
          blocks: [{ type: "stats", stats: b.stats }, ...b.charts.map((c) => ({ type: "chart", ...c }))],
        }]);
        setSuggestions(b.suggested_questions);
      })
      .catch(() => {});
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
    setTkOpen(false);
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
    setBusy(true); setError("");
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

  return (
    <div className="mx-auto flex h-[calc(100vh-49px)] max-w-2xl flex-col">
      {step === "upload" && (
        <div className="flex flex-1 items-start justify-center overflow-y-auto px-5 py-12">
          <div className="w-full border border-rule bg-paper p-6">
            <h1 className="text-[22px] leading-snug tracking-tight">{t(lang, "addTitle")}</h1>
            <p className="mt-2 text-[14px] text-slate/60">{t(lang, "addBody")}</p>
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => setFile(e.target.files[0])}
              className="mt-6 block w-full text-[14px] text-slate/70
                         file:mr-3 file:cursor-pointer file:border-0 file:bg-field
                         file:px-4 file:py-2.5 file:text-[13px] file:text-slate hover:file:bg-rule/60"
            />
            <button
              onClick={handleUpload}
              disabled={!file || busy}
              className="mt-5 w-full bg-ink px-5 py-3 text-[15px] font-medium text-white
                         hover:bg-slate disabled:cursor-not-allowed disabled:bg-rule disabled:text-slate/40"
            >
              {busy ? t(lang, "reading") : t(lang, "addFile")}
            </button>
            {error && <p className="mt-3 text-[13px] text-clay">{error}</p>}

            {samples.length > 0 && (
              <div className="mt-8 border-t border-rule pt-5">
                <p className="mb-3 text-[13px] text-slate/50">{t(lang, "trySample")}</p>
                <div className="space-y-1.5">
                  {samples.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => handleSample(s.id)}
                      disabled={busy}
                      className="block w-full border border-rule px-4 py-2.5 text-left hover:border-ink disabled:opacity-50"
                    >
                      <span className="block text-[13.5px]">{s.title}</span>
                      <span className="block text-[12px] text-slate/50">{s.blurb}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {datasets.length > 0 && (
              <div className="mt-8 border-t border-rule pt-5">
                <p className="mb-3 text-[13px] text-slate/50">{t(lang, "earlier")}</p>
                <div className="space-y-1.5">
                  {datasets.map((d) => (
                    <button
                      key={d.id}
                      onClick={() => setDataset(d)}
                      className="block w-full border border-rule px-4 py-2.5 text-left text-[13px] hover:border-ink hover:text-ink"
                    >
                      {d.file_name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {step === "chat" && dataset && (
        <>
          <div className="flex flex-col gap-1.5 border-b border-rule px-5 py-2.5 [&_button]:whitespace-nowrap [&_select]:whitespace-nowrap">
            <span className="text-[12px] text-slate/50">
              {t(lang, "chattingAbout")} <span className="text-slate">{dataset.file_name}</span>
            </span>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              <div className="flex border border-rule" role="group" aria-label="Language">
                {LANGS.map((l) => (
                  <button
                    key={l.id}
                    onClick={() => setLang(l.id)}
                    className={`px-2 py-0.5 text-[11.5px] ${lang === l.id ? "bg-slate text-white" : "text-slate/55 hover:text-slate"}`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setPriv(!priv)}
                title={t(lang, "privateHint")}
                aria-pressed={priv}
                className={`border px-2 py-0.5 text-[11.5px] ${priv ? "border-ink bg-ink text-white" : "border-rule text-slate/55 hover:text-slate"}`}
              >
                {t(lang, "privateMode")}
              </button>
              <button onClick={shareDigest} className="text-[12px] text-slate/50 hover:text-ink">{t(lang, "shareSummary")}</button>
              {datasets.filter((x) => x.id !== dataset.id).length > 0 && (
                <select
                  value="" onChange={(e) => compareWith(e.target.value)} aria-label={t(lang, "compareWith")}
                  className="sel max-w-[11rem] border border-rule bg-paper px-1.5 py-0.5 text-[11.5px] text-slate/60"
                >
                  <option value="">{t(lang, "compareWith")}</option>
                  {datasets.filter((x) => x.id !== dataset.id).map((x) => <option key={x.id} value={x.id}>{x.file_name}</option>)}
                </select>
              )}
              <button onClick={() => downloadCleaned(dataset.id, dataset.file_name)} className="text-[12px] text-slate/50 hover:text-ink">
                {t(lang, "download")}
              </button>
              <button onClick={() => setStep("upload")} className="text-[12px] text-slate/50 hover:text-ink">
                {t(lang, "switchFile")}
              </button>
            </div>
          </div>
          <ToolkitBar toolkit={toolkit} lang={lang} onAsk={send} shop={shop} setShop={setShop} open={tkOpen} setOpen={setTkOpen} />
          {priv && (
            <p className="border-b border-rule bg-field px-5 py-1.5 text-[12px] text-slate/60">{t(lang, "privateHint")}</p>
          )}
          {lang !== "en" && !llmOk && !priv && (
            <p className="border-b border-rule bg-field px-5 py-1.5 text-[12px] text-slate/60">{t(lang, "hindiNote")}</p>
          )}

          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
            {messages.map((m, i) => (
              <Bubble key={i} role={m.role}>
                {m.role === "user" ? m.text : (
                  <>
                    {m.lead && <p className="mb-2 text-[12px] text-slate/45">{t(lang, "hello")}</p>}
                    <AssistantContent msg={m} onPredict={handlePredict} predicting={predicting} lang={lang} />
                    <Toolbar msg={m} lang={lang} speakingId={speakingId} onSpeak={onSpeak} id={i} />
                  </>
                )}
              </Bubble>
            ))}

            {messages.length > 0 && !busy && uniqueChips.length > 0 && messages.length <= 1 && (
              <div>
                <p className="mb-2 text-[13px] text-slate/55">{t(lang, "tryAsking")}</p>
                <div className="flex flex-wrap gap-2">
                  {uniqueChips.map((q) => (
                    <button
                      key={q}
                      onClick={() => send(q)}
                      className="border border-rule bg-paper px-3 py-1.5 text-left text-[13px] hover:border-ink hover:text-ink"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {busy && (
              <Bubble role="assistant">
                <span className="text-slate/40">{t(lang, "thinking")}</span>
              </Bubble>
            )}
          </div>

          {error && <div className="mx-5 mb-2 border border-clay/30 bg-clay/[0.04] px-3 py-2 text-[13px] text-clay">{error}</div>}

          <div className="flex gap-2 border-t border-rule p-4">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder={listening ? t(lang, "listening") : t(lang, "ask")}
              className="flex-1 border border-rule bg-paper px-4 py-2.5 text-[14px]"
            />
            {canListen() && (
              <button
                onClick={toggleMic}
                aria-label={t(lang, "speak")}
                aria-pressed={listening}
                className={`border px-3 text-[13px] ${listening ? "border-clay bg-clay text-white" : "border-rule bg-paper text-slate/70 hover:border-ink hover:text-ink"}`}
              >
                {listening ? "●" : t(lang, "speak")}
              </button>
            )}
            <button
              onClick={() => send()}
              disabled={!input.trim() || busy}
              className="bg-ink px-5 text-[13px] font-medium text-white hover:bg-slate disabled:bg-rule disabled:text-slate/40"
            >
              {t(lang, "send")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
