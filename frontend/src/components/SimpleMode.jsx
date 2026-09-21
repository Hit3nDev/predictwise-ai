import { useEffect, useState } from "react";
import {
  uploadDataset, cleanDataset, getQuestionTemplates, askQuestion, predict, detail,
} from "../api";

/* A friendlier shell than Technical Mode's data-tool chrome: bigger type,
   more air, plain sentences instead of labels. Same tokens (ink/clay/paper)
   so it's recognisably the same product, not a different app bolted on. */

function Card({ children, className = "" }) {
  return (
    <div className={`border border-rule bg-paper p-6 ${className}`}>{children}</div>
  );
}

function BigButton({ children, ...props }) {
  return (
    <button
      {...props}
      className="w-full bg-ink px-5 py-3.5 text-[15px] font-medium text-white
                 transition-colors hover:bg-slate disabled:cursor-not-allowed disabled:bg-rule disabled:text-slate/40"
    >
      {children}
    </button>
  );
}

/* For "will this happen again" questions, the model's raw output is 0/1 (or
   True/False) by convention — meaningless to read as-is. Every template this
   maps to (purchased, churned, renewed, returned...) uses 1 = "it happened",
   so this translation is safe specifically for the repeat/classification
   template. Numeric predictions (predict_number) are shown as real numbers,
   unchanged, because there the number IS the answer. */
function phraseOutcome(value) {
  const v = String(value).trim().toLowerCase();
  if (["1", "true", "yes"].includes(v)) return "Yes";
  if (["0", "false", "no"].includes(v)) return "No";
  return String(value);
}

