import { useEffect, useState } from "react";
import { uploadDataset, listDatasets } from "./api";

export default function App() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refreshDatasets = async () => {
    try {
      const data = await listDatasets();
      setDatasets(data);
    } catch {
      // backend not reachable yet — ignore on initial load
    }
  };

  useEffect(() => {
    refreshDatasets();
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await uploadDataset(file);
      setResult(data);
      refreshDatasets();
    } catch (err) {
      setError(err?.response?.data?.detail || "Upload failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center py-16 px-4">
      <div className="w-full max-w-xl">
        <h1 className="text-3xl font-bold text-navy mb-1">PredictWise AI</h1>
        <p className="text-slate-500 mb-8">
          Upload a CSV or Excel file to get a quick profile of your dataset.
        </p>

        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Dataset file (.csv, .xlsx)
          </label>
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={(e) => setFile(e.target.files[0])}
            className="block w-full text-sm text-slate-600 mb-4 file:mr-4 file:py-2 file:px-4
                       file:rounded-lg file:border-0 file:bg-accent file:text-white
                       hover:file:bg-navy file:cursor-pointer cursor-pointer"
          />
          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className="w-full bg-accent hover:bg-navy disabled:bg-slate-300
                       text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {loading ? "Uploading..." : "Upload & Analyze"}
          </button>

          {error && (
            <p className="text-red-600 text-sm mt-3">{error}</p>
          )}

          {result && (
            <div className="mt-5 p-4 bg-emerald-50 border border-emerald-200 rounded-lg text-sm">
              <p className="font-semibold text-emerald-800 mb-1">{result.file_name}</p>
              <p className="text-emerald-700">
                {result.row_count} rows &times; {result.column_count} columns
              </p>
              <p className="text-emerald-700 mt-1 break-words">
                Columns: {result.columns.join(", ")}
              </p>
            </div>
          )}
        </div>

        {datasets.length > 0 && (
          <div className="mt-8">
            <h2 className="text-lg font-semibold text-navy mb-3">Uploaded datasets</h2>
            <div className="space-y-2">
              {datasets.map((d) => (
                <div
                  key={d.id}
                  className="bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm flex justify-between"
                >
                  <span className="font-medium text-slate-700">{d.file_name}</span>
                  <span className="text-slate-500">
                    {d.row_count} rows &middot; {d.column_count} cols
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
