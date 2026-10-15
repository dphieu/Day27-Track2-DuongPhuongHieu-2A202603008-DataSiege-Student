"""Cross-check the Practice report against the published answer key by seq.

Run outside defense.py: this offline diagnostic reads files and is not loaded
into the event sandbox. It never reads phase keys or encrypted schedules.
"""
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def index_by_seq(records, label):
    indexed = {}
    for record in records:
        seq = record["seq"]
        if type(seq) is not int:
            raise ValueError(f"{label}: seq must be an integer")
        if seq in indexed:
            raise ValueError(f"{label}: duplicate seq {seq}")
        indexed[seq] = record
    return indexed


def validate(report, answers):
    if report["phase"] != "practice":
        raise ValueError("Only the Practice phase has a published answer key")
    verdicts = index_by_seq(report["verdicts"], "report")
    expected = index_by_seq(answers, "answer key")
    if not expected or verdicts.keys() != expected.keys():
        raise ValueError("Report and answer key must contain the same nonempty set of seq IDs")

    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    mismatches = []
    for seq in sorted(expected):
        alerted = verdicts[seq]["alert"]
        actual = expected[seq]["is_faulty"]
        if type(alerted) is not bool or type(actual) is not bool:
            raise ValueError(f"seq {seq}: alert and is_faulty must be booleans")
        outcome = ("tp" if alerted else "fn") if actual else ("fp" if alerted else "tn")
        counts[outcome] += 1
        if alerted != actual:
            mismatches.append({"seq": seq, "alert": alerted, "is_faulty": actual,
                               "pillar": expected[seq].get("pillar"),
                               "fault_key": expected[seq].get("fault_key")})

    n_faulty = counts["tp"] + counts["fn"]
    n_clean = counts["fp"] + counts["tn"]
    tpr = counts["tp"] / n_faulty if n_faulty else 0.0
    fpr = counts["fp"] / n_clean if n_clean else 0.0
    budget = report["budget"]
    overage = max(0.0, (report["cost_ledger"] - budget) / budget) if budget else 0.0
    score = round(100 * (0.5 * tpr - 0.3 * fpr - 0.2 * min(overage, 1)), 2)
    calculated = {"n_faulty": n_faulty, "n_clean": n_clean, "tpr": round(tpr, 4),
                  "fpr": round(fpr, 4), "cost_overage": round(overage, 4), "score": score}
    for field, value in calculated.items():
        if report[field] != value:
            raise ValueError(f"Report {field}={report[field]} disagrees with calculated {value}")
    return {"phase": "practice", "event_count": len(expected), **counts, **calculated,
            "cost_ledger": report["cost_ledger"], "budget": budget,
            "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "solution/practice_report.json")
    parser.add_argument("--answers", type=Path, default=ROOT / "phases/practice_answer_key.json")
    parser.add_argument("--out", type=Path, default=ROOT / "solution/practice_validation.json")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))["result"]
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    summary = validate(report, answers)
    output = json.dumps(summary, indent=2)
    args.out.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
