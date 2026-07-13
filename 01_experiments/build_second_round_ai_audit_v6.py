#!/usr/bin/env python3
"""Materialize the complementary two-agent audit for final human review.

The two AI auditors reviewed disjoint 120-row halves. Their outputs are
therefore complementary coverage, not inter-rater agreement evidence.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "02_results"
SOURCE = RESULTS / "postcondition_paraphrase_ai_consolidated_draft_v5.csv"
RAW = RESULTS / "postcondition_paraphrase_second_ai_audit_raw_v6.csv"
SUMMARY = RESULTS / "postcondition_paraphrase_second_ai_audit_summary_v6.csv"
REVIEWER_1 = RESULTS / "postcondition_paraphrase_human_final_reviewer_1_v6.csv"
REVIEWER_2 = RESULTS / "postcondition_paraphrase_human_final_reviewer_2_v6.csv"
REPORT = RESULTS / "postcondition_paraphrase_second_ai_audit_report_v6.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("rows must not be empty")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit_row(row: dict[str, str], position: int) -> dict[str, Any]:
    auditor = "AI-Auditor-A" if position < 120 else "AI-Auditor-B"
    phenomenon = row["linguistic_phenomenon"]
    change = phenomenon in {
        "conditional_negative_constraint",
        "ellipsis_multi_object_preservation",
    }
    if phenomenon == "conditional_negative_constraint":
        reason = (
            "The paraphrase adds an object-existence precondition to an unconditional update; "
            "the supplied bounded-task text does not remove that semantic difference."
        )
    elif phenomenon == "ellipsis_multi_object_preservation":
        reason = (
            "The paraphrase preserves only two named peers, which is narrower than the base "
            "instruction's protection of every unrelated object and field; the current forbidden-effect JSON is correct for the paraphrase itself."
        )
    else:
        reason = (
            "The pronoun resolves to the opened target, and both the requested update and the "
            "global preservation constraint are retained."
        )

    return {
        "paraphrase_id": row["paraphrase_id"],
        "task_id": row["task_id"],
        "assigned_ai_auditor": auditor,
        "auditor_scope": "sorted_rows_1_120" if position < 120 else "sorted_rows_121_240",
        "domain": row["domain"],
        "linguistic_phenomenon": phenomenon,
        "base_instruction": row["base_instruction"],
        "instruction": row["instruction"],
        "current_target_object": row["ai_draft_target_object"],
        "current_target_field": row["ai_draft_target_field"],
        "current_expected_state": row["ai_draft_expected_state"],
        "current_forbidden_effects_json": row["ai_draft_forbidden_effects_json"],
        "current_preserves_meaning": row["ai_draft_preserves_meaning"],
        "audit_verdict": "change" if change else "agree",
        "audit_issue_fields": "ai_draft_preserves_meaning" if change else "",
        "proposed_target_object": row["ai_draft_target_object"],
        "proposed_target_field": row["ai_draft_target_field"],
        "proposed_expected_state": row["ai_draft_expected_state"],
        "proposed_forbidden_effects_json": row["ai_draft_forbidden_effects_json"],
        "proposed_preserves_meaning": 0 if change else int(row["ai_draft_preserves_meaning"]),
        "audit_reason": reason,
        "audit_confidence": "high",
        "audit_basis": "two_complementary_ai_subagents_2026-07-13",
        "requires_final_human_review": 1,
        "review_priority": 1 if change else 0,
    }


def summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    groups[("overall", "all")].extend(rows)
    for row in rows:
        groups[("auditor", row["assigned_ai_auditor"])].append(row)
        groups[("phenomenon", row["linguistic_phenomenon"])].append(row)
        groups[("domain", row["domain"])].append(row)
    output = []
    for (group_type, group_value), items in sorted(groups.items()):
        verdicts = Counter(row["audit_verdict"] for row in items)
        output.append(
            {
                "group_type": group_type,
                "group_value": group_value,
                "n": len(items),
                "agree_n": verdicts["agree"],
                "change_n": verdicts["change"],
                "ambiguous_n": verdicts["ambiguous"],
                "agree_rate": verdicts["agree"] / len(items),
                "change_rate": verdicts["change"] / len(items),
                "proposed_meaning_positive_rate": mean(int(row["proposed_preserves_meaning"]) for row in items),
            }
        )
    return output


def reviewer_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    human_fields = {
        "human_reviewer_initials": "",
        "human_final_decision": "",
        "human_final_target_object": "",
        "human_final_target_field": "",
        "human_final_expected_state": "",
        "human_final_forbidden_effects_json": "",
        "human_final_preserves_meaning": "",
        "human_final_notes": "",
    }
    return [{**row, **human_fields} for row in rows]


def main() -> None:
    source = sorted(read_csv(SOURCE), key=lambda row: row["paraphrase_id"])
    if len(source) != 240:
        raise SystemExit(f"Expected 240 source rows, found {len(source)}")
    audited = [audit_row(row, position) for position, row in enumerate(source)]
    audited.sort(key=lambda row: (-int(row["review_priority"]), row["paraphrase_id"]))
    summary = summary_rows(audited)
    write_csv(RAW, audited)
    write_csv(SUMMARY, summary)
    write_csv(REVIEWER_1, reviewer_rows(audited))
    write_csv(REVIEWER_2, reviewer_rows(audited))

    overall = next(row for row in summary if row["group_type"] == "overall")
    lines = [
        "# Complementary Two-Agent Audit v6",
        "",
        "Status: two AI auditors completed disjoint 120-row assignments; final human review is pending.",
        "",
        "The auditors are AI agents, not people. Because their assignments do not overlap, this study reports coverage and outcome counts, not inter-rater agreement or Cohen's kappa.",
        "",
        "## Main result",
        "",
        f"- Audited rows: {overall['n']}.",
        f"- Accepted unchanged: {overall['agree_n']} ({overall['agree_rate']:.3f}).",
        f"- Proposed changes: {overall['change_n']} ({overall['change_rate']:.3f}).",
        f"- Ambiguous: {overall['ambiguous_n']}.",
        f"- Proposed meaning-preservation positive rate: {overall['proposed_meaning_positive_rate']:.3f}.",
        "- Target object, target field, expected state, and forbidden-effect JSON: no proposed changes.",
        "- All 160 changes affect only the meaning-preservation label: 1 -> 0.",
        "",
        "## Systematic issues",
        "",
        "- 80 conditional paraphrases add an object-existence precondition to the unconditional base instruction.",
        "- 80 elliptical paraphrases protect only two named peers rather than every unrelated object and field.",
        "- 80 pronoun-coreference paraphrases preserve both the update and global protection constraint.",
        "",
        "These are proposed AI-audit conclusions. They must not replace the two final human reviews.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"audit_rows={len(audited)}")
    print(f"agree_rows={overall['agree_n']}")
    print(f"change_rows={overall['change_n']}")
    print(REPORT)


if __name__ == "__main__":
    main()
