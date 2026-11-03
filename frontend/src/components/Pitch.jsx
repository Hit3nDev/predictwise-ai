import { useEffect } from "react";
import { Icon, LogoMark } from "./icons";

/* The honest case for this app next to a general chat assistant. Every cell
   is something this codebase does (and is tested for), or says plainly that
   it doesn't. */

const ROWS = [
  ["Gives you answers without being asked",
   "Opens with a briefing and a weekly to-do list from your own file.",
   "You have to know what to ask."],
  ["Shows how each number was worked out",
   "Every AI answer can show the exact calculation on your file.",
   "Only if you ask, and it can still recall or round figures."],
  ["Predicts with a tested score",
   "Trains several models, scores them on rows they never saw, and says how reliable the result is.",
   "Gives an estimate; no held-out test unless you build one."],
  ["Warns when a question is outside your data",
   "A 999-month tenure is flagged before you rely on the answer.",
   "Will usually still answer."],
  ["Checks it is fair across groups",
   "Compares outcomes across city, age band and so on, using the four-fifths guideline.",
   "Not built in."],
  ["Keeps your file on your computer",
   "The file stays here. Private mode sends nothing to any AI service.",
   "The file is uploaded to a cloud service."],
  ["Made for a Hindi-speaking shopkeeper",
   "₹ with lakh and crore, Hindi and Hinglish, voice in and out, one tap to share on WhatsApp.",
   "Can do Hindi, but not set up around a shop's day."],
  ["Works without an AI key",
   "Counts, trends, forecasts, groups, unusual rows and predictions all run offline.",
   "Needs internet."],
];

export default function Pitch({ onClose }) {
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 overflow-y-auto bg-black/60 p-4 backdrop-blur-sm sm:p-10" onClick={onClose} role="dialog" aria-modal="true" aria-label="Why PredictWise">
      <div className="mx-auto max-w-3xl animate-rise overflow-hidden rounded-[16px] border border-line bg-bone shadow-lift" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-6 px-6 pb-6 pt-6 sm:px-8">
          <div>
            <p className="eyebrow flex items-center gap-2"><LogoMark size={16} /> Why PredictWise?</p>
            <h2 className="display mt-4 text-[32px] leading-[1.05] sm:text-[40px]">
              A shopkeeper should not need to know data to use <em>their own</em> data.
            </h2>
            <p className="mt-4 max-w-[60ch] text-[14.5px] leading-relaxed text-mute">
              Most small businesses already keep sales in a notebook or a spreadsheet. They never use it, because
              asking good questions is a skill. PredictWise asks the questions for them, and shows its working.
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-ink/20 text-ink hover:border-ink hover:bg-ink hover:text-sheet">
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="overflow-x-auto border-t border-line bg-sheet">
          <table className="w-full min-w-[560px] text-left text-[13.5px]">
            <thead>
              <tr className="border-b border-line">
                <th className="px-6 py-3 sm:px-8" />
                <th className="eyebrow px-3 py-3 font-normal !text-ink">PredictWise</th>
                <th className="eyebrow px-3 py-3 pr-6 font-normal sm:pr-8">A general chat assistant</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([what, us, them], i) => (
                <tr key={what} className="border-t border-line align-top">
                  <td className="w-[28%] px-6 py-3.5 sm:px-8">
                    <span className="num mr-2.5 text-[11px] text-mute">{String(i + 1).padStart(2, "0")}</span>
                    <span className="font-semibold">{what}</span>
                  </td>
                  <td className="px-3 py-3.5">{us}</td>
                  <td className="px-3 py-3.5 pr-6 text-mute sm:pr-8">{them}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="border-t border-line px-6 py-4 text-[12.5px] text-mute sm:px-8">
          A general assistant is the better choice for open writing, brainstorming and questions that have nothing to do with your file.
          PredictWise is built for one job: turning your own records into decisions you can trust.
        </p>
      </div>
    </div>
  );
}