export default function SimpleMode({ dataset, setDataset, datasets, refresh }) {
  const [step, setStep] = useState("upload");   // upload | ask | answer
  const [file, setFile] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [formValues, setFormValues] = useState({});
  const [predictionOut, setPredictionOut] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (dataset) {
      setStep("ask");
      getQuestionTemplates(dataset.id).then(setTemplates).catch(() => {});
    }
  }, [dataset]);

  const run = async (fn, onDone) => {
    setBusy(true); setError("");
    try { onDone(await fn()); }
    catch (e) { setError(detail(e, "Something went wrong reaching the server.")); }
    finally { setBusy(false); }
  };

  const handleUpload = () => {
    if (!file) return;
    run(() => uploadDataset(file), async (d) => {
      // Clean silently with sensible defaults — a shop owner shouldn't have
      // to know what "IQR clipping" means to get a usable answer.
      await cleanDataset(d.id, {
        drop_duplicates: true,
        numeric_strategy: "median",
        categorical_strategy: "mode",
        outlier_method: "iqr_clip",
      }).catch(() => {});
      setDataset({ ...d, is_cleaned: true });
      refresh();
    });
  };

  const ask = (payload) =>
    run(() => askQuestion(dataset.id, payload), (r) => {
      setAnswer(r);
      setPredictionOut(null);
      setFormValues(Object.fromEntries(r.fields.map((f) => [f.name, ""])));
      setStep("answer");
    });

  const handlePredict = () => {
    const row = {};
    for (const [k, v] of Object.entries(formValues)) {
      if (v === "") continue;
      row[k] = isNaN(Number(v)) ? v : Number(v);
    }
    run(() => predict(answer.model_id, [row]), setPredictionOut);
  };

  return (
    <div className="mx-auto max-w-2xl px-5 py-10 md:py-16">
      {error && (
        <div className="mb-5 border border-clay/30 bg-clay/[0.04] px-4 py-3 text-[14px] text-clay">
          {error}
        </div>
      )}

      {/* ---------------------------------------------------------- upload */}
      {step === "upload" && (
        <Card>
          <h1 className="text-[22px] leading-snug tracking-tight">
            Add your business data
          </h1>
          <p className="mt-2 text-[14px] text-slate/60">
            A spreadsheet of customers, sales, or orders — anything you already
            keep in Excel or export from your billing software.
          </p>

          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={(e) => setFile(e.target.files[0])}
            className="mt-6 block w-full text-[14px] text-slate/70
                       file:mr-3 file:cursor-pointer file:border-0 file:bg-field
                       file:px-4 file:py-2.5 file:text-[13px] file:text-slate hover:file:bg-rule/60"
          />
          <div className="mt-5">
            <BigButton onClick={handleUpload} disabled={!file || busy}>
              {busy ? "Reading your file…" : "Add this file"}
            </BigButton>
          </div>

          {datasets.length > 0 && (
            <div className="mt-8 border-t border-rule pt-5">
              <p className="mb-3 text-[13px] text-slate/50">Or use something you added before:</p>
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
        </Card>
      )}

      {/* -------------------------------------------------------------- ask */}
      {step === "ask" && dataset && (
        <div className="space-y-5">
          <div>
            <p className="text-[13px] text-slate/50">Using {dataset.file_name}</p>
            <h1 className="mt-1 text-[22px] leading-snug tracking-tight">
              What do you want to know?
            </h1>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {templates.map((t) => (
              <button
                key={t.id}
                disabled={!t.available || busy}
                onClick={() => ask({ template_id: t.id })}
                className={`border p-4 text-left transition-colors ${
                  t.available
                    ? "border-rule bg-paper hover:border-ink"
                    : "border-rule/50 bg-field/50 opacity-50"
                }`}
              >
                <p className="text-[14px] font-medium">{t.label}</p>
                <p className="mt-1 text-[12px] text-slate/50">
                  {t.available ? t.hint : t.reason}
                </p>
              </button>
            ))}
          </div>

          <Card>
            <p className="mb-1 text-[13px] text-slate/60">Or type your own question</p>
            <p className="mb-3 text-[12px] text-slate/40">
              Name a column and I'll focus on it — e.g. "what affects income the most"
              or "compare sales by city".
            </p>
            <div className="flex gap-2">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && question.trim() && ask({ question })}
                placeholder="e.g. what affects income the most?"
                className="flex-1 border border-rule bg-paper px-4 py-2.5 text-[14px]"
              />
              <button
                onClick={() => ask({ question })}
                disabled={!question.trim() || busy}
                className="bg-ink px-5 text-[13px] font-medium text-white hover:bg-slate disabled:bg-rule disabled:text-slate/40"
              >
                Ask
              </button>
            </div>
          </Card>

          <button
            onClick={() => setStep("upload")}
            className="text-[13px] text-slate/50 hover:text-ink"
          >
            ← Use a different file
          </button>
        </div>
      )}

      {/* ---------------------------------------------------------- answer */}
      {step === "answer" && answer && (
        <div className="space-y-5">
          <button
            onClick={() => setStep("ask")}
            className="text-[13px] text-slate/50 hover:text-ink"
          >
            ← Ask something else
          </button>

          <Card>
            <p className="mb-4 text-[13px] uppercase tracking-wide text-slate/40">
              {answer.matched_label}
            </p>

            <div className="space-y-3">
              {answer.narrative.map((line, i) => (
                <p key={i} className="text-[16px] leading-relaxed text-slate">
                  {line}
                </p>
              ))}
            </div>

            {answer.kind === "ranking" && answer.ranking && (
              <div className="mt-6 space-y-2">
                {answer.ranking.map((row, i) => {
                  const max = answer.ranking[0].value;
                  return (
                    <div key={row.name} className="flex items-center gap-3">
                      <span className="w-6 text-[12px] text-slate/40">{i + 1}</span>
                      <span className="w-28 shrink-0 truncate text-[13px]">{row.name}</span>
                      <div className="h-3 flex-1 bg-field">
                        <div
                          className="h-3 bg-ink/70"
                          style={{ width: `${(row.value / max) * 100}%` }}
                        />
                      </div>
                      <span className="num w-16 text-right text-[12px] text-slate/55">
                        {Math.round(row.value).toLocaleString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {answer.kind === "predictable" && (
            <Card>
              <p className="mb-1 text-[14px] font-medium">Try it on a specific case</p>
              <p className="mb-4 text-[13px] text-slate/55">
                Fill in what you know — leave the rest blank.
              </p>

              <div className="space-y-4">
                {answer.fields.map((f) => (
                  <div key={f.name}>
                    <label className="mb-1 block text-[13px] text-slate/60">
                      {f.label}
                      {f.type === "number" && f.min != null && (
                        <span className="text-slate/35"> (usually {f.min}–{f.max})</span>
                      )}
                    </label>
                    {f.type === "select" ? (
                      <select
                        value={formValues[f.name] ?? ""}
                        onChange={(e) => setFormValues((v) => ({ ...v, [f.name]: e.target.value }))}
                        className="sel w-full border border-rule bg-paper px-3 py-2.5 text-[14px]"
                      >
                        <option value="">— not sure —</option>
                        {f.options.map((o) => (
                          <option key={o} value={o}>{o}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={formValues[f.name] ?? ""}
                        onChange={(e) => setFormValues((v) => ({ ...v, [f.name]: e.target.value }))}
                        placeholder={f.typical != null ? String(f.typical) : ""}
                        className="w-full border border-rule bg-paper px-3 py-2.5 text-[14px]"
                      />
                    )}
                  </div>
                ))}
              </div>

              <div className="mt-5">
                <BigButton onClick={handlePredict} disabled={busy}>
                  {busy ? "Working it out…" : "Get my answer"}
                </BigButton>
              </div>

              {predictionOut && (
                <div className="mt-6 border-t border-rule pt-5">
                  {predictionOut.results.map((r, i) => (
                    <div key={i}>
                      <p className="text-[13px] text-slate/50">
                        {answer.matched_template === "repeat"
                          ? `Will this happen (${answer.target})?`
                          : `Predicted ${answer.target}`}
                      </p>
                      <p className="num mt-1 text-[36px] leading-none text-ink">
                        {answer.matched_template === "repeat"
                          ? phraseOutcome(r.prediction)
                          : typeof r.prediction === "number"
                          ? r.prediction.toLocaleString(undefined, { maximumFractionDigits: 2 })
                          : String(r.prediction)}
                      </p>
                      {r.confidence != null && (
                        <p className="mt-2 text-[13px] text-slate/55">
                          About {Math.round(r.confidence * 100)} out of 100 similar cases show this outcome.
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
