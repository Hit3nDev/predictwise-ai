"""
Report builder: turns a trained model into a single self-contained HTML page
that can be printed to PDF (Ctrl+P) or handed to a bank, a partner or a
shop-floor manager.

The headline paragraph is written by the LLM when a key is configured, and by
a plain template otherwise, so the report is useful with or without a key.
Everything else is generated from stored results, so no number in the report
is ever invented by a language model.
"""

from __future__ import annotations

import html
import json
from datetime import datetime

import llm_provider
from trust import _fmt, pretty

e = html.escape


def _metric_words(task: str, metrics: dict, target: str) -> tuple[str, str]:
    """(headline number, plain sentence) for the held-out score."""
    if task == "classification":
        acc = metrics.get("accuracy")
        if acc is None:
            return "—", "No score was recorded."
        right = round(acc * 10)
        verdict = (
            "very reliable" if acc >= 0.9 else "reliable" if acc >= 0.8
            else "fairly reliable" if acc >= 0.7 else "only a rough guide"
        )
        return f"{acc:.0%}", f"On rows it had never seen, it got {right} out of 10 right. That is {verdict}."
    r2 = metrics.get("r2")
    mae = metrics.get("mae")
    if r2 is None:
        return "—", "No score was recorded."
    verdict = (
        "very reliable" if r2 >= 0.85 else "reliable" if r2 >= 0.65
        else "fairly reliable" if r2 >= 0.4 else "only a rough guide"
    )
    off = f" Its guesses are typically off by about {_fmt(mae)}." if mae is not None else ""
    return f"{r2:.0%}", f"It explains {r2:.0%} of why {pretty(target)} goes up and down, which is {verdict}.{off}"


def _template_summary(target, task, n_rows, metrics, top_features, audit, monitoring) -> str:
    head, sentence = _metric_words(task, metrics, target)
    drivers = ", ".join(pretty(f["feature"]) for f in top_features[:3]) or "the columns provided"
    out = (
        f"This report describes a model that predicts {pretty(target)} from {n_rows:,} past records. "
        f"{sentence} The things that matter most are {drivers}."
    )
    if audit and audit["status"] == "review":
        out += f" A fairness check across {pretty(audit['group_column'])} found gaps worth a closer look."
    elif audit and audit["status"] == "pass":
        out += f" A fairness check across {pretty(audit['group_column'])} found no large gaps."
    if monitoring and monitoring["status"] == "drifting":
        out += " Recent inputs have drifted away from the training data, so retraining is advisable."
    return out


def _llm_summary(facts: dict) -> str | None:
    if not llm_provider.configured():
        return None
    result = llm_provider.complete(
        messages=[{"role": "user", "content": json.dumps(facts, default=str)}],
        system=(
            "You write the opening paragraph of a one-page report for a small-business owner with no "
            "data background. Use ONLY the facts in the JSON; never add numbers. Three to four plain "
            "sentences: what was predicted, how reliable it is, what matters most, one caution if any. "
            "No jargon, no bullet points, no headings."
        ),
        max_tokens=250,
    )
    text = (result or {}).get("text")
    return text.strip() if text else None


