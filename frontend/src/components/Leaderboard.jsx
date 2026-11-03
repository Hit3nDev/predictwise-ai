/**
 * Model leaderboard.
 *
 * Each row draws the cross-validated score as a bar that runs behind the
 * algorithm name, so ranking is legible at a glance before any number is read.
 * Bars grow on arrival, which shows the ranking resolving.
 */

import { Tag } from "./ui";

function fmt(v, digits = 3) {
  if (v === null || v === undefined) return "—";
  return Number(v).toFixed(digits);
}

export default function Leaderboard({ result }) {
  const ranked = result.leaderboard.filter((e) => e.status === "ok");
  const failed = result.leaderboard.filter((e) => e.status !== "ok");
  const top = Math.max(...ranked.map((e) => e.cv_mean ?? 0), 0.0001);

  return (
    <section className="sheet animate-rise overflow-hidden">
      <header className="flex items-baseline justify-between gap-4 border-b border-line px-5 py-3.5 sm:px-6">
        <h2 className="text-[15px] font-semibold tracking-tight">Model leaderboard</h2>
        <span className="eyebrow text-right">ranked by {result.cv_folds}-fold cv {result.primary_metric}</span>
      </header>

      <ol>
        {ranked.map((e, i) => {
          const width = ((e.cv_mean ?? 0) / top) * 100;
          return (
            <li key={e.algorithm} className="relative border-b border-line last:border-b-0">
              {/* score bar sits behind the text */}
              <div
                className="bar-grow absolute inset-y-0 left-0"
                style={{
                  width: `${width}%`,
                  background: e.is_best ? "rgb(var(--lime) / .4)" : "rgb(var(--ink) / .05)",
                  animationDelay: `${i * 60}ms`,
                }}
              />
              <div className="relative flex items-center gap-4 px-5 py-3 sm:px-6">
                <span className="num w-5 text-[11px] text-mute">{String(e.rank).padStart(2, "0")}</span>

                <span className="flex-1 text-[14px] font-medium">
                  {e.algorithm}
                  {e.is_best && <Tag tone="ink" className="ml-2.5 align-middle">selected</Tag>}
                </span>

                <span className="num w-28 text-right text-[13px]">
                  {fmt(e.cv_mean)}
                  <span className="text-[11px] text-mute"> ±{fmt(e.cv_std, 2)}</span>
                </span>

                <span className="num hidden w-16 text-right text-[12px] text-mute sm:block">
                  {fmt(e.train_seconds, 2)}s
                </span>
              </div>
            </li>
          );
        })}
      </ol>

      {failed.length > 0 && (
        <div className="border-t border-line px-5 py-3 text-[12px] text-mute sm:px-6">
          {failed.map((f) => (
            <p key={f.algorithm}>
              {f.algorithm} — {f.status}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
