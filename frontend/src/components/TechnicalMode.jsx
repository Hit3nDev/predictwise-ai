import { useState } from "react";
import {
  uploadDataset, cleanDataset, getEDA, trainModels, predict, detail,
} from "../api";
import { Button, Notice } from "./ui";
import { Icon } from "./icons";
import { DataStage, CleanStage, ExploreStage } from "./stages";
import { ModelStage, PredictStage, AuditStage } from "./modelStages";

const STAGES = [
  { id: "data",    name: "Data",    hint: "Upload a file, or pick one already on file." },
  { id: "clean",   name: "Clean",   hint: "Fill gaps, drop repeats, cap extreme values. Every step is logged." },
  { id: "explore", name: "Explore", hint: "Shape, missing values, distributions and correlations." },
  { id: "model",   name: "Model",   hint: "Train several algorithms and compare them honestly." },
  { id: "predict", name: "Predict", hint: "Run the selected model on a new row and see why." },
  { id: "audit",   name: "Audit",   hint: "Fairness across groups, drift in the inputs, a printable report." },
];

export default function TechnicalMode({ dataset, setDataset, datasets, refresh }) {
  const [stage, setStage] = useState("data");
  const [cleanResult, setCleanResult] = useState(null);
  const [eda, setEda] = useState(null);
  const [training, setTraining] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [predCount, setPredCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (fn, onDone) => {
    setBusy(true); setError("");
    try { onDone(await fn()); }
    catch (e) { setError(detail(e, "The server didn't respond. Is the backend running?")); }
    finally { setBusy(false); }
  };

  const resetDownstream = () => {
    setCleanResult(null); setEda(null); setTraining(null); setPrediction(null);
  };

  const handleUpload = (file) =>
    file && run(() => uploadDataset(file), (d) => {
      setDataset(d); resetDownstream(); refresh(); setStage("clean");
    });

  const handleSelect = (d) => { setDataset(d); resetDownstream(); setStage("clean"); };

  const handleClean = (opts) =>
    run(() => cleanDataset(dataset.id, opts), (r) => {
      setCleanResult(r); setEda(null); refresh();
    });

  const handleEDA = () =>
    run(() => getEDA(dataset.id, true), (r) => { setEda(r); setStage("explore"); });

  const handleTrain = (target) =>
    run(() => trainModels(dataset.id, { target }), (r) => {
      setTraining(r); setPrediction(null); setStage("model");
    });

  const handlePredict = (row) =>
    run(() => predict(training.best_model_id, [row]), (r) => {
      setPrediction(r); setPredCount((n) => n + 1);
    });

  const reachable = (id) => {
    if (id === "data") return true;
    if (!dataset) return false;
    if (id === "predict" || id === "audit") return Boolean(training);
    return true;
  };

  const idx = STAGES.findIndex((x) => x.id === stage);
  const cur = STAGES[idx];
  const next = (label, onClick) => (
    <div className="flex justify-end">
      <Button onClick={onClick} disabled={busy}>{label} <Icon name="arrow" size={15} /></Button>
    </div>
  );

  return (
    <div className="flex min-h-[calc(100vh-56px)] flex-col md:flex-row">
      <nav className="shrink-0 border-line bg-rail text-railink md:w-[264px] md:border-r">
        <p className="eyebrow hidden px-7 pb-3 pt-7 !text-railink/40 md:block">Pipeline</p>
        <ol className="flex overflow-x-auto px-2 py-2 md:block md:px-4 md:py-0">
          {STAGES.map((s, i) => {
            const on = stage === s.id;
            const ok = reachable(s.id);
            const done = idx > i && ok;
            return (
              <li key={s.id} className="shrink-0 md:shrink">
                <button
                  onClick={() => ok && setStage(s.id)}
                  disabled={!ok}
                  className={`relative flex w-full items-center gap-3.5 rounded-[10px] px-3 py-2.5 text-left transition ${
                    on ? "bg-railink/[0.07]" : ok ? "hover:bg-railink/[0.04]" : "cursor-not-allowed opacity-30"
                  }`}
                >
                  <span className={`num flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] ${
                    on ? "bg-lime text-[#111111]" : done ? "bg-railink text-rail" : "border border-railink/25 text-railink/60"
                  }`}>
                    {done ? <Icon name="check" size={12} strokeWidth={2.6} /> : String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0">
                    <span className={`block text-[14px] font-medium ${on ? "text-lime" : "text-railink/85"}`}>{s.name}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        {dataset && (
          <div className="mx-4 mb-7 mt-6 hidden rounded-[10px] border border-railink/10 p-4 md:block">
            <p className="eyebrow !text-railink/40">Active dataset</p>
            <p className="mt-1.5 truncate text-[13px] text-railink/90" title={dataset.file_name}>{dataset.file_name}</p>
            <p className="num mt-1 text-[11px] text-railink/45">
              {dataset.row_count.toLocaleString("en-IN")} × {dataset.column_count}
              {dataset.is_cleaned && <span className="ml-2 rounded-full bg-lime px-1.5 py-px text-[9.5px] uppercase tracking-wider text-[#111111]">cleaned</span>}
            </p>
          </div>
        )}
      </nav>

      <main className="min-w-0 flex-1 px-5 py-7 md:px-10 md:py-10">
        <div className="mx-auto max-w-[1040px]">
          <div className="mb-7 flex items-end justify-between gap-6 border-b border-line pb-5">
            <div>
              <p className="eyebrow">Stage {String(idx + 1).padStart(2, "0")} / {String(STAGES.length).padStart(2, "0")}</p>
              <h1 className="display mt-2 text-[34px] leading-none sm:text-[40px]" style={{ fontVariationSettings: '"SOFT" 30, "WONK" 0' }}>{cur.name}</h1>
            </div>
            <p className="hidden max-w-[30ch] text-right text-[13px] leading-snug text-mute sm:block">{cur.hint}</p>
          </div>

          <div className="space-y-5">
            {error && <Notice>{error}</Notice>}

            {stage === "data" && (
              <DataStage
                datasets={datasets}
                active={dataset}
                onUpload={handleUpload}
                onSelect={handleSelect}
                busy={busy}
              />
            )}

            {stage === "clean" && dataset && (
              <>
                <CleanStage onClean={handleClean} busy={busy} result={cleanResult} />
                {next("Continue to exploration", handleEDA)}
              </>
            )}

            {stage === "explore" && dataset && (
              <>
                <ExploreStage eda={eda} onRun={handleEDA} busy={busy} />
                {eda && next("Continue to modelling", () => setStage("model"))}
              </>
            )}

            {stage === "model" && dataset && (
              <>
                <ModelStage dataset={dataset} result={training} onTrain={handleTrain} busy={busy} />
                {training && next("Continue to prediction", () => setStage("predict"))}
              </>
            )}

            {stage === "predict" && (
              <PredictStage result={training} onPredict={handlePredict} busy={busy} output={prediction} />
            )}

            {stage === "audit" && <AuditStage result={training} predictionCount={predCount} />}
          </div>
        </div>
      </main>
    </div>
  );
}
