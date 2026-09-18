import { useEffect, useState } from "react";
import { uploadDataset, listDatasets, cleanDataset, getEDA } from "./api";
import CleaningPanel from "./components/CleaningPanel";
import EDADashboard from "./components/EDADashboard";

const TABS = [
  { id: "upload", label: "1. Upload" },
  { id: "clean", label: "2. Clean" },
  { id: "eda", label: "3. Explore" },
];

export default function App() {
  const [tab, setTab] = useState("upload");
  const [file, setFile] = useState(null);
  const [activeDataset, setActiveDataset] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [cleanResult, setCleanResult] = useState(null);
  const [eda, setEda] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [error, setError] = useState("");

  const refreshDatasets = async () => {
    try {
      setDatasets(await listDatasets());
    } catch {
      /* backend not up yet */
    }
  };

  useEffect(() => {
    refreshDatasets();
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    setCleanResult(null);
    setEda(null);
    try {
      const data = await uploadDataset(file);
      setActiveDataset(data);
      refreshDatasets();
      setTab("clean");
    } catch (err) {
      setError(err?.response?.data?.detail || "Upload failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  const handleClean = async (options) => {
    if (!activeDataset) return;
    setCleaning(true);
    setError("");
    try {
      setCleanResult(await cleanDataset(activeDataset.id, options));
      setEda(null);
      refreshDatasets();
    } catch (err) {
      setError(err?.response?.data?.detail || "Cleaning failed.");
    } finally {
      setCleaning(false);
    }
  };

  const loadEDA = async () => {
    if (!activeDataset) return;
    setLoading(true);
    setError("");
    try {
      setEda(await getEDA(activeDataset.id, true));
      setTab("eda");
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not load EDA.");
    } finally {
      setLoading(false);
    }
  };

  const selectDataset = async (d) => {
    setActiveDataset(d);
    setCleanResult(null);
    setEda(null);
    setTab("clean");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-5">
          <h1 className="text-2xl font-bold text-navy">PredictWise AI</h1>
          <p className="text-sm text-slate-500">
            Explainable AutoML and Decision Intelligence Platform
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Step tabs */}
        <div className="mb-6 flex gap-1 rounded-lg border border-slate-200 bg-white p-1">
          {TABS.map((t) => {
            const disabled =
              (t.id === "clean" || t.id === "eda") && !activeDataset;
            return (
              <button
                key={t.id}
                onClick={() => !disabled && setTab(t.id)}
                disabled={disabled}
                className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                  tab === t.id
                    ? "bg-accent text-white"
                    : disabled
                    ? "text-slate-300"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {error && (
          <div className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {activeDataset && (
          <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
            <span className="font-medium text-slate-700">{activeDataset.file_name}</span>
            <span className="text-slate-500">
              {activeDataset.row_count} rows × {activeDataset.column_count} cols
            </span>
            {activeDataset.is_cleaned && (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                cleaned
              </span>
            )}
          </div>
        )}

        {/* --- Upload tab --- */}
        {tab === "upload" && (
          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-6">
              <h2 className="mb-1 text-lg font-semibold text-navy">Upload a dataset</h2>
              <p className="mb-4 text-sm text-slate-500">
                CSV or Excel. The file is validated and profiled on upload.
              </p>
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={(e) => setFile(e.target.files[0])}
                className="mb-4 block w-full cursor-pointer text-sm text-slate-600 file:mr-4 file:cursor-pointer
                           file:rounded-lg file:border-0 file:bg-accent file:px-4 file:py-2 file:text-white
                           hover:file:bg-navy"
              />
              <button
                onClick={handleUpload}
                disabled={!file || loading}
                className="w-full rounded-lg bg-accent py-2.5 font-medium text-white transition-colors hover:bg-navy disabled:bg-slate-300"
              >
                {loading ? "Uploading..." : "Upload & Analyze"}
              </button>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-6">
              <h2 className="mb-3 text-lg font-semibold text-navy">Your datasets</h2>
              {datasets.length === 0 ? (
                <p className="text-sm text-slate-400">Nothing uploaded yet.</p>
              ) : (
                <div className="space-y-2">
                  {datasets.map((d) => (
                    <button
                      key={d.id}
                      onClick={() => selectDataset(d)}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-4 py-2.5 text-left text-sm hover:border-accent hover:bg-slate-50"
                    >
                      <span className="font-medium text-slate-700">{d.file_name}</span>
                      <span className="text-xs text-slate-500">
                        {d.row_count} × {d.column_count}
                        {d.is_cleaned && (
                          <span className="ml-2 text-emerald-600">cleaned</span>
                        )}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* --- Clean tab --- */}
        {tab === "clean" && activeDataset && (
          <div className="space-y-5">
            <CleaningPanel
              onClean={handleClean}
              cleaning={cleaning}
              result={cleanResult}
            />
            <button
              onClick={loadEDA}
              disabled={loading}
              className="w-full rounded-lg border border-accent bg-white py-2.5 font-medium text-accent transition-colors hover:bg-accent hover:text-white disabled:opacity-50"
            >
              {loading ? "Loading..." : "Continue to exploratory analysis →"}
            </button>
          </div>
        )}

        {/* --- EDA tab --- */}
        {tab === "eda" &&
          (eda ? (
            <EDADashboard eda={eda} />
          ) : (
            <div className="rounded-xl border border-slate-200 bg-white p-8 text-center">
              <p className="mb-4 text-sm text-slate-500">
                Generate the exploratory analysis for this dataset.
              </p>
              <button
                onClick={loadEDA}
                disabled={loading}
                className="rounded-lg bg-accent px-6 py-2.5 font-medium text-white hover:bg-navy disabled:bg-slate-300"
              >
                {loading ? "Analyzing..." : "Run EDA"}
              </button>
            </div>
          ))}
      </div>
    </div>
  );
}
