import { useEffect, useState } from "react";
import { lookupName, detail } from "../api";
import { CardBlock } from "./blocks";
import { Notice } from "./ui";
import { Icon, ThinkingMark } from "./icons";
import { t } from "../i18n";

/* One customer or product at a glance. The names offered are the biggest by sales, so a
   presenter can click one straight away; typing works with partial names and misspellings. */

export default function Lookup({ dataset, lang, onAsk }) {
  const [q, setQ] = useState("");
  const [opts, setOpts] = useState(null);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRes(null); setQ(""); setOpts(null);
    lookupName(dataset.id, "").then(setOpts).catch(() => setOpts({}));
  }, [dataset.id]);

  const run = (name) => {
    const v = (name ?? q).trim();
    if (!v) return;
    setQ(v); setBusy(true);
    lookupName(dataset.id, v)
      .then(setRes)
      .catch((e) => setRes({ available: false, reason: detail(e, "Couldn't look that up.") }))
      .finally(() => setBusy(false));
  };

  const names = (opts?.customers?.length || 0) + (opts?.products?.length || 0);

  return (
    <div className="mx-auto w-full max-w-[780px] px-5 py-8 sm:px-8">
      <p className="eyebrow">{t(lang, "lookup")}</p>
      <h2 className="display mt-2 text-[30px] leading-tight sm:text-[36px]">{t(lang, "lookupTitle")}</h2>

      <div className="mt-5 flex items-center gap-1.5 rounded-full border-[1.5px] border-ink/70 bg-sheet py-1.5 pl-5 pr-1.5 transition focus-within:border-cobalt focus-within:shadow-ring">
        <Icon name="search" size={16} className="shrink-0 text-mute" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder={t(lang, "lookupHint")}
          className="bare min-w-0 flex-1 bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-ink/35"
        />
        <button onClick={() => run()} disabled={!q.trim() || busy} aria-label={t(lang, "lookup")} className="flex h-10 w-10 items-center justify-center rounded-full bg-ink text-sheet transition hover:bg-lime hover:text-[#111111] disabled:bg-ink/10 disabled:text-ink/30">
          <Icon name="arrow" size={18} strokeWidth={2.2} />
        </button>
      </div>

      {opts && names === 0 && !res && <div className="mt-6"><Notice tone="info">{t(lang, "noNames")}</Notice></div>}

      {opts && names > 0 && !res && !busy && (
        <div className="mt-7 space-y-6 animate-rise">
          {opts.customers?.length > 0 && (
            <div>
              <p className="eyebrow mb-2.5">{t(lang, "topCustomers")}</p>
              <div className="flex flex-wrap gap-2">{opts.customers.slice(0, 12).map((n) => <button key={n} onClick={() => run(n)} className="chip">{n}</button>)}</div>
            </div>
          )}
          {opts.products?.length > 0 && (
            <div>
              <p className="eyebrow mb-2.5">{t(lang, "products")}</p>
              <div className="flex flex-wrap gap-2">{opts.products.slice(0, 18).map((n) => <button key={n} onClick={() => run(n)} className="chip">{n}</button>)}</div>
            </div>
          )}
        </div>
      )}

      {busy && (
        <div className="mt-8 flex items-center gap-3"><ThinkingMark size={22} /><span className="eyebrow">{t(lang, "thinking")}</span></div>
      )}

      {res && !busy && !res.available && (
        <div className="mt-6 animate-rise">
          <Notice tone="info">{res.reason}</Notice>
          {res.suggestions?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">{res.suggestions.map((n) => <button key={n} onClick={() => run(n)} className="chip">{n}</button>)}</div>
          )}
          <button onClick={() => setRes(null)} className="eyebrow mt-4 hover:text-ink">← back to names</button>
        </div>
      )}

      {res && !busy && res.available && (
        <div className="mt-6 animate-rise">
          <div className="text-[15.5px] leading-[1.65]">
            {res.narrative.map((line, i) => <p key={i} className={i > 0 ? "mt-2" : ""}>{line}</p>)}
          </div>
          <CardBlock block={res} />
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
            <button onClick={() => onAsk(`Tell me about ${res.name}`)} className="eyebrow inline-flex items-center gap-1.5 hover:text-ink"><Icon name="send" size={13} /> {t(lang, "askInChat")}</button>
            <button onClick={() => setRes(null)} className="eyebrow hover:text-ink">← back to names</button>
          </div>
        </div>
      )}
    </div>
  );
}
