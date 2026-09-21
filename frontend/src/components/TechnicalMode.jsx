import { useState } from "react";
import {
  uploadDataset, cleanDataset, getEDA, trainModels, predict, detail,
} from "../api";
import { Notice } from "./ui";
import { DataStage, CleanStage, ExploreStage } from "./stages";
import { ModelStage, PredictStage } from "./modelStages";

const STAGES = [
  { id: "data",    name: "Data",    hint: "upload a file" },
  { id: "clean",   name: "Clean",   hint: "fix gaps and repeats" },
  { id: "explore", name: "Explore", hint: "see what's in it" },
  { id: "model",   name: "Model",   hint: "train and compare" },
  { id: "predict", name: "Predict", hint: "run it on new rows" },
];

export default function TechnicalMode({ dataset, setDataset, datasets, refresh }) {
  const [stage, setStage] = useState("data");
  const [cleanResult, setCleanResult] = useState(null);
  const [eda, setEda] = useState(null);
  const [training, setTraining] = useState(null);
  const [prediction, setPrediction] = useState(null);
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
    run(() => predict(training.best_model_id, [row]), setPrediction);

  const reachable = (id) => {
    if (id === "data") return true;
    if (!dataset) return false;
    if (id === "predict") return Boolean(training);
    return true;
  };

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <nav className="shrink-0 bg-slate text-white md:w-56">
        <ol className="flex md:block">
          {STAGES.map((s, i) => {
            const on = stage === s.id;
            const ok = reachable(s.id);
            return (
              <li key={s.id} className="flex-1">
                <button
                  onClick={() => ok && setStage(s.id)}
                  disabled={!ok}
                  className={`w-full border-b border-white/10 px-5 py-3 text-left transition-colors
                    ${on ? "bg-white/[0.09]" : ok ? "hover:bg-white/[0.05]" : "opacity-30"}`}
                >
                  <span className="flex items-baseline gap-2.5">
                    <span className="num text-[11px] text-white/40">{i + 1}</span>
                    <span className="text-[14px]">{s.name}</span>
                  </span>
                  <span className="mt-0.5 hidden pl-[22px] text-[11px] text-white/40 md:block">
                    {s.hint}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        {dataset && (
          <div className="hidden px-5 py-4 md:block">
            <p className="num truncate text-[12px] text-white/70">{dataset.file_name}</p>
            <p className="num mt-0.5 text-[11px] text-white/40">
              {dataset.row_count} × {dataset.column_count}
              {dataset.is_cleaned && " · cleaned"}
            </p>
          </div>
        )}
      </nav>

      <main className="min-w-0 flex-1 p-5 md:p-8">
        <div className="mx-auto max-w-5xl space-y-5">
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
              <button
                onClick={handleEDA}
                disabled={busy}
                className="w-full border border-slate/25 py-2.5 text-[13px] hover:border-ink hover:text-ink disabled:opacity-40"
              >
                Continue to exploration
              </button>
            </>
          )}

          {stage === "explore" && dataset && (
            <>
              <ExploreStage eda={eda} onRun={handleEDA} busy={busy} />
              {eda && (
                <button
                  onClick={() => setStage("model")}
                  className="w-full border border-slate/25 py-2.5 text-[13px] hover:border-ink hover:text-ink"
                >
                  Continue to modelling
                </button>
              )}
            </>
          )}

          {stage === "model" && dataset && (
            <>
              <ModelStage dataset={dataset} result={training} onTrain={handleTrain} busy={busy} />
              {training && (
                <button
                  onClick={() => setStage("predict")}
                  className="w-full border border-slate/25 py-2.5 text-[13px] hover:border-ink hover:text-ink"
                >
                  Continue to prediction
                </button>
              )}
            </>
          )}

          {stage === "predict" && (
            <PredictStage result={training} onPredict={handlePredict} busy={busy} output={prediction} />
          )}
        </div>
      </main>
    </div>
  );
}