CSS = """
:root{--slate:#10131a;--paper:#fff;--field:#f2f3ef;--rule:#d8dad2;--ink:#2f7d6e;--clay:#a8432f}
*{box-sizing:border-box}
body{margin:0;background:var(--field);color:var(--slate);font:15px/1.55 Archivo,"Helvetica Neue",Arial,sans-serif}
.page{max-width:800px;margin:32px auto;background:var(--paper);border:1px solid var(--rule);border-radius:2px;padding:48px 56px}
h1{font-size:28px;line-height:1.15;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:17px;margin:34px 0 10px;padding-top:14px;border-top:1px solid var(--rule)}
p{margin:0 0 10px;max-width:68ch}
.meta{color:#5a6070;font-size:13px;margin-bottom:22px}
.num{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
.lead{font-size:17px;line-height:1.5}
.score{display:flex;gap:18px;align-items:baseline;margin:14px 0}
.score b{font-size:44px;line-height:1;color:var(--ink);letter-spacing:-.02em}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:8px 0}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule)}
th{font-weight:600;color:#5a6070}
td.r,th.r{text-align:right}
.bar{height:8px;background:var(--field);border-radius:1px;min-width:120px}
.bar i{display:block;height:100%;background:var(--ink)}
.pill{display:inline-block;padding:1px 8px;border:1px solid currentColor;border-radius:2px;font-size:12.5px}
.ok{color:var(--ink)}.warn{color:var(--clay)}
.foot{margin-top:36px;padding-top:12px;border-top:1px solid var(--rule);color:#5a6070;font-size:12.5px}
@media print{body{background:#fff}.page{border:0;margin:0;padding:0;max-width:none}h2{break-after:avoid}}
@media (max-width:640px){.page{margin:0;padding:24px 18px;border:0}}
"""


