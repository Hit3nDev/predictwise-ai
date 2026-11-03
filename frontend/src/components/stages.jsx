import { useState } from "react";
import { Panel, Button, Field, Select, Readout, Empty, Tag } from "./ui";
import { Icon } from "./icons";
import { MissingBars, Histogram, Heatmap, DataTable } from "./Charts";

/* ---------------------------------------------------------------- 1. Data */

export function DataStage({ datasets, onUpload, onSelect, active, busy }) {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div className="grid animate-rise gap-5 md:grid-cols-2">
      <Panel title="Add a dataset" note="csv · xlsx · xls">
        <label
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-[10px] border-[1.5px] border-dashed px-5 py-9 text-center transition ${
            dragging ? "border-ink bg-lime/40" : file ? "border-ink/60 bg-lime/20" : "border-ink/30 bg-bone/70 hover:border-ink hover:bg-lime/25"
          }`}
        >
          <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files[0])} className="sr-only" />
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-lime text-[#111111]">
            <Icon name={file ? "file" : "upload"} size={18} />
          </span>
          {file ? (
            <p className="mt-3 max-w-full truncate text-[13.5px] font-medium">{file.name}</p>
          ) : (
            <>
              <p className="mt-3 text-[13.5px] font-medium">Drop a CSV or Excel file here</p>
              <p className="mt-0.5 text-[12px] text-mute">Columns and types are read on upload.</p>
            </>
          )}
        </label>
        <Button className="mt-4 w-full" onClick={() => onUpload(file)} disabled={!file || busy}>
          {busy ? "Reading…" : "Upload dataset"}
        </Button>
      </Panel>

      <Panel title="Datasets" note={`${datasets.length} on file`} flush>
        {datasets.length === 0 ? (
          <div className="p-5"><Empty>Nothing here yet. Upload a file to begin.</Empty></div>
        ) : (
          <ul className="max-h-[380px] overflow-y-auto">
            {datasets.map((d) => {
              const on = active?.id === d.id;
              return (
                <li key={d.id}>
                  <button
                    onClick={() => onSelect(d)}
                    className={`flex w-full items-center gap-3 border-b border-line px-5 py-3 text-left hover:bg-bone ${on ? "bg-lime/30" : ""}`}
                  >
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${on ? "bg-ink" : "bg-line"}`} />
                    <span className="min-w-0 flex-1 truncate text-[13.5px]">{d.file_name}</span>
                    <span className="num shrink-0 text-[11px] text-mute">{d.row_count}×{d.column_count}</span>
                    {d.is_cleaned && <Tag>cleaned</Tag>}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
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
    <div className="space-y-5">
      <Panel title="Preprocessing" note="every step is recorded">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Missing numbers">
            <Select value={opts.numeric_strategy} onChange={(e) => set("numeric_strategy", e.target.value)}>
              <option value="median">Replace with median</option>
              <option value="mean">Replace with mean</option>
              <option value="zero">Replace with zero</option>
              <option value="drop">Drop those rows</option>
            </Select>
          </Field>

          <Field label="Missing text">
            <Select value={opts.categorical_strategy} onChange={(e) => set("categorical_strategy", e.target.value)}>
              <option value="mode">Replace with most common</option>
              <option value="constant">Replace with “Unknown”</option>
              <option value="drop">Drop those rows</option>
            </Select>
          </Field>

          <Field label="Extreme values">
            <Select value={opts.outlier_method} onChange={(e) => set("outlier_method", e.target.value)}>
              <option value="none">Keep as they are</option>
              <option value="iqr_clip">Cap using the IQR rule</option>
            </Select>
          </Field>
        </div>

        <label className="mt-5 flex w-fit cursor-pointer items-center gap-2.5 text-[13.5px]">
          <input
            type="checkbox"
            checked={opts.drop_duplicates}
            onChange={(e) => set("drop_duplicates", e.target.checked)}
            className="h-4 w-4 accent-[rgb(var(--cobalt))]"
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
        <Panel title="What changed" note={`${result.rows_before} → ${result.rows_after} rows`}>
          <ol className="divide-y divide-line">
            {result.operations.map((op, i) => (
              <li key={i} className="flex gap-4 py-2.5 text-[13.5px] first:pt-0 last:pb-0">
                <span className="num shrink-0 text-[11px] text-mute">{String(i + 1).padStart(2, "0")}</span>
                <span>{op.detail}</span>
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
    <div className="space-y-5">
      <Panel title="Shape" note={eda.source === "cleaned" ? "cleaned data" : "raw data"}>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-6">
          <Readout value={eda.row_count.toLocaleString("en-IN")} label="rows" />
          <Readout value={eda.column_count} label="columns" />
          <Readout value={eda.numeric_columns} label="numeric" />
          <Readout value={eda.categorical_columns} label="text" />
          <Readout value={eda.total_missing} label="missing values" tone={eda.total_missing ? "warn" : "good"} />
          <Readout value={eda.duplicate_rows} label="repeated rows" tone={eda.duplicate_rows ? "warn" : "good"} />
        </div>
      </Panel>

      <Panel title="Missing values">
        <MissingBars rows={eda.missing_summary} />
      </Panel>

      {eda.histograms.length > 0 && (
        <Panel title="Distributions">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {eda.histograms.map((h) => (
              <div key={h.column} className="rounded-[10px] border border-line p-3">
                <p className="num mb-3 truncate text-[12px] text-mute">{h.column}</p>
                <Histogram bins={h.bins} />
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Correlation" note="red negative · cobalt positive">
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
