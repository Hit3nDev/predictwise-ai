/**
 * Interface primitives.
 *
 * The house style here is a measuring instrument: hairline rules instead of
 * card chrome, numerals in the mono face, no shadows, radius kept at 2px.
 */

export function Panel({ title, note, children, flush = false }) {
  return (
    <section className="border border-rule bg-paper">
      {(title || note) && (
        <header className="flex items-baseline justify-between border-b border-rule px-5 py-3">
          <h2 className="text-[15px] font-medium tracking-tight">{title}</h2>
          {note && <span className="num text-[11px] text-slate/45">{note}</span>}
        </header>
      )}
      <div className={flush ? "" : "p-5"}>{children}</div>
    </section>
  );
}

export function Button({ children, variant = "solid", ...props }) {
  const base =
    "px-4 py-2 text-[13px] font-medium transition-colors disabled:cursor-not-allowed";
  const styles = {
    solid: "bg-ink text-white hover:bg-slate disabled:bg-rule disabled:text-slate/40",
    outline:
      "border border-slate/25 text-slate hover:border-ink hover:text-ink disabled:opacity-40",
  };
  return (
    <button className={`${base} ${styles[variant]}`} {...props}>
      {children}
    </button>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12px] text-slate/55">{label}</span>
      {children}
    </label>
  );
}

export function Select(props) {
  return (
    <select
      {...props}
      className="sel w-full border border-rule bg-paper px-3 py-2 text-[13px] text-slate"
    />
  );
}

/** A single measured value. The number is the loudest thing on screen. */
export function Readout({ value, label, tone = "plain" }) {
  const tones = {
    plain: "text-slate",
    ink: "text-ink",
    clay: "text-clay",
  };
  return (
    <div className="border-l border-rule pl-3">
      <p className={`num text-[22px] leading-tight ${tones[tone]}`}>{value}</p>
      <p className="mt-0.5 text-[11px] text-slate/50">{label}</p>
    </div>
  );
}

export function Empty({ children }) {
  return (
    <p className="border border-dashed border-rule px-5 py-8 text-center text-[13px] text-slate/45">
      {children}
    </p>
  );
}

export function Notice({ children, tone = "clay" }) {
  const tones = {
    clay: "border-clay/30 bg-clay/[0.04] text-clay",
    ink: "border-ink/30 bg-ink/[0.04] text-ink",
  };
  return (
    <div className={`border px-4 py-2.5 text-[13px] ${tones[tone]}`}>{children}</div>
  );
}
