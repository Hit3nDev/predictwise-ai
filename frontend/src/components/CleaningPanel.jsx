import { useState } from "react";

const SELECT_CLASS =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus:border-accent focus:outline-none";

export default function CleaningPanel({ onClean, cleaning, result }) {
  const [options, setOptions] = useState({
    drop_duplicates: true,
    numeric_strategy: "median",
    categorical_strategy: "mode",
    outlier_method: "none",
  });

  const set = (key, value) => setOptions((o) => ({ ...o, [key]: value }));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="mb-1 text-lg font-semibold text-navy">Data cleaning</h2>
      <p className="mb-4 text-sm text-slate-500">
        Configure the preprocessing pipeline. Every operation applied is logged.
      </p>

      <div className="grid gap-4 md:grid-cols-3">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-600">
            Missing numeric values
          </label>
          <select
            className={SELECT_CLASS}
            value={options.numeric_strategy}
            onChange={(e) => set("numeric_strategy", e.target.value)}
          >
            <option value="median">Fill with median</option>
            <option value="mean">Fill with mean</option>
            <option value="zero">Fill with zero</option>
            <option value="drop">Drop those rows</option>
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-600">
            Missing categorical values
          </label>
          <select
            className={SELECT_CLASS}
            value={options.categorical_strategy}
            onChange={(e) => set("categorical_strategy", e.target.value)}
          >
            <option value="mode">Fill with most frequent</option>
            <option value="constant">Fill with "Unknown"</option>
            <option value="drop">Drop those rows</option>
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-slate-600">
            Outlier handling
          </label>
          <select
            className={SELECT_CLASS}
            value={options.outlier_method}
            onChange={(e) => set("outlier_method", e.target.value)}
          >
            <option value="none">Leave as-is</option>
            <option value="iqr_clip">Clip using IQR rule</option>
          </select>
        </div>
      </div>

      <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={options.drop_duplicates}
          onChange={(e) => set("drop_duplicates", e.target.checked)}
          className="h-4 w-4 rounded border-slate-300 accent-[#2B6CB0]"
        />
        Remove duplicate rows
      </label>

      <button
        onClick={() => onClean(options)}
        disabled={cleaning}
        className="mt-5 w-full rounded-lg bg-accent py-2.5 font-medium text-white transition-colors hover:bg-navy disabled:bg-slate-300"
      >
        {cleaning ? "Cleaning..." : "Run cleaning pipeline"}
      </button>

      {result && (
        <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="mb-2 text-sm font-medium text-slate-700">
            {result.rows_before} → {result.rows_after} rows
            <span className="ml-2 font-normal text-slate-500">
              ({result.operations.length} operation
              {result.operations.length === 1 ? "" : "s"} applied)
            </span>
          </p>
          <ul className="space-y-1.5">
            {result.operations.map((op, i) => (
              <li key={i} className="flex gap-2 text-xs text-slate-600">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                <span>
                  <span className="font-mono text-slate-500">{op.operation}</span> — {op.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