def build_report(
    *, dataset_name, experiment, model, leaderboard, importance, reference,
    audit, monitoring, audience="simple",
) -> str:
    task = experiment.task_type
    target = experiment.target_column
    metrics = json.loads(model.metrics_json or "{}")
    n_rows = (experiment.n_train or 0) + (experiment.n_test or 0)
    headline, sentence = _metric_words(task, metrics, target)
    technical = audience == "technical"

    facts = {
        "target": target, "task": task, "rows_used": n_rows, "score": metrics,
        "top_factors": [f["feature"] for f in importance[:4]],
        "fairness": (audit or {}).get("findings"),
        "input_health": (monitoring or {}).get("note"),
    }
    summary = _llm_summary(facts) or _template_summary(target, task, n_rows, metrics, importance, audit, monitoring)

    parts = [
        f"<h1>What {e(pretty(target))} depends on</h1>",
        f"<div class='meta'>From <b>{e(dataset_name)}</b> · {n_rows:,} records · "
        f"prepared {datetime.now().strftime('%d %b %Y')}</div>",
        f"<p class='lead'>{e(summary)}</p>",
        "<h2>How far to trust it</h2>",
        f"<div class='score'><b class='num'>{e(headline)}</b><span>{e(sentence)}</span></div>",
        "<p>This score comes from rows the model was <i>not</i> allowed to see while learning, "
        "so it is an honest estimate of how it will do on new cases.</p>",
    ]

    # Drivers
    if importance:
        top = max(abs(f["importance"]) for f in importance) or 1
        parts.append("<h2>What matters most</h2>")
        parts.append("<table><tr><th>Factor</th><th>Influence</th>" + ("<th class='r'>Score drop</th>" if technical else "") + "</tr>")
        for f in importance[:8]:
            w = max(2, round(abs(f["importance"]) / top * 100))
            parts.append(
                f"<tr><td>{e(pretty(f['feature']).capitalize())}</td>"
                f"<td><div class='bar'><i style='width:{w}%'></i></div></td>"
                + (f"<td class='r num'>{f['importance']:.4f}</td>" if technical else "")
                + "</tr>"
            )
        parts.append("</table>")

    # Fairness
    if audit:
        cls = {"pass": "ok", "review": "warn"}.get(audit["status"], "")
        label = {"pass": "No large gaps", "review": "Worth a closer look", "insufficient_data": "Not enough data"}[audit["status"]]
        parts.append(f"<h2>Fairness check by {e(pretty(audit['group_column']))}</h2>")
        parts.append(f"<p><span class='pill {cls}'>{label}</span></p>")
        for line in audit["findings"]:
            parts.append(f"<p>{e(line)}</p>")
        cols = ["Group", "People"]
        if audit["task"] == "classification":
            if audit.get("positive_class") is not None:
                cols.append(f"Got “{e(str(audit['positive_class']))}”")
            cols.append("Model right")
        else:
            cols += ["Average predicted", "Typical error"]
        parts.append("<table><tr>" + "".join(f"<th{' class=r' if i else ''}>{c}</th>" for i, c in enumerate(cols)) + "</tr>")
        for g in audit["groups"]:
            cells = [e(g["group"]), f"{g['n']}"]
            if audit["task"] == "classification":
                if audit.get("positive_class") is not None:
                    cells.append(f"{g['selection_rate']:.0%}")
                cells.append(f"{g['accuracy']:.0%}")
            else:
                cells += [_fmt(g["mean_predicted"]), _fmt(g["mae"])]
            num_attr = " class='r num'"
            parts.append("<tr>" + "".join(f"<td{num_attr if i else ''}>{c}</td>" for i, c in enumerate(cells)) + "</tr>")
        parts.append("</table>")

    # Health of live use
    if monitoring and monitoring["total"]:
        parts.append("<h2>How it has been used so far</h2>")
        parts.append(f"<p>{monitoring['total']} predictions made. {e(monitoring['note'])}</p>")

    # Limits
    parts.append("<h2>What to keep in mind</h2>")
    notes = [
        "The model learns from past records. If your business changes (new prices, new customers, a new season), its answers get less reliable.",
        "It finds patterns, not reasons. A factor that matters to the model is a clue worth investigating, not proof that it causes the outcome.",
    ]
    if reference:
        rng = [
            f"{pretty(k)}: {_fmt(v['min'])} to {_fmt(v['max'])}"
            for k, v in list(reference.items()) if v["kind"] == "numeric"
        ][:4]
        if rng:
            notes.append("It only knows the ranges it was trained on (" + "; ".join(rng) + "). Outside those, treat answers as guesses.")
    parts.append("<ul>" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>")

    # Technical appendix
    if technical:
        parts.append("<h2>Model card</h2>")
        parts.append(
            "<table>"
            f"<tr><th>Task</th><td>{e(task)}</td></tr>"
            f"<tr><th>Selected model</th><td>{e(model.algorithm)}</td></tr>"
            f"<tr><th>Selection rule</th><td>Highest mean {experiment.cv_folds}-fold cross-validated score on the training split</td></tr>"
            f"<tr><th>Rows (train / held-out)</th><td class='num'>{experiment.n_train} / {experiment.n_test}</td></tr>"
            f"<tr><th>Held-out metrics</th><td class='num'>{e(', '.join(f'{k} {v}' for k, v in metrics.items()))}</td></tr>"
            f"<tr><th>Model ID</th><td class='num'>{model.id}</td></tr>"
            "</table>"
        )
        parts.append("<h2>All models tried</h2><table><tr><th>Rank</th><th>Algorithm</th><th class='r'>CV mean</th><th class='r'>CV std</th></tr>")
        for m in leaderboard:
            parts.append(
                f"<tr><td>{m.rank or '—'}</td><td>{e(m.algorithm)}</td>"
                f"<td class='r num'>{'—' if m.cv_mean is None else f'{m.cv_mean:.4f}'}</td>"
                f"<td class='r num'>{'—' if m.cv_std is None else f'{m.cv_std:.4f}'}</td></tr>"
            )
        parts.append("</table>")

    parts.append("<div class='foot'>Prepared by PredictWise AI. Figures come from stored model results; "
                 + ("the opening paragraph was written by an AI assistant from those figures." if _llm_used(summary, importance, metrics, task, target, n_rows, audit, monitoring) else "")
                 + " Print this page to save it as a PDF.</div>")

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{e(pretty(target).capitalize())} report</title><style>{CSS}</style></head>"
        f"<body><div class='page'>{''.join(parts)}</div></body></html>"
    )


def _llm_used(summary, importance, metrics, task, target, n_rows, audit, monitoring) -> bool:
    return summary != _template_summary(target, task, n_rows, metrics, importance, audit, monitoring)
