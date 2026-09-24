import { useEffect, useRef, useState } from "react";
import {
  uploadDataset, cleanDataset, getQuestionTemplates, chatWithDataset, predict, detail,
} from "../api";

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

function PredictForm({ msg, onPredict, busy }) {
  const [values, setValues] = useState(Object.fromEntries((msg.fields || []).map((f) => [f.name, ""])));
  return (
    <div className="mt-4 border-t border-rule pt-3">
      <p className="mb-2 text-[12px] text-slate/50">Try it for a specific case:</p>
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
        {busy ? "Working it out…" : "Get my answer"}
      </button>
    </div>
  );
}

function AssistantContent({ msg, onPredict, predicting }) {
  return (
    <div>
      {msg.narrative.map((line, i) => (
        <p key={i} className={i > 0 ? "mt-2" : ""}>{line}</p>
      ))}
      {msg.kind === "ranking" && msg.ranking && <RankingBars rows={msg.ranking} />}
      {msg.kind === "table" && msg.table && <DataTable rows={msg.table} />}
      {msg.kind === "predictable" && msg.fields?.length > 0 && (
        <PredictForm msg={msg} onPredict={onPredict} busy={predicting} />
      )}
    </div>
  );
}

export default function SimpleMode({ dataset, setDataset, datasets, refresh }) {
  const [step, setStep] = useState("upload");
  const [file, setFile] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (dataset) {
      setStep("chat");
      setMessages([]);
      getQuestionTemplates(dataset.id).then(setTemplates).catch(() => {});
    }
  }, [dataset]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleUpload = () => {
    if (!file) return;
    setBusy(true); setError("");
    uploadDataset(file)
      .then(async (d) => {
        await cleanDataset(d.id, {
          drop_duplicates: true, numeric_strategy: "median",
          categorical_strategy: "mode", outlier_method: "iqr_clip",
        }).catch(() => {});
        setDataset({ ...d, is_cleaned: true });
        refresh();
      })
      .catch((e) => setError(detail(e, "Couldn't read that file.")))
      .finally(() => setBusy(false));
  };

  const send = async (text) => {
    const question = (text ?? input).trim();
    if (!question || busy) return;
    setInput("");
    setError("");
    const history = messages.map((m) => ({ role: m.role, content: m.text || m.narrative?.[0] || "" }));
    setMessages((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const r = await chatWithDataset(dataset.id, question, history);
      setMessages((m) => [...m, { role: "assistant", ...r }]);
    } catch (e) {
      setError(detail(e, "Something went wrong reaching the server."));
    } finally {
      setBusy(false);
    }
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
      if (res.confidence != null) {
        lines.push(`About ${Math.round(res.confidence * 100)} out of 100 similar cases show this.`);
      }
      setMessages((m) => [...m, { role: "assistant", narrative: lines, kind: "text" }]);
    } catch (e) {
      setError(detail(e, "Couldn't get a prediction for that."));
    } finally {
      setPredicting(false);
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-49px)] max-w-2xl flex-col">
      {step === "upload" && (
        <div className="flex flex-1 items-start justify-center px-5 py-16">
          <div className="w-full border border-rule bg-paper p-6">
            <h1 className="text-[22px] leading-snug tracking-tight">Add your business data</h1>
            <p className="mt-2 text-[14px] text-slate/60">
              A spreadsheet of customers, sales, or orders. Once it's in, just ask questions about it.
            </p>
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
              {busy ? "Reading your file…" : "Add this file"}
            </button>
            {error && <p className="mt-3 text-[13px] text-clay">{error}</p>}

            {datasets.length > 0 && (
              <div className="mt-8 border-t border-rule pt-5">
                <p className="mb-3 text-[13px] text-slate/50">Or continue with something you added before:</p>
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
          <div className="flex items-center justify-between border-b border-rule px-5 py-2.5">
            <span className="text-[12px] text-slate/50">
              Chatting about <span className="text-slate">{dataset.file_name}</span>
            </span>
            <button onClick={() => setStep("upload")} className="text-[12px] text-slate/50 hover:text-ink">
              Switch file
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
            {messages.length === 0 && (
              <div>
                <p className="mb-3 text-[14px] text-slate/60">
                  Ask anything about this data — a count, an average, what affects something,
                  or a prediction. Or start with one of these:
                </p>
                <div className="flex flex-wrap gap-2">
                  {templates.filter((t) => t.available).map((t) => (
                    <button
                      key={t.id}
                      onClick={() => send(t.label)}
                      className="border border-rule bg-paper px-3 py-1.5 text-[13px] hover:border-ink hover:text-ink"
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <Bubble key={i} role={m.role}>
                {m.role === "user" ? m.text : (
                  <AssistantContent msg={m} onPredict={handlePredict} predicting={predicting} />
                )}
              </Bubble>
            ))}

            {busy && (
              <Bubble role="assistant">
                <span className="text-slate/40">Thinking…</span>
              </Bubble>
            )}
          </div>

          {error && <div className="mx-5 mb-2 border border-clay/30 bg-clay/[0.04] px-3 py-2 text-[13px] text-clay">{error}</div>}

          <div className="flex gap-2 border-t border-rule p-4">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask about your data…"
              className="flex-1 border border-rule bg-paper px-4 py-2.5 text-[14px]"
            />
            <button
              onClick={() => send()}
              disabled={!input.trim() || busy}
              className="bg-ink px-5 text-[13px] font-medium text-white hover:bg-slate disabled:bg-rule disabled:text-slate/40"
            >
              Send
            </button>
          </div>
        </>
      )}
    </div>
  );
}
