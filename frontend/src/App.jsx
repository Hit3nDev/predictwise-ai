import { useEffect, useState } from "react";
import { listDatasets, getHealth } from "./api";
import TechnicalMode from "./components/TechnicalMode";
import SimpleMode from "./components/SimpleMode";
import Pitch from "./components/Pitch";
import { Icon, LogoMark } from "./components/icons";

/* Where the backend is running. On AWS this reads "Live on AWS" with the storage and
   database actually in use, so the cloud setup is visible on screen. */
function RuntimeBadge() {
  const [h, setH] = useState(null);
  useEffect(() => { getHealth().then(setH).catch(() => setH({ status: "down" })); }, []);
  if (!h) return null;
  const cloud = h.storage === "s3";
  const down = h.status !== "ok";
  const db = h.database === "postgresql" ? "RDS PostgreSQL" : h.database === "sqlite" ? "SQLite" : h.database;
  const text = down ? "Backend offline" : cloud ? `Live on AWS · S3 · ${db}` : `Local · ${db} · disk`;
  return (
    <span
      className="eyebrow hidden items-center gap-2 lg:inline-flex"
      title={h.server && h.server !== "local" ? `Served by ${h.server}` : undefined}
    >
      <span className={`h-2 w-2 rounded-full ${down ? "bg-signal" : cloud ? "bg-lime ring-1 ring-ink/70" : "bg-cobalt"} ${down ? "" : "animate-pulseDot"}`} />
      {text}
    </span>
  );
}

function ModeSwitch({ mode, setMode }) {
  return (
    <div className="relative grid grid-cols-2 rounded-full border border-ink/20 bg-sheet p-[3px]" role="group" aria-label="Mode">
      <span
        aria-hidden="true"
        className={`absolute bottom-[3px] top-[3px] w-[calc(50%-3px)] rounded-full bg-ink transition-transform duration-300 ease-out ${
          mode === "technical" ? "translate-x-full" : "translate-x-0"
        }`}
        style={{ left: 3 }}
      />
      {["simple", "technical"].map((m) => (
        <button
          key={m}
          onClick={() => setMode(m)}
          aria-pressed={mode === m}
          className={`relative z-[1] rounded-full px-4 py-1.5 text-[12.5px] font-medium capitalize ${mode === m ? "text-sheet" : "text-mute hover:text-ink"}`}
        >
          {m}
        </button>
      ))}
    </div>
  );
}

/* Dark is the default; the choice is remembered on this browser (index.html applies it before paint). */
function loadTheme() {
  try { return localStorage.getItem("pw-theme") || "dark"; } catch { return "dark"; }
}

export default function App() {
  const [mode, setMode] = useState("simple");   // simple | technical
  const [theme, setTheme] = useState(loadTheme); // dark | light
  const [dataset, setDataset] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [showPitch, setShowPitch] = useState(false);

  const refresh = () => listDatasets().then(setDatasets).catch(() => {});
  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("pw-theme", theme); } catch { /* private window: fine */ }
  }, [theme]);

  return (
    <div className="min-h-screen">
      {/* Always-visible mode switch: either audience can flip at any point,
          without losing the dataset they've already picked. */}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-bone/90 px-4 backdrop-blur-sm sm:px-6">
        <div className="flex items-center gap-2.5">
          <LogoMark size={26} />
          <span className="font-display text-[21px] font-semibold tracking-tight" style={{ fontVariationSettings: '"SOFT" 40' }}>
            PredictWise
          </span>
          <button
            onClick={() => setShowPitch(true)}
            className="eyebrow ml-3 hidden rounded-full border border-ink/15 px-2.5 py-1 hover:border-ink hover:text-ink md:inline-flex"
          >
            Why PredictWise?
          </button>
        </div>

        <div className="flex items-center gap-3 sm:gap-5">
          <RuntimeBadge />
          <ModeSwitch mode={mode} setMode={setMode} />
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={theme === "dark" ? "Switch to the light theme" : "Switch to the dark theme"}
            title={theme === "dark" ? "Light theme" : "Dark theme"}
            className="hidden h-8 w-8 items-center justify-center rounded-full border border-ink/15 text-mute hover:border-ink hover:text-ink sm:flex"
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} size={15} />
          </button>
        </div>
      </header>

      {showPitch && <Pitch onClose={() => setShowPitch(false)} />}

      <div className="min-h-[calc(100vh-56px)]">
        {mode === "simple" ? (
          <SimpleMode dataset={dataset} setDataset={setDataset} datasets={datasets} refresh={refresh} />
        ) : (
          <TechnicalMode dataset={dataset} setDataset={setDataset} datasets={datasets} refresh={refresh} />
        )}
      </div>
    </div>
  );
}
