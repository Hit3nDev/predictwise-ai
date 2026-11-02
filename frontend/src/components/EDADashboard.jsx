import { BarChart, Histogram, CorrelationHeatmap, StatCard } from "./Charts";

export default function EDADashboard({ eda }) {
  if (!eda) return null;

  return (
    <div className="space-y-8">
      {/* --- Headline stats ------------------------------------------- */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-navy">Dataset overview</h2>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
              eda.source === "cleaned"
                ? "bg-emerald-100 text-emerald-700"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {eda.source === "cleaned" ? "cleaned data" : "raw data"}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <StatCard label="Rows" value={eda.row_count} />
          <StatCard label="Columns" value={eda.column_count} />
          <StatCard label="Numeric" value={eda.numeric_columns} />
          <StatCard label="Categorical" value={eda.categorical_columns} />
          <StatCard
            label="Missing values"
            value={eda.total_missing}
            tone={eda.total_missing > 0 ? "warn" : "good"}
          />
          <StatCard
            label="Duplicate rows"
            value={eda.duplicate_rows}
            tone={eda.duplicate_rows > 0 ? "warn" : "good"}
          />
        </div>
      </section>

      {/* --- Missing values ------------------------------------------- */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-navy">Missing values by column</h2>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          {eda.missing_summary.length ? (
            <BarChart
              data={eda.missing_summary}
              labelKey="column"
              valueKey="missing_pct"
              suffix="%"
            />
          ) : (
            <p className="text-sm text-emerald-700">
              No missing values — every column is complete.
            </p>
          )}
        </div>
      </section>

      {/* --- Distributions -------------------------------------------- */}
      {eda.histograms.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-navy">Distributions</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {eda.histograms.map((h) => (
              <div key={h.column} className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="mb-3 truncate text-sm font-medium text-slate-700">{h.column}</p>
                <Histogram bins={h.bins} />
                <div className="mt-2 flex justify-between text-[10px] text-slate-400">
                  <span>{h.bins[0]?.label.split("–")[0]}</span>
                  <span>{h.bins[h.bins.length - 1]?.label.split("–")[1]}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* --- Correlations --------------------------------------------- */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-navy">Correlation matrix</h2>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <CorrelationHeatmap
            columns={eda.correlation.columns}
            matrix={eda.correlation.matrix}
          />
        </div>
      </section>

      {/* --- Column profile ------------------------------------------- */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-navy">Column profile</h2>
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2.5">Column</th>
                <th className="px-4 py-2.5">Type</th>
                <th className="px-4 py-2.5">Missing</th>
                <th className="px-4 py-2.5">Unique</th>
                <th className="px-4 py-2.5">Mean / Top</th>
                <th className="px-4 py-2.5">Min</th>
                <th className="px-4 py-2.5">Max</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {eda.columns.map((c) => (
                <tr key={c.name} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-medium text-slate-700">{c.name}</td>
                  <td className="px-4 py-2.5 text-slate-500">{c.dtype}</td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-600">
                    {c.missing}{" "}
                    {c.missing > 0 && (
                      <span className="text-amber-600">({c.missing_pct}%)</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-600">{c.unique}</td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-600">
                    {c.is_numeric ? (c.mean ?? "—") : (c.top_value ?? "—")}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-600">
                    {c.is_numeric ? (c.min ?? "—") : "—"}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-600">
                    {c.is_numeric ? (c.max ?? "—") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* --- Data preview --------------------------------------------- */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-navy">Data preview</h2>
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                {Object.keys(eda.preview[0] || {}).map((k) => (
                  <th key={k} className="whitespace-nowrap px-4 py-2.5">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {eda.preview.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50">
                  {Object.values(row).map((v, j) => (
                    <td key={j} className="whitespace-nowrap px-4 py-2 text-slate-600">
                      {String(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
