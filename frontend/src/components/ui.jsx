/**
 * Interface primitives.
 *
 * White sheets on bone paper, hairline borders, no drop shadows. Section labels are small
 * mono "eyebrows"; measurements are set in the mono face so the numbers stay the loudest thing.
 */

export function Eyebrow({ children, className = "" }) {
  return <p className={`eyebrow ${className}`}>{children}</p>;
}

export function Panel({ title, note, index, children, flush = false, className = "" }) {
  return (
    <section className={`sheet animate-rise overflow-hidden ${className}`}>
      {(title || note) && (
        <header className="flex items-baseline justify-between gap-4 border-b border-line px-5 py-3.5 sm:px-6">
          <div className="flex items-baseline gap-3">
            {index && <span className="num text-[11px] text-mute">{index}</span>}
            <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
          </div>
          {note && <span className="eyebrow text-right">{note}</span>}
        </header>
      )}
      <div className={flush ? "" : "p-5 sm:p-6"}>{children}</div>
    </section>
  );
}

export function Button({ children, variant = "solid", size = "md", className = "", ...props }) {
  const v = { solid: "btn-solid", outline: "btn-outline", ghost: "btn-ghost" }[variant];
  const s = size === "sm" ? "px-3 py-1.5 text-[12.5px]" : size === "lg" ? "px-6 py-3.5 text-[15px]" : "";
  return (
    <button className={`btn ${v} ${s} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-medium text-mute">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11.5px] text-mute">{hint}</span>}
    </label>
  );
}

export function Select({ className = "", ...props }) {
  return <select {...props} className={`sel field-input ${className}`} />;
}

export function Input({ className = "", ...props }) {
  return <input {...props} className={`field-input ${className}`} />;
}

/** A single measured value. tone: plain | good | warn */
export function Readout({ value, label, tone = "plain" }) {
  const tones = { plain: "text-ink", good: "text-cobalt", warn: "text-signal" };
  return (
    <div className="rounded-[10px] border border-line bg-bone/60 px-4 py-3">
      <p className={`num text-[24px] font-medium leading-none tracking-tight ${tones[tone] ?? tones.plain}`}>{value}</p>
      <p className="eyebrow mt-2">{label}</p>
    </div>
  );
}

export function Empty({ children }) {
  return (
    <p className="rounded-[10px] border border-dashed border-ink/25 px-5 py-10 text-center text-[13px] text-mute">
      {children}
    </p>
  );
}

export function Notice({ children, tone = "warn" }) {
  const tones = {
    warn: "border-signal/35 bg-signal/[0.06] text-signal",
    info: "border-ink/15 bg-sheet text-ink",
  };
  return <div className={`rounded-[10px] border px-4 py-3 text-[13px] ${tones[tone] ?? tones.warn}`}>{children}</div>;
}

/** A small mono tag. tone: line | lime | ink | signal | cobalt */
export function Tag({ children, tone = "line", className = "" }) {
  const tones = {
    line: "border-line bg-sheet text-mute",
    lime: "border-ink/15 bg-lime text-[#111111]",
    ink: "border-ink bg-ink text-sheet",
    signal: "border-signal/40 bg-signal/[0.08] text-signal",
    cobalt: "border-cobalt/30 bg-cobalt/[0.07] text-cobalt",
  };
  return (
    <span className={`eyebrow inline-flex items-center gap-1 rounded-full border px-2 py-[3px] !text-[9.5px] ${tones[tone] ?? tones.line} ${className}`}>
      {children}
    </span>
  );
}

export function Switch({ checked, onChange, label, hint }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="flex w-full items-start gap-3 text-left">
      <span className={`relative mt-[3px] inline-flex h-5 w-9 shrink-0 rounded-full border transition ${checked ? "border-ink bg-ink" : "border-ink/25 bg-sheet"}`}>
        <span className={`absolute top-[3px] h-3 w-3 rounded-full transition-all ${checked ? "left-[19px] bg-lime" : "left-[3px] bg-ink/35"}`} />
      </span>
      <span className="min-w-0">
        <span className="block text-[13.5px] font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-[12px] leading-snug text-mute">{hint}</span>}
      </span>
    </button>
  );
}
