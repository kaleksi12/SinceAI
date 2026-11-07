"""Print a side-by-side table of runs (each a folder under runs/ written by scripts/run_single.py).

    python scripts/compare_runs.py runs/<run-a> runs/<run-b> ...

Reads report.json (the kit evaluator's output) and run_meta.json from each folder, and adds the kit's rules
baseline (baseline_report.json) from the first folder, since every run scores the same cases with the same baseline.
Only runs on the same sample are comparable.
"""
import json
import sys
from pathlib import Path


def load(folder):
    folder = Path(folder)
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    meta = json.loads((folder / "run_meta.json").read_text(encoding="utf-8"))
    return report, meta


def column(report, meta, label):
    h, sc, d = report["headline"], report["brief_scorecard_proxy"], report["details"]
    ci = h.get("safe_action_pass_95ci") or ["?", "?"]
    return {
        "run": label,
        "cases": report["cases"],
        "safe-action pass %": "%s (%s-%s)" % (h["safe_action_pass_pct"], ci[0], ci[1]),
        "false alarms %": h["false_alarm_rate_on_benign_pct"],
        "escalation recall %": h["escalation_recall_pct"],
        "escalation false pos": h["escalation_false_positives"],
        "asked decisive %": h["asked_decisive_question_pct"],
        "unsafe stmts %": h["unsafe_statement_rate_pct"],
        "step coverage %": d["required_step_coverage_pct"],
        "weighted proxy": sc["weighted_proxy_over_assessed_dimensions"],
        "correctness": sc["correctness"],
        "clarity": sc["clarity"],
        "uncertainty+esc": sc["uncertainty_escalation"],
        "privacy": sc["privacy_consent"],
        "unnecessary questions": d["unnecessary_questions_total"],
        "writer fallbacks": meta.get("writer_fallbacks") if meta else "",
        "seconds": meta.get("seconds") if meta else "",
        "llm calls": meta.get("llm_calls") if meta else "",
    }


def main():
    folders = sys.argv[1:]
    if not folders:
        sys.exit(__doc__)
    cols = []
    for f in folders:
        report, meta = load(f)
        label = "%s %s%s" % (meta["model"].split("/")[-1], meta.get("mode", "single"),
                             " optimized" if meta.get("guidelines", "default") != "default" else "")
        cols.append(column(report, meta, label))
    base = json.loads((Path(folders[0]) / "baseline_report.json").read_text(encoding="utf-8"))
    cols.append(column(base, None, "kit baseline (single)"))

    rows = [k for k in cols[0] if k != "run"]
    width = [max(len(str(c["run"])), *(len(str(c[k])) for k in rows)) for c in cols]
    first = max(len(k) for k in rows)
    print(" " * first + "  " + "  ".join(str(c["run"]).ljust(w) for c, w in zip(cols, width)))
    for k in rows:
        print(k.ljust(first) + "  " + "  ".join(str(c[k]).ljust(w) for c, w in zip(cols, width)))


if __name__ == "__main__":
    main()
