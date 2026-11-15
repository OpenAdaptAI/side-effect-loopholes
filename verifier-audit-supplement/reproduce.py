#!/usr/bin/env python3
"""Derive the verifier-audit counts from the packaged evidence.

The ``data/`` derivatives are the reviewed supplement's anonymous cell records.
The ``camera_ready/`` files are aggregate summaries of the camera-ready
evidence. Where a camera-ready count can be recomputed from ``data/``, this
script recomputes it and refuses to run when the two disagree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RUNGS = ("RUNG-0", "RUNG-1", "RUNG-2", "RUNG-3")


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def load_member(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def appworld_rung(cell: dict, manifest: dict) -> str:
    trajectories = {row["trajectory"]: row for row in manifest["trajectories"]}
    evaluators = {row["evaluator"]: row for row in manifest["evaluators"]}
    trajectory = trajectories[cell["trajectory"]]
    evaluator = evaluators[cell["evaluator"]]
    base = trajectories[evaluator["base_trajectory"]]
    if evaluator["kind"] == "base" and base["trajectory"] == trajectory["trajectory"]:
        return "DIAG"
    if evaluator["kind"] == "moved" and base["trajectory"] == trajectory["trajectory"]:
        return "RUNG-0"
    if base["generator"] == trajectory["generator"]:
        return "RUNG-1"
    if set(base["effect_dimensions"]) & set(trajectory["effect_dimensions"]):
        return "RUNG-2"
    return "RUNG-3"


def intent_swap() -> dict:
    cells = load("intent_swap_cells.json")
    manifests = load("manifests.json")
    wa_class_to_rung = {
        "control": "DIAG",
        "moved-intent": "RUNG-0",
        "sibling-config": "RUNG-1",
        "within-family-catalog": "RUNG-2",
        "within-family-form-or-cross-family": "RUNG-3",
    }
    aw_rows = [(appworld_rung(cell, manifests["appworld"]), cell) for cell in cells["appworld"]]
    wa_rows = [(wa_class_to_rung[cell["registered_class"]], cell) for cell in cells["workarena"]]

    def summarize(rows: list[tuple[str, dict]], source: str) -> dict:
        diagonal = [cell for rung, cell in rows if rung == "DIAG"]
        assert diagonal and all(cell["verdict"] == "PASS" for cell in diagonal)
        per_rung = []
        for rung in RUNGS:
            valid = [
                cell
                for row_rung, cell in rows
                if row_rung == rung and cell["verdict"] in {"PASS", "FAIL"}
            ]
            per_rung.append(
                {
                    "rung": rung,
                    "valid": len(valid),
                    "checker_pass": sum(cell["verdict"] == "PASS" for cell in valid),
                }
            )
        result = {
            "grid_cells": len(rows),
            "diagonal_controls": len(diagonal),
            "off_diagonal_valid": sum(row["valid"] for row in per_rung),
            "checker_pass": sum(row["checker_pass"] for row in per_rung),
            "errors": sum(
                cell["verdict"] not in {"PASS", "FAIL"} for rung, cell in rows if rung != "DIAG"
            ),
            "per_rung": per_rung,
        }
        if source == "workarena":
            result["foreign_session_provenance_rejections"] = sum(
                rung == "RUNG-3"
                and cell["evidence_kind"] == "foreign-session-provenance-rejection"
                and cell["verdict"] == "FAIL"
                for rung, cell in rows
            )
        return result

    appworld = summarize(aw_rows, "appworld")
    workarena = summarize(wa_rows, "workarena")
    return {
        "appworld": appworld,
        "workarena": workarena,
        "combined_off_diagonal_valid": appworld["off_diagonal_valid"]
        + workarena["off_diagonal_valid"],
        "combined_checker_pass": appworld["checker_pass"] + workarena["checker_pass"],
        "interpretation": "checker-verdict-census-not-false-accept-rate",
    }


def census_non_idempotent(row: dict) -> bool:
    if row["control_call_errors"] != 0:
        return False
    return any(
        item["status"] == "RAN"
        and item["call_errors"] == 0
        and any(before != after for before, after in item["counter_pairs"].values())
        for item in row["tested"]
    )


def application_delta(control: dict, fault: dict) -> dict[str, int]:
    keys = control.keys() | fault.keys()
    return {key: fault.get(key, 0) - control.get(key, 0) for key in sorted(keys)}


def duplicate_write() -> dict:
    census = load("fault_censuses.json")["tasks"]
    primary = load("appworld_extra_cells.json")["cells"]
    non_idempotent = {row["task"] for row in census if census_non_idempotent(row)}
    eligible = []
    for row in primary:
        control = row["conditions"]["control"]
        fault = row["conditions"]["f_extra"]
        delta = application_delta(control["counters"], fault["counters"])
        clean = control["call_errors"] == fault["call_errors"] == 0
        extra_call = fault["api_calls"] - control["api_calls"] == 1
        state_difference = any(value != 0 for value in delta.values())
        if row["cell"] in non_idempotent and clean and extra_call and state_difference:
            eligible.append((row, delta))
    positives = [row for row, _ in eligible if row["conditions"]["f_extra"]["checker_pass"]]
    return {
        "census_tasks": len(census),
        "mutation_eligible": sum(row["mutation_eligible"] for row in census),
        "non_idempotent": len(non_idempotent),
        "degenerate_edits": len(census) - len(non_idempotent),
        "eligible_effects": len(eligible),
        "checker_pass": len(positives),
        "checker_fail": len(eligible) - len(positives),
        "eligible_generators": len({row["generator"] for row, _ in eligible}),
        "positive_generators": len({row["generator"] for row in positives}),
        "control_checker_pass": sum(
            row["conditions"]["control"]["checker_pass"] for row, _ in eligible
        ),
        "evidence_kind": "paired-replay-application-cardinality",
    }


def workarena_readback() -> dict:
    report = load("workarena_extra_readback.json")
    rows = report["cells"]
    protocol = report["sanitized_protocol"]
    templates = {row["template"] for row in rows}
    if len(rows) != protocol["fixed_cell_count"] or len(templates) != 4:
        raise ValueError("WorkArena derivative must cover 23 cells and exactly four templates")

    def predicates(row: dict) -> dict[str, bool]:
        values = row["value_equivalence"]
        observed = {values["persisted_raw"], values["persisted_display"]} - {None}
        requested_observed = values["requested"] in observed
        default_observed = values["default"] in observed
        requested_differs = values["requested"] != values["default"]
        completed = row["http_status"] == 200
        return {
            "completed": completed,
            "requested_observed": completed and requested_observed,
            "default_observed": completed and default_observed,
            "confirmed_nondefault_effect": (
                completed and requested_observed and requested_differs and not default_observed
            ),
        }

    classified = [(row, predicates(row)) for row in rows]
    confirmed = [(row, flags) for row, flags in classified if flags["confirmed_nondefault_effect"]]
    degenerate_passes = [
        (row, flags)
        for row, flags in classified
        if row["checker_verdict"] == "PASS"
        and flags["requested_observed"]
        and flags["default_observed"]
    ]
    return {
        "selected_cells": len(rows),
        "selected_templates": len(templates),
        "completed_readbacks": sum(flags["completed"] for _, flags in classified),
        "requested_value_observed": sum(flags["requested_observed"] for _, flags in classified),
        "default_value_also_observed": sum(flags["default_observed"] for _, flags in classified),
        "checker_pass": sum(row["checker_verdict"] == "PASS" for row in rows),
        "oracle_nondefault_passes": sum(row["checker_verdict"] == "PASS" for row, _ in confirmed),
        "oracle_nondefault_pass_templates": len(
            {row["template"] for row, _ in confirmed if row["checker_verdict"] == "PASS"}
        ),
        "degenerate_checker_passes": len(degenerate_passes),
        "cleanup_clean": sum(row["cleanup_clean"] for row in rows),
        "resumed": sum(row["resumed"] for row in rows),
        "evidence_kind": report["evidence_kind"],
        "selection": report["selection"],
        "status": "withdrawn-see-camera_ready/workarena_rerun_alias_probe.json",
    }


def workarena_readback_template_signatures() -> list[list[int]]:
    """Per template: [cells, oracle nondefault passes, default-alias passes]."""
    rows = load("workarena_extra_readback.json")["cells"]
    signatures: dict[str, list[int]] = {}
    for row in rows:
        values = row["value_equivalence"]
        observed = {values["persisted_raw"], values["persisted_display"]} - {None}
        completed = row["http_status"] == 200
        nondefault = (
            completed
            and values["requested"] in observed
            and values["requested"] != values["default"]
            and values["default"] not in observed
        )
        alias = completed and values["requested"] in observed and values["default"] in observed
        signature = signatures.setdefault(row["template"], [0, 0, 0])
        signature[0] += 1
        signature[1] += row["checker_verdict"] == "PASS" and nondefault
        signature[2] += row["checker_verdict"] == "PASS" and alias
    return sorted(signatures.values())


def fault_vectors() -> list[dict]:
    rows = load("fault_family_vectors.json")["families"]
    assert len({row["evidence_kind"] for row in rows}) > 1
    return rows


def rank_consequence() -> dict:
    data = load("rank_consequence.json")
    out = {
        "metric": data["metric"],
        "official_archive": data["official_archive"],
        "false_accept_input": data["false_accept_input"],
        "false_reject_input": data["false_reject_input"],
        "splits": {},
        "interpretation": data["interpretation"],
    }
    for split, rows in sorted(data["splits"].items()):
        scores = {row["configuration"]: row["successes"] / row["tasks"] for row in rows}
        split_out = {}
        for budget_name, budget in data["budgets"].items():
            alpha = budget["alpha_max"]
            beta = budget["beta_max"]
            intervals = {
                name: [
                    max(0.0, min(1.0, (score - alpha) / (1 - alpha))),
                    max(0.0, min(1.0, score / (1 - beta))),
                ]
                for name, score in scores.items()
            }
            order = [row["configuration"] for row in rows]
            decided = undecided = ties = 0
            for index, above in enumerate(order):
                for below in order[index + 1 :]:
                    if scores[above] == scores[below]:
                        ties += 1
                    elif intervals[above][0] > intervals[below][1]:
                        decided += 1
                    else:
                        undecided += 1
            leader = order[0]
            top1_unique = all(
                intervals[leader][0] > intervals[challenger][1] for challenger in order[1:]
            )
            split_out[budget_name] = {
                "alpha_max": alpha,
                "beta_max": beta,
                "strict_shipped_pairs": decided + undecided,
                "pairs_surviving": decided,
                "pairs_undecided": undecided,
                "shipped_ties": ties,
                "pair_order_survival": decided / (decided + undecided),
                "shipped_leader_uniquely_identified": top1_unique,
            }
        out["splits"][split] = split_out
    return out


def patch_repair() -> dict:
    patches = load_member("patch_repair/patches.json")["patches"]
    cells = load_member("patch_repair/regrade_summary.json")["cells"]
    extra = [row for row in cells if row["condition"] == "extra_ni"]
    controls = [row for row in cells if row["condition"] == "control"]
    require(len(extra) == len(controls) == 6, "regrade summary must hold 6 Extra-NI and 6 controls")
    for row in cells:
        require(
            row["requirements"] == row["requirements_passed"] + row["requirements_failed"],
            "regrade requirement counts do not add up",
        )
        require(
            (row["regraded_verdict"] == "PASS") == (row["requirements_failed"] == 0),
            "regrade verdict disagrees with its requirement counts",
        )
    generators = {row["generator"] for row in patches}
    require(
        generators == {row["generator"] for row in cells}, "patch and regrade generators differ"
    )
    for row in patches:
        change = row["change"]
        require(change["kind"] == "insert-only", "a test change is not insert-only")
        require(
            change["shipped_lines_changed_or_deleted"] == 0, "a test change edits shipped lines"
        )
        require(change["requirement_blocks_added"] == 0, "a test change adds a requirement")
        require(change["assertions_added"] == 1, "a test change adds more than one assertion")
    protocol = (ROOT / "patch_repair" / "PROTOCOL_PATCH_REPAIR_2026_08_30.md").read_text(
        encoding="utf-8"
    )
    require("new post-census increment" in protocol, "missing patch-repair protocol freeze")
    extra_fail = sum(
        row["shipped_verdict"] == "PASS" and row["regraded_verdict"] == "FAIL" for row in extra
    )
    control_pass = sum(
        row["shipped_verdict"] == "PASS" and row["regraded_verdict"] == "PASS" for row in controls
    )
    return {
        "extra_row_pass_to_fail": extra_fail,
        "control_still_pass": control_pass,
        "six_of_six": extra_fail == 6 and control_pass == 6,
        "patched_generators": len(generators),
        "extra_row_failures_on_the_patched_requirement": sum(
            row["failed_requirements_holding_the_inserted_assertion"] == row["requirements_failed"]
            for row in extra
            if row["requirements_failed"]
        ),
        "shipped_lines_changed_or_deleted": sum(
            row["change"]["shipped_lines_changed_or_deleted"] for row in patches
        ),
    }


def checks_pass(summary: dict) -> bool:
    return all(row["ok"] for row in summary["count_checks"]) and summary["digest_checks_passed"] > 0


POSTCONDITION_FAMILIES = (
    "appworld:F-CLAIM-ONLY",
    "appworld:F-OMIT",
    "appworld:F-PARTIAL",
    "appworld:F-WRONG-VALUE",
    "workarena:W-CLAIM-ONLY",
    "workarena:W-NO-SUBMIT",
    "workarena:W-OMIT-DIVERGENT",
    "workarena:W-OMIT-FIELD",
)


def operator_tally(swap: dict, vectors: list[dict]) -> dict:
    """Recompute the camera-ready operator totals from data/ and compare."""
    summary = load_member("camera_ready/operator_tally.json")
    require(
        all(row["ok"] for row in summary["count_checks"]), "tally source reports a failed check"
    )
    by_family = {row["family"]: row for row in vectors}
    post = [by_family[family] for family in POSTCONDITION_FAMILIES]
    derived = {
        "scored": sum(row["scored"] for row in post),
        "PASS": sum(row["checker_pass"] for row in post),
        "FAIL": sum(row["checker_fail"] for row in post),
        "PASS_effect_correct": sum(row["degenerate_pass"] for row in post),
    }
    totals = summary["postcondition_operators"]["totals"]
    for key, value in derived.items():
        require(totals[key] == value, f"postcondition {key} differs from data/")
    require(
        totals["confirmed_false_accepts"] == 0, "a postcondition edit is a confirmed false accept"
    )
    extra = by_family["appworld:F-EXTRA"]
    frame = summary["frame_operators"]["appworld:F-EXTRA"]
    require(frame["PASS"] == extra["checker_pass"], "F-EXTRA PASS differs from data/")
    require(
        frame["PASS_effect_correct"] == extra["degenerate_pass"], "F-EXTRA equivalent PASS differs"
    )
    require(
        frame["confirmed_false_accepts"] == extra["false_accepts_supported_by_this_evidence"],
        "F-EXTRA confirmed false accepts differ from data/",
    )
    binding = summary["binding_operators_intent_swap"]
    twins = {
        source: next(row["valid"] for row in swap[source]["per_rung"] if row["rung"] == "RUNG-0")
        for source in ("appworld", "workarena")
    }
    for source in ("appworld", "workarena"):
        require(
            binding[source]["off_diagonal_valid"] == swap[source]["off_diagonal_valid"],
            f"{source} off-diagonal count differs from data/",
        )
        require(binding[source]["one_parameter_twins"] == twins[source], f"{source} twins differ")
    require(
        binding["off_diagonal_valid_total"] == swap["combined_off_diagonal_valid"],
        "combined off-diagonal count differs from data/",
    )
    require(
        binding["off_diagonal_pass_total"] == swap["combined_checker_pass"], "swap PASS differs"
    )
    return {
        "postcondition_scored": derived["scored"],
        "postcondition_checker_fail": derived["FAIL"],
        "postcondition_checker_pass": derived["PASS"],
        "postcondition_pass_effect_correct": derived["PASS_effect_correct"],
        "postcondition_families_with_a_pass": sorted(
            row["family"] for row in post if row["checker_pass"]
        ),
        "appworld_extra_checker_pass": extra["checker_pass"],
        "appworld_extra_pass_effect_correct": extra["degenerate_pass"],
        "confirmed_false_accepts": frame["confirmed_false_accepts"],
        "confirmed_false_accepts_by_generator": summary["confirmed_false_accepts_by_generator"],
        "binding_off_diagonal_valid": {
            "appworld": swap["appworld"]["off_diagonal_valid"],
            "workarena": swap["workarena"]["off_diagonal_valid"],
            "total": swap["combined_off_diagonal_valid"],
        },
        "binding_checker_pass": swap["combined_checker_pass"],
        "one_parameter_twins": {**twins, "total": sum(twins.values())},
    }


def paired_census() -> dict:
    summary = load_member("camera_ready/workarena_paired_census.json")
    require(checks_pass(summary), "census source reports a failed check")
    pairs, episodes, checker = summary["pairs"], summary["episodes"], summary["checker"]
    candidates = pairs["complete_valid_candidates"]
    require(pairs["scheduled"] == sum(pairs["scheduled_by_template"].values()), "pair frame")
    require(pairs["scheduled"] == pairs["complete_valid"] + pairs["unresolved"], "pair accounting")
    require(
        pairs["unresolved"] == sum(pairs["unresolved_by_template"].values()), "unresolved split"
    )
    require(
        pairs["complete_valid"] == sum(pairs["complete_valid_by_template"].values()),
        "complete-pair split",
    )
    require(
        pairs["complete_valid"] == sum(row["complete_valid_pairs"] for row in candidates),
        "candidate pairs",
    )
    require(episodes["scheduled"] == 2 * pairs["scheduled"], "two episodes per pair")
    require(episodes["valid"] == sum(episodes["valid_by_condition"].values()), "valid split")
    require(
        episodes["scheduled"] - episodes["valid"]
        == sum(episodes["invalid_by_template_condition"].values()),
        "invalid split",
    )
    hardware = pairs["unresolved_by_template"].get("create-hardware-asset", 0)
    stopped = sum(
        count
        for key, count in episodes["invalid_by_template_condition"].items()
        if key.endswith(":mutation") and not key.startswith("create-hardware-asset")
    )
    require(hardware + stopped == pairs["unresolved"], "unresolved causes do not add up")
    isolated = sum(
        row["episodes"]
        for row in summary["isolation_of_valid_episodes"]
        if not row["same_task_object"] and row["shared_mutable_specification_objects"] == 0
    )
    return {
        "scope": summary["scope"],
        "scheduled_pairs": pairs["scheduled"],
        "scheduled_episodes": episodes["scheduled"],
        "complete_valid_pairs": pairs["complete_valid"],
        "complete_valid_mutation_checker_pass": pairs["complete_valid_mutation_checker"].get(
            "PASS", 0
        ),
        "complete_valid_control_checker_pass": pairs["complete_valid_control_checker"].get(
            "PASS", 0
        ),
        "complete_valid_readback_confirmed_extra_value": pairs[
            "complete_valid_readback_confirmed_extra_value"
        ],
        "complete_valid_templates": sorted(pairs["complete_valid_by_template"]),
        "complete_valid_candidate_fields": len(candidates),
        "complete_valid_field_names": sorted({row["field"] for row in candidates}),
        "valid_controls": episodes["valid_by_condition"]["control"],
        "valid_controls_reward_1": checker["valid_control_reward"].get("1", 0),
        "valid_mutations": episodes["valid_by_condition"]["mutation"],
        "unresolved_pairs": pairs["unresolved"],
        "unresolved_hardware_asset_pairs": hardware,
        "unresolved_mutation_stopped_before_checker": stopped,
        "delivered_with_verdict": checker["delivered_with_verdict"],
        "delivered_extra_field_flag_unset": checker["delivered_extra_field_flag_at_check_time"].get(
            "unset", 0
        ),
        "valid_episodes_isolated": isolated,
    }


def rerun_withdrawal(readback: dict) -> dict:
    probe = load_member("camera_ready/workarena_rerun_alias_probe.json")
    require(checks_pass(probe), "alias probe reports a failed check")
    accounting, shared = probe["rerun_accounting"], probe["shared_configuration"]
    require(probe["cells"] == readback["selected_cells"], "probe and rerun cover different cells")
    require(
        accounting["nondefault_passes"] == readback["oracle_nondefault_passes"],
        "probe accounting differs from the rerun derivative",
    )
    require(
        accounting["nondefault_passes"]
        == accounting["nondefault_passes_hardware_asset"]
        + accounting["nondefault_passes_outside_hardware_asset"],
        "probe accounting does not add up",
    )
    probe_signatures = sorted(
        [
            cells,
            accounting["nondefault_passes_by_template"].get(template, 0),
            accounting["default_alias_passes_by_template"].get(template, 0),
        ]
        for template, cells in probe["cells_by_template"].items()
    )
    require(
        probe_signatures == workarena_readback_template_signatures(),
        "probe templates do not match the rerun derivative's template aliases",
    )
    return {
        "rerun_cells": probe["cells"],
        "rerun_nondefault_passes": accounting["nondefault_passes"],
        "hardware_asset_cells": shared["hardware_asset_cells"],
        "hardware_asset_cells_expected_serial_overwritten": shared[
            "hardware_asset_cells_expected_serial_overwritten_by_driver"
        ],
        "other_cells": shared["other_cells"],
        "other_cells_any_expected_value_changed": shared["other_cells_any_expected_value_changed"],
        "deep_copy_cells_any_expected_value_changed": probe["deep_copied_configuration"][
            "cells_any_expected_value_changed"
        ],
        "nondefault_passes_outside_hardware_asset": accounting[
            "nondefault_passes_outside_hardware_asset"
        ],
        "status": "withdrawn",
    }


def reward_equivalence() -> dict:
    summary = load_member("camera_ready/e2_reward_equivalence.json")
    c = summary["procredit_c"]

    def rewards(side: dict) -> dict:
        binary = int(side["requirements_passed"] == side["requirements"])
        # ProCredit: Phi_T = 1 when R = 1 and Phi_0 = 0; undetermined when R = 0.
        procredit = binary + c * (1.0 - 0.0) if binary else None
        return {
            "pass_fraction": side["requirements_passed"] / side["requirements"],
            "binary": binary,
            "procredit": procredit,
        }

    equal = differ = 0
    by_generator: dict[str, int] = {}
    for pair in summary["pairs"]:
        control, duplicate = rewards(pair["control"]), rewards(pair["duplicate"])
        require(control["procredit"] is not None, "a control fails its requirements")
        equal += control == duplicate
        extra_writes = (
            pair["duplicate"]["application_writes"] - pair["control"]["application_writes"]
        )
        differ += pair["end_states_differ"] and extra_writes > 0
        by_generator[pair["generator"]] = by_generator.get(pair["generator"], 0) + 1
    return {
        "pairs": len(summary["pairs"]),
        "pairs_with_equal_reward_under_all_three_formulas": equal,
        "pairs_whose_duplicate_made_extra_writes": differ,
        "pairs_by_generator": dict(sorted(by_generator.items())),
        "outcome": summary["outcome"],
        "model_calls": summary["model_calls"],
    }


def failed_duplicates() -> dict:
    summary = load_member("camera_ready/e1b_failed_duplicate_reasons.json")
    listed = summary["repeat_rows_listed"]
    require(len(listed) == summary["repeat_rows"], "E1b rows do not add up")
    flagged = sum(row["failed_a_one_added_payment_request_check"] for row in listed)
    require(
        flagged == summary["repeat_rows_failing_a_one_added_payment_request_check"],
        "E1b count-check rows do not add up",
    )
    return {
        "rows": summary["rows"],
        "agent_model_pairs": summary["agent_model_pairs"],
        "rows_with_any_payment_request_create": summary["rows_with_any_payment_request_create"],
        "repeat_rows": summary["repeat_rows"],
        "repeat_rows_by_status": summary["repeat_rows_by_status"],
        "repeat_agent_model_pairs": summary["repeat_agent_model_pairs"],
        "repeat_rows_failing_a_one_added_payment_request_check": flagged,
        "model_calls": summary["model_calls"],
    }


def official_traces() -> dict:
    summary = load_member("camera_ready/e1_official_trace_regrade.json")
    require(summary["pass_rows"] + summary["fail_rows"] == summary["rows"], "E1 rows do not add up")
    reconciliation = summary["reconciliation"]
    require(
        summary["fail_rows_hit"]["B"] - summary["fail_rows_hit"]["A"]
        == reconciliation["rows_in_B_not_A"] - reconciliation["rows_in_A_not_B"],
        "E1 reconciliation does not add up",
    )
    pass_hits = sum(summary["pass_rows_hit"].values()) + sum(
        count for rule in summary["pass_rows_hit_by_target"].values() for count in rule.values()
    )
    return {
        "rows": summary["rows"],
        "configurations": summary["configurations"],
        "pass_rows": summary["pass_rows"],
        "pass_rows_with_a_repeated_or_identical_target_write": pass_hits,
        "fail_rows_repeating_payment_request_create": {
            rule: summary["fail_rows_hit_by_target"][rule]["payment_request_create"]
            for rule in ("A", "B")
        },
        "fail_rows_with_identical_payment_request_pair": summary["fail_rows_hit"]["C"],
        "question_1_outcome": summary["question_1_outcome"],
        "question_2_outcome": summary["question_2_outcome"],
        "model_calls": summary["model_calls"],
    }


def natural_runs() -> dict:
    summary = load_member("camera_ready/e6_natural_runs_count_check.json")
    accepted = summary["shipped_accept"]
    require(
        accepted
        == summary["shipped_accept_end_state_equals_reference"]
        + summary["shipped_accept_end_state_differs_from_reference"],
        "E6 accepted runs do not add up",
    )
    require(accepted == sum(summary["shipped_accept_by_model"].values()), "E6 model split")
    control = summary["positive_control"]
    return {
        "trials": summary["trials"],
        "task_ids": summary["task_ids"],
        "shipped_accept": accepted,
        "shipped_accept_distinct_call_logs": summary["shipped_accept_distinct_call_logs"],
        "count_check_rejects": summary["count_check_rejects_among_shipped_accept"],
        "shipped_accept_end_state_equals_reference": summary[
            "shipped_accept_end_state_equals_reference"
        ],
        "positive_control_active": (
            f"{control['shipped_pass_count_check_fail']}/{control['task_ids']}"
        ),
        "outcome": summary["outcome"],
        "model_calls": summary["model_calls"],
    }


def workarena_perstep() -> dict:
    """Counts of the per-step experiment over complete valid groups (an
    unresolved episode counts as neither an acceptance nor a rejection)."""
    report = load_member("camera_ready/workarena_perstep_episodes.json")
    groups = report["groups"]
    episodes = [e for g in groups for e in g["episodes"]]
    require(len(episodes) == report["run_episodes"] == report["scheduled_episodes"],
            "per-step episodes do not add up")
    require(len({e["episode_id"] for e in episodes}) == len(episodes), "per-step duplicate episode")
    require(sum(e["valid"] for e in episodes) == report["valid_episodes"], "per-step valid count")
    complete = [g for g in groups if g["complete_valid"]]
    require(len(complete) == report["complete_valid_groups"], "per-step complete groups")

    def ended(e: dict) -> bool:
        if e["first_terminal_step"] is None:
            return False
        require(e["first_terminal_outcome"] == "TERMINAL_OUT_OF_SCOPE_REJECT"
                and e["browsergym_episode_reward"] == 0, "per-step unexpected termination")
        return True

    out = {"probe_mutant_flag_set": [0, 0], "probe_control_flag_set": [0, 0],
           "perstep_first_ended": [0, 0], "perstep_last_ended": [0, 0],
           "perstep_last_reward_1": [0, 0], "perstep_control_ended": [0, 0],
           "perstep_control_reward_1": [0, 0], "copy_rejected_mutant": [0, 0],
           "copy_rejected_control": [0, 0]}

    def add(key: str, hit: bool) -> None:
        out[key][0] += int(bool(hit))
        out[key][1] += 1

    for group in complete:
        role = {(e["condition"], e["placement"]): e for e in group["episodes"]}
        control = role[("control", "none")]
        if group["mode"] == "probe":
            add("probe_mutant_flag_set", role[("mutation", "last")]["pre_insert_window_flag"] == "true")
            add("probe_control_flag_set", control["pre_insert_window_flag"] == "true")
        elif group["mode"] == "perstep":
            add("perstep_first_ended", ended(role[("mutation", "first")]))
            add("perstep_last_ended", ended(role[("mutation", "last")]))
            add("perstep_last_reward_1", role[("mutation", "last")]["browsergym_episode_reward"] == 1)
            add("perstep_control_ended", ended(control))
            add("perstep_control_reward_1", control["browsergym_episode_reward"] == 1)
        else:
            add("copy_rejected_mutant", role[("mutation", "last")]["copy_rejected_on_persisted_flag"])
            add("copy_rejected_control", control["copy_rejected_on_persisted_flag"])
    return {"scheduled_episodes": report["scheduled_episodes"],
            "valid_episodes": report["valid_episodes"],
            "complete_valid_groups": report["complete_valid_groups"],
            **{k: f"{v[0]}/{v[1]}" for k, v in out.items()}}


def workarena_perstep_rerun() -> dict:
    """Counts of the 15 November rerun: the correct run and the fill-last
    edited run for each text or reference field, with BrowserGym's own
    post-step call at submit as the final grade."""
    report = load_member("camera_ready/workarena_perstep_rerun_episodes.json")
    episodes = [e for g in report["groups"] for e in g["episodes"]]
    require(len(episodes) == report["run_episodes"] == report["scheduled_episodes"],
            "rerun episodes do not add up")
    require(sum(e["valid"] for e in episodes) == report["valid_episodes"], "rerun valid count")
    complete = [g for g in report["groups"] if g["complete_valid"]]
    require(len(complete) == report["complete_valid_groups"], "rerun complete groups")
    out = {"ended_before_submit": [0, 0], "control_submit_reward_1": [0, 0],
           "edited_submit_reward_1": [0, 0], "edited_extra_value_confirmed": [0, 0]}

    def add(key: str, hit: bool) -> None:
        out[key][0] += int(bool(hit))
        out[key][1] += 1

    for group in complete:
        for e in group["episodes"]:
            require(e["mode"] == "perstep_bgsubmit" and "submit_step_reward" in e,
                    "rerun episode lacks a submit-step grade")
            add("ended_before_submit", e["first_terminal_step"] is not None)
            if e["condition"] == "control":
                add("control_submit_reward_1", e["submit_step_reward"] == 1)
            else:
                require(e["placement"] == "last", "rerun edited run is not fill-last")
                add("edited_submit_reward_1", e["submit_step_reward"] == 1)
                add("edited_extra_value_confirmed",
                    e["readback_status"] == "CONFIRMED_MUTATED_EFFECT")
    return {"scheduled_episodes": report["scheduled_episodes"],
            "valid_episodes": report["valid_episodes"],
            "complete_valid_groups": report["complete_valid_groups"],
            **{k: f"{v[0]}/{v[1]}" for k, v in out.items()}}


def camera_ready(swap: dict, vectors: list[dict], readback: dict) -> dict:
    return {
        "operator_tally": operator_tally(swap, vectors),
        "workarena_paired_census": paired_census(),
        "workarena_rerun_withdrawal": rerun_withdrawal(readback),
        "e1_official_traces": official_traces(),
        "e1b_failed_duplicates": failed_duplicates(),
        "e2_reward_equivalence": reward_equivalence(),
        "e6_natural_runs": natural_runs(),
        "workarena_perstep": workarena_perstep(),
        "workarena_perstep_rerun": workarena_perstep_rerun(),
    }


def reproduce() -> dict:
    swap = intent_swap()
    vectors = fault_vectors()
    readback = workarena_readback()
    return {
        "schema_version": 5,
        "intent_swap": swap,
        "fault_arm": {
            "appworld_duplicate_write": duplicate_write(),
            "workarena_extra_field_readback": readback,
            "per_family_vectors": vectors,
        },
        "patch_repair": patch_repair(),
        "rank_consequence": rank_consequence(),
        "camera_ready": camera_ready(swap, vectors, readback),
    }


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        value == path.as_posix()
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
    )


def verify_manifest() -> None:
    manifest = ROOT / "MANIFEST.sha256"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if len(lines) != len(set(lines)):
        raise SystemExit("manifest is not unique")
    declared = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\\\x00]+)", line)
        if not match or not safe_relative_path(match.group(2)):
            raise SystemExit("malformed manifest row")
        declared[match.group(2)] = match.group(1)
    if list(declared) != sorted(declared):
        raise SystemExit("manifest paths are not sorted")
    actual_files = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    if set(declared) != actual_files:
        raise SystemExit("manifest membership mismatch")
    for relative, expected in declared.items():
        path = ROOT / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit(f"checksum mismatch: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verify-manifest", action="store_true")
    args = parser.parse_args()
    if args.verify_manifest or args.check:
        verify_manifest()
    rendered = canonical_json(reproduce())
    if args.check:
        expected = json.loads((ROOT / "expected_results.json").read_text(encoding="utf-8"))
        if reproduce() != expected:
            raise SystemExit("reproduced counts differ from expected_results.json")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
