/**
 * Model leaderboard.
 *
 * Each row draws the cross-validated score as a bar that runs behind the
 * algorithm name, so ranking is legible at a glance before any number is read.
 * This is the one animated element in the interface — bars grow on arrival,
 * which shows the ranking resolving.
 */

function fmt(v, digits = 3) {
  if (v === null || v === undefined) return "—";
  return Number(v).toFixed(digits);
}

export default function Leaderboard({ result }) {
  const ranked = result.leaderboard.filter((e) => e.status === "ok");
  const failed = result.leaderboard.filter((e) => e.status !== "ok");
  const top = Math.max(...ranked.map((e) => e.cv_mean ?? 0), 0.0001);

  return (
    <div>
      <div className="flex items-baseline justify-between border-b border-rule px-5 py-3">
        <h2 className="text-[15px] font-medium tracking-tight">Model leaderboard</h2>
        <span className="num text-[11px] text-slate/45">
          ranked by {result.cv_folds}-fold cv {result.primary_metric}
        </span>
      </div>

      <ol>
        {ranked.map((e, i) => {
          const width = ((e.cv_mean ?? 0) / top) * 100;
          return (
            <li
              key={e.algorithm}
              className={`relative border-b border-rule/70 ${
                e.is_best ? "bg-ink/[0.045]" : ""
              }`}
            >
              {/* score bar sits behind the text */}
              <div
                className="bar-grow absolute inset-y-0 left-0"
                style={{
                  width: `${width}%`,
                  background: e.is_best ? "rgba(47,125,110,.16)" : "rgba(16,19,26,.05)",
                  animationDelay: `${i * 60}ms`,
                }}
              />
              <div className="relative flex items-center gap-4 px-5 py-3">
                <span className="num w-4 text-[12px] text-slate/40">{e.rank}</span>

                <span className="flex-1 text-[14px]">
                  {e.algorithm}
                  {e.is_best && (
                    <span className="num ml-2.5 border-b border-ink text-[10px] uppercase text-ink">
                      selected
                    </span>
                  )}
                </span>

                <span className="num w-24 text-right text-[13px]">
                  {fmt(e.cv_mean)}
                  <span className="text-[11px] text-slate/40"> ±{fmt(e.cv_std, 2)}</span>
                </span>

                <span className="num w-16 text-right text-[12px] text-slate/55">
                  {fmt(e.train_seconds, 2)}s
                </span>
              </div>
            </li>
          );
        })}
      </ol>

      {failed.length > 0 && (
        <div className="px-5 py-3 text-[12px] text-slate/45">
          {failed.map((f) => (
            <p key={f.algorithm}>
              {f.algorithm} — {f.status}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
