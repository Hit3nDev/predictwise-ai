import { useEffect, useState } from "react";
import { listDatasets } from "./api";
import TechnicalMode from "./components/TechnicalMode";
import SimpleMode from "./components/SimpleMode";

export default function App() {
  const [mode, setMode] = useState("simple");   // simple | technical
  const [dataset, setDataset] = useState(null);
  const [datasets, setDatasets] = useState([]);

  const refresh = () => listDatasets().then(setDatasets).catch(() => {});
  useEffect(() => { refresh(); }, []);

  return (
    <div className="min-h-screen">
      {/* Always-visible mode switch — either audience can flip at any point,
          without losing the dataset they've already picked. */}
      <header className="flex items-center justify-between border-b border-rule bg-paper px-5 py-3">
        <span className="text-[14px] tracking-tight">PredictWise</span>

        <div className="flex border border-rule">
          <button
            onClick={() => setMode("simple")}
            className={`px-3.5 py-1.5 text-[12px] font-medium transition-colors ${
              mode === "simple" ? "bg-ink text-white" : "text-slate/55 hover:text-slate"
            }`}
          >
            Simple
          </button>
          <button
            onClick={() => setMode("technical")}
            className={`px-3.5 py-1.5 text-[12px] font-medium transition-colors ${
              mode === "technical" ? "bg-ink text-white" : "text-slate/55 hover:text-slate"
            }`}
          >
            Technical
          </button>
        </div>
      </header>

      <div className="min-h-[calc(100vh-49px)] bg-field">
        {mode === "simple" ? (
          <SimpleMode dataset={dataset} setDataset={setDataset} datasets={datasets} refresh={refresh} />
        ) : (
          <TechnicalMode dataset={dataset} setDataset={setDataset} datasets={datasets} refresh={refresh} />
        )}
      </div>
    </div>
  );
}
