import { useEffect } from "react";

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
    <div className="fixed inset-0 z-20 overflow-y-auto bg-slate/60 p-4 sm:p-10" onClick={onClose} role="dialog" aria-modal="true" aria-label="Why PredictWise">
      <div className="mx-auto max-w-3xl border border-rule bg-paper" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-6 border-b border-rule px-6 py-5">
          <div>
            <h2 className="text-[22px] leading-snug tracking-tight">A shopkeeper should not need to know data to use their own data</h2>
            <p className="mt-2 max-w-[60ch] text-[14px] text-slate/65">
              Most small businesses already keep sales in a notebook or a spreadsheet. They never use it, because
              asking good questions is a skill. PredictWise asks the questions for them, and shows its working.
            </p>
          </div>
          <button onClick={onClose} className="text-[13px] text-slate/50 hover:text-ink">Close</button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-[13px]">
            <thead className="bg-field text-slate/55">
              <tr>
                <th className="px-6 py-2.5 font-medium" />
                <th className="px-3 py-2.5 font-medium text-ink">PredictWise</th>
                <th className="px-3 py-2.5 pr-6 font-medium">A general chat assistant</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(([what, us, them]) => (
                <tr key={what} className="border-t border-rule/70 align-top">
                  <td className="w-[28%] px-6 py-3 font-medium">{what}</td>
                  <td className="px-3 py-3">{us}</td>
                  <td className="px-3 py-3 pr-6 text-slate/60">{them}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="border-t border-rule px-6 py-4 text-[12.5px] text-slate/55">
          A general assistant is the better choice for open writing, brainstorming and questions that have nothing to do with your file.
          PredictWise is built for one job: turning your own records into decisions you can trust.
        </p>
      </div>
    </div>
  );
}
