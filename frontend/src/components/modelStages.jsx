import { useState, useEffect } from "react";
import { Panel, Button, Field, Select, Readout, Empty, Notice } from "./ui";
import { ImportanceBars } from "./charts";
import Leaderboard from "./Leaderboard";

const METRIC_LABELS = {
  accuracy: "accuracy",
  f1: "f1 score",
  roc_auc: "roc auc",
  r2: "r²",
  rmse: "rmse",
  mae: "mae",
};

/* --------------------------------------------------------------- 4. Model */

export function ModelStage({ dataset, result, onTrain, busy }) {
  const [target, setTarget] = useState("");

  useEffect(() => {
    if (dataset?.columns?.length) setTarget(dataset.columns[dataset.columns.length - 1]);
  }, [dataset]);

  return (
    <div className="space-y-px">
      <Panel title="Train models" note="cross-validated selection">
        <div className="grid items-end gap-4 md:grid-cols-[2fr_auto]">
          <Field label="Column to predict">
            <Select value={target} onChange={(e) => setTarget(e.target.value)}>
              {dataset?.columns?.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
          <Button onClick={() => onTrain(target)} disabled={!target || busy}>
            {busy ? "Training…" : "Train models"}
          </Button>
        </div>
        <p className="mt-3 text-[12px] text-slate/50">
          Several algorithms are trained and compared. The one with the best
          cross-validated score is kept and scored again on data it never saw.
        </p>
      </Panel>

      {result && (
        <>
          <Panel title="Selected model" note={`predicting ${result.target}`}>
            <div className="mb-5 flex flex-wrap items-baseline gap-3">
              <span className="text-[22px] tracking-tight">{result.best_algorithm}</span>
              <span className="num text-[12px] text-slate/50">{result.task}</span>
            </div>

            <div className="grid grid-cols-2 gap-5 md:grid-cols-5">
              {Object.entries(result.best_metrics).map(([k, v]) => (
                <Readout
                  key={k}
                  value={typeof v === "number" ? v.toFixed(3) : v}
                  label={`${METRIC_LABELS[k] ?? k} · held out`}
                  tone={k === result.primary_metric ? "ink" : "plain"}
                />
              ))}
              <Readout value={result.n_train} label="rows trained on" />
              <Readout value={result.n_test} label="rows held back" />
            </div>

            {result.dropped_columns?.length > 0 && (
              <p className="mt-5 text-[12px] text-slate/55">
                Ignored as identifiers: {result.dropped_columns.join(", ")}
              </p>
            )}
          </Panel>

          <div className="border border-rule bg-paper">
            <Leaderboard result={result} />
          </div>

          <Panel title="What drives the prediction" note="permutation importance">
            <ImportanceBars items={result.feature_importance} />
            <p className="mt-4 text-[12px] text-slate/50">
              Each feature is shuffled in turn; the drop in score is how much the
              model relied on it.
            </p>
          </Panel>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- 5. Predict */

export function PredictStage({ result, onPredict, busy, output }) {
  const [values, setValues] = useState({});

  useEffect(() => {
    if (result?.features) {
      setValues(Object.fromEntries(result.features.map((f) => [f, ""])));
    }
  }, [result]);

  if (!result) {
    return (
      <Panel title="Predict">
        <Empty>Train a model first — predictions run against the selected model.</Empty>
      </Panel>
    );
  }

  const submit = () => {
    // Send numbers as numbers; leave blanks out so the model imputes them.
    const row = {};
    for (const [k, v] of Object.entries(values)) {
      if (v === "") continue;
      row[k] = isNaN(Number(v)) || v.trim() === "" ? v : Number(v);
    }
    onPredict(row);
  };

  return (
    <div className="space-y-px">
      <Panel title="Predict" note={`${result.best_algorithm} · ${result.target}`}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {result.features.map((f) => (
            <Field key={f} label={f}>
              <input
                value={values[f] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
                placeholder="—"
                className="num w-full border border-rule bg-paper px-3 py-2 text-[13px]"
              />
            </Field>
          ))}
        </div>
        <div className="mt-5">
          <Button onClick={submit} disabled={busy}>
            {busy ? "Predicting…" : "Predict"}
          </Button>
        </div>
        <p className="mt-3 text-[12px] text-slate/50">
          Blank fields are filled in with the values the model was trained on.
        </p>
      </Panel>

      {output && (
        <Panel title="Result">
          {output.results.map((r, i) => (
            <div key={i}>
              <div className="flex items-baseline gap-4">
                <span className="num text-[32px] leading-none text-ink">
                  {typeof r.prediction === "number"
                    ? Number(r.prediction).toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })
                    : String(r.prediction)}
                </span>
                <span className="text-[13px] text-slate/55">predicted {output.target}</span>
              </div>

              {r.confidence != null && (
                <p className="num mt-2 text-[12px] text-slate/60">
                  confidence {(r.confidence * 100).toFixed(1)}%
                </p>
              )}

              {r.probabilities && (
                <div className="mt-5 space-y-1.5">
                  {Object.entries(r.probabilities)
                    .sort((a, b) => b[1] - a[1])
                    .map(([cls, p]) => (
                      <div key={cls} className="flex items-center gap-3">
                        <span className="num w-24 truncate text-[12px]">{cls}</span>
                        <div className="h-3 flex-1 bg-field">
                          <div className="h-3 bg-ink/70" style={{ width: `${p * 100}%` }} />
                        </div>
                        <span className="num w-14 text-right text-[12px] text-slate/60">
                          {(p * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </Panel>
      )}
    </div>
  );
}
