import { useState } from "react";
import { Panel, Button, Field, Select, Readout, Empty, Notice } from "./ui";
import { MissingBars, Histogram, Heatmap, DataTable } from "./charts";

/* ---------------------------------------------------------------- 1. Data */

export function DataStage({ datasets, onUpload, onSelect, active, busy }) {
  const [file, setFile] = useState(null);

  return (
    <div className="grid gap-px bg-rule md:grid-cols-[1fr_1fr]">
      <div className="bg-paper p-5">
        <h2 className="mb-1 text-[15px] font-medium tracking-tight">Add a dataset</h2>
        <p className="mb-4 text-[13px] text-slate/55">
          CSV or Excel. Columns and types are read on upload.
        </p>

        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={(e) => setFile(e.target.files[0])}
          className="mb-4 block w-full text-[13px] text-slate/70
                     file:mr-3 file:cursor-pointer file:border file:border-slate/25
                     file:bg-paper file:px-3 file:py-1.5 file:text-[12px] file:text-slate
                     hover:file:border-ink hover:file:text-ink"
        />
        <Button onClick={() => onUpload(file)} disabled={!file || busy}>
          {busy ? "Reading…" : "Upload dataset"}
        </Button>
      </div>

      <div className="bg-paper">
        <div className="border-b border-rule px-5 py-3">
          <h2 className="text-[15px] font-medium tracking-tight">Datasets</h2>
        </div>
        {datasets.length === 0 ? (
          <p className="px-5 py-8 text-center text-[13px] text-slate/45">
            Nothing here yet. Upload a file to begin.
          </p>
        ) : (
          <ul>
            {datasets.map((d) => (
              <li key={d.id}>
                <button
                  onClick={() => onSelect(d)}
                  className={`flex w-full items-center justify-between border-b border-rule/70 px-5 py-2.5 text-left hover:bg-field ${
                    active?.id === d.id ? "bg-field" : ""
                  }`}
                >
                  <span className="num truncate text-[13px]">{d.file_name}</span>
                  <span className="num shrink-0 text-[11px] text-slate/50">
                    {d.row_count}×{d.column_count}
                    {d.is_cleaned && <span className="ml-2 text-ink">cleaned</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- 2. Clean */

export function CleanStage({ onClean, busy, result }) {
  const [opts, setOpts] = useState({
    drop_duplicates: true,
    numeric_strategy: "median",
    categorical_strategy: "mode",
    outlier_method: "none",
  });
  const set = (k, v) => setOpts((o) => ({ ...o, [k]: v }));

  return (
    <div className="space-y-px">
      <Panel title="Preprocessing" note="every step is recorded">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Missing numbers">
            <Select
              value={opts.numeric_strategy}
              onChange={(e) => set("numeric_strategy", e.target.value)}
            >
              <option value="median">Replace with median</option>
              <option value="mean">Replace with mean</option>
              <option value="zero">Replace with zero</option>
              <option value="drop">Drop those rows</option>
            </Select>
          </Field>

          <Field label="Missing text">
            <Select
              value={opts.categorical_strategy}
              onChange={(e) => set("categorical_strategy", e.target.value)}
            >
              <option value="mode">Replace with most common</option>
              <option value="constant">Replace with “Unknown”</option>
              <option value="drop">Drop those rows</option>
            </Select>
          </Field>

          <Field label="Extreme values">
            <Select
              value={opts.outlier_method}
              onChange={(e) => set("outlier_method", e.target.value)}
            >
              <option value="none">Keep as they are</option>
              <option value="iqr_clip">Cap using the IQR rule</option>
            </Select>
          </Field>
        </div>

        <label className="mt-4 flex w-fit cursor-pointer items-center gap-2 text-[13px]">
          <input
            type="checkbox"
            checked={opts.drop_duplicates}
            onChange={(e) => set("drop_duplicates", e.target.checked)}
            className="h-3.5 w-3.5 accent-[#2f7d6e]"
          />
          Remove repeated rows
        </label>

        <div className="mt-5">
          <Button onClick={() => onClean(opts)} disabled={busy}>
            {busy ? "Running…" : "Clean dataset"}
          </Button>
        </div>
      </Panel>

      {result && (
        <Panel
          title="What changed"
          note={`${result.rows_before} → ${result.rows_after} rows`}
        >
          <ol className="space-y-2">
            {result.operations.map((op, i) => (
              <li key={i} className="flex gap-3 text-[13px]">
                <span className="num shrink-0 text-slate/35">{String(i + 1).padStart(2, "0")}</span>
                <span className="text-slate/80">{op.detail}</span>
              </li>
            ))}
          </ol>
        </Panel>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- 3. Explore */

export function ExploreStage({ eda, onRun, busy }) {
  if (!eda) {
    return (
      <Panel title="Exploratory analysis">
        <Empty>Run the analysis to profile this dataset.</Empty>
        <div className="mt-4">
          <Button onClick={onRun} disabled={busy}>
            {busy ? "Analysing…" : "Analyse dataset"}
          </Button>
        </div>
      </Panel>
    );
  }

  return (
    <div className="space-y-px">
      <Panel title="Shape" note={eda.source === "cleaned" ? "cleaned data" : "raw data"}>
        <div className="grid grid-cols-2 gap-5 md:grid-cols-6">
          <Readout value={eda.row_count} label="rows" />
          <Readout value={eda.column_count} label="columns" />
          <Readout value={eda.numeric_columns} label="numeric" />
          <Readout value={eda.categorical_columns} label="text" />
          <Readout
            value={eda.total_missing}
            label="missing values"
            tone={eda.total_missing ? "clay" : "ink"}
          />
          <Readout
            value={eda.duplicate_rows}
            label="repeated rows"
            tone={eda.duplicate_rows ? "clay" : "ink"}
          />
        </div>
      </Panel>

      <Panel title="Missing values">
        <MissingBars rows={eda.missing_summary} />
      </Panel>

      {eda.histograms.length > 0 && (
        <Panel title="Distributions">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {eda.histograms.map((h) => (
              <div key={h.column}>
                <p className="num mb-2 truncate text-[12px] text-slate/60">{h.column}</p>
                <Histogram bins={h.bins} />
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Correlation" note="clay negative · green positive">
        <Heatmap columns={eda.correlation.columns} matrix={eda.correlation.matrix} />
      </Panel>

      <Panel title="Columns" flush>
        <DataTable rows={eda.columns.map((c) => ({
          column: c.name,
          type: c.dtype,
          missing: c.missing,
          unique: c.unique,
          "mean / most common": c.is_numeric ? (c.mean ?? "—") : (c.top_value ?? "—"),
          min: c.is_numeric ? (c.min ?? "—") : "—",
          max: c.is_numeric ? (c.max ?? "—") : "—",
        }))} />
      </Panel>

      <Panel title="First rows" flush>
        <DataTable rows={eda.preview} maxHeight="320px" />
      </Panel>
    </div>
  );
}
