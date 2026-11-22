#!/usr/bin/env python3
"""Validate a TB371FC acceptance ledger offline; never execute its commands.

Exit 0 means internally consistent, not hardware accepted. --require-accepted
returns 2 for a valid pending ledger. Exit 1 is malformed/inconsistent evidence.
This checks provenance structure, references, integrity and declared gates. It
cannot authenticate an experiment or replace engineering review of its results.
"""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


REPO = Path(__file__).resolve().parents[2]
DEFAULT = REPO / "docs/research/2026-11-23/acceptance.json"
CLASSES = {"source_clue", "host_build", "device_android", "device_linux"}
STATUSES = {"not_run", "blocked", "running", "pass", "fail", "not_applicable"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_PLAN_BYTES = 5 * 1024 * 1024


class Invalid(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Invalid(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def reject_constant(value):
    raise Invalid("nonfinite JSON number: " + value)


def indexed(items, label):
    require(isinstance(items, list), label + " must be a list")
    result = {}
    for item in items:
        require(isinstance(item, dict), label + " entry must be an object")
        key = item.get("id")
        require(isinstance(key, str) and key, label + " entry lacks id")
        require(key not in result, label + " duplicate id: " + key)
        result[key] = item
    return result


def timestamp(value, label):
    require(isinstance(value, str), label + " must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Invalid(label + " is not an ISO timestamp") from exc
    require(parsed.utcoffset() is not None, label + " needs a timezone")
    return parsed


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def safe_evidence_path(root, value, check_files):
    require(isinstance(value, str), "evidence path must be a string")
    path = PurePosixPath(value)
    require(value and not path.is_absolute() and ".." not in path.parts
            and "\\" not in value and str(path) == value,
            "evidence path must be normalized and relative: " + value)
    current = root
    for part in path.parts:
        current = current / part
        require(not current.is_symlink(), "evidence symlink refused: " + value)
    require(current.resolve().is_relative_to(root.resolve()), "evidence path escaped repository")
    if check_files:
        require(current.is_file(), "evidence file unavailable: " + value)
        require(current.stat().st_size <= 64 * 1024 * 1024,
                "evidence exceeds 64 MiB metadata bound: " + value)
    return current


def validate(plan, root=REPO, check_files=False):
    require(isinstance(plan, dict) and type(plan.get("schema_version")) is int
            and plan["schema_version"] == 1,
            "expected acceptance schema_version 1")
    owner = plan["device"]["id"]
    require(nonempty(owner), "device id missing")
    require(set(plan["evidence_classes"]) == CLASSES, "four evidence classes required")
    evidence = indexed(plan["evidence_registry"], "evidence")
    tests = indexed(plan["tests"], "tests")
    require(tests, "empty acceptance scope")
    stacks = indexed(plan["stack_manifests"], "stack_manifests")
    profiles = plan["comparison_profiles"]
    usage_profiles = indexed(plan["usage_profiles"], "usage_profiles")
    commands = plan["command_catalog"]

    def refs(ids, label, kind=None, run=None, controlled=False):
        require(isinstance(ids, list) and ids, label + " needs evidence references")
        require(len(ids) == len(set(ids)), label + " duplicates evidence")
        for eid in ids:
            require(eid in evidence, label + " references unknown evidence: " + str(eid))
            ev = evidence[eid]
            if kind:
                require(ev["evidence_class"] == kind, label + " requires " + kind + ": " + eid)
            if controlled:
                require(ev.get("controlled_measurement") is True,
                        label + " needs an actual controlled baseline: " + eid)
            if run:
                require(ev.get("device_id") == owner and ev.get("stack_id") == run["stack_id"]
                        and ev.get("run_id") == run["id"], label + " run/stack/device mismatch: " + eid)

    for eid, ev in evidence.items():
        require(ev.get("evidence_class") in CLASSES, eid + " unknown evidence class")
        require(SHA256.fullmatch(ev.get("sha256", "")) is not None, eid + " needs SHA256")
        require(isinstance(ev.get("claims"), list) and ev["claims"], eid + " claims missing")
        require(isinstance(ev.get("limits"), list) and ev["limits"], eid + " limits missing")
        if ev["evidence_class"] in {"device_android", "device_linux"}:
            require(ev.get("device_id") == owner, eid + " is not this owner device")
        if ev["evidence_class"] == "device_linux":
            require(nonempty(ev.get("run_id")) and ev.get("stack_id") in stacks,
                    eid + " lacks a registered Linux run/stack")
        path = safe_evidence_path(root, ev["path"], check_files)
        if check_files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            require(digest == ev["sha256"], eid + " evidence file hash changed: " + ev["path"])

    for sid, stack in stacks.items():
        refs([stack["evidence_id"]], sid + " manifest")
        require(set(stack["components"]) == set(plan["stack_component_keys"]),
                sid + " must identify all eight stack components")
        for key, digest in stack["components"].items():
            require(isinstance(digest, str) and SHA256.fullmatch(digest), sid + ": " + key + " SHA256 missing")

    def cycle_check(tid, active, done):
        if tid in done:
            return
        require(tid not in active, "dependency cycle at " + tid)
        active.add(tid)
        for dep in tests[tid]["dependencies"]:
            require(dep in tests, tid + " unknown dependency: " + dep)
            cycle_check(dep, active, done)
        active.remove(tid)
        done.add(tid)

    done = set()
    for tid in tests:
        cycle_check(tid, set(), done)

    for tid, case in tests.items():
        result = case["result"]
        status = result["status"]
        require(status in STATUSES, tid + " invalid status")
        require(case.get("required_for_best") is True,
                tid + " cannot be removed from the whole-device gate by changing required_for_best")
        require(case["execution"]["environment"] == "device_linux", tid + " is not a Linux case")
        minimum = case["execution"]["minimum_repetitions"]
        require(type(minimum) is int and minimum > 0, tid + " repetitions must be positive")
        require(case["acceptance"]["criteria"], tid + " has no acceptance criteria")
        criteria = indexed(case["acceptance"]["criteria"], tid + " criteria")
        refs(case["baseline"]["evidence_ids"], tid + " existing baseline")
        for cid in case["execution"]["command_ids"]:
            require(cid in commands, tid + " unknown command template: " + cid)
        for pid in case["acceptance"]["comparison_profile_ids"]:
            require(pid in profiles, tid + " unknown comparison profile: " + pid)
        require(isinstance(result["open_issues"], list) and isinstance(result["workarounds"], list),
                tid + " issue/workaround lists missing")
        if status in {"not_run", "blocked"}:
            require(result["run"] is None and not result["criteria_results"]
                    and not result["comparison_results"] and not result["evidence_ids"],
                    tid + " unexecuted case contains purported run results")
            if status == "blocked":
                require(result["blocked_by"], tid + " blocked case needs a reason")
            continue
        if status == "not_applicable":
            require(case["applicability"]["status"] == "confirm_on_owner_android",
                    tid + " required feature cannot be excluded")
            absence = result.get("absence", {})
            require(nonempty(absence.get("reason")) and nonempty(absence.get("reviewer")),
                    tid + " owner absence review missing")
            refs(absence.get("evidence_ids"), tid + " absence", "device_android", controlled=True)
            continue
        run = result["run"]
        require(isinstance(run, dict), tid + " executed case needs run metadata")
        for key in plan["result_contract"]["run_fields"]:
            require(key in run, tid + " run lacks " + key)
        require(run["device_id"] == owner and run["stack_id"] in stacks, tid + " wrong device/stack")
        require(nonempty(run["id"]) and nonempty(run["reviewer"]), tid + " run id/reviewer missing")
        require(run["profile_id"] in usage_profiles, tid + " unknown usage profile")
        started = timestamp(run["started_utc"], tid + " started_utc")
        if status == "running":
            continue
        finished = timestamp(run["finished_utc"], tid + " finished_utc")
        require(finished >= started, tid + " negative run duration")
        refs(result["evidence_ids"], tid + " results", "device_linux", run)
        refs([run["conditions_evidence_id"]], tid + " conditions", "device_linux", run)
        if status != "pass":
            continue
        require(not result["blocked_by"] and not result["open_issues"] and not result["workarounds"],
                tid + " cannot pass with unresolved issues/workarounds")
        require(type(run["repetitions"]) is int and run["repetitions"] >= minimum,
                tid + " too few repetitions")
        for dep in case["dependencies"]:
            require(tests[dep]["result"]["status"] in {"pass", "not_applicable"},
                    tid + " unresolved dependency: " + dep)
            if tests[dep]["result"]["status"] == "pass":
                require(tests[dep]["result"]["run"]["stack_id"] == run["stack_id"],
                        tid + " dependency tested a different stack: " + dep)
        seen = set()
        for outcome in result["criteria_results"]:
            cid = outcome["criterion_id"]
            require(cid in criteria and cid not in seen, tid + " unknown/duplicate criterion")
            seen.add(cid)
            require(outcome.get("met") is True and outcome.get("actual") is not None
                    and nonempty(outcome.get("unit")), cid + " missing actual/met/unit")
            if criteria[cid].get("kind") == "functional" and criteria[cid].get("target") is True:
                require(outcome["actual"] is True, cid + " unknown/false functional result cannot pass")
            refs(outcome.get("evidence_ids"), cid, "device_linux", run)
        require(seen == set(criteria), tid + " criteria results incomplete")
        required_profiles = set(case["acceptance"]["comparison_profile_ids"])
        measured_profiles = set()
        for comparison in result["comparison_results"]:
            pid = comparison["profile_id"]
            require(pid in required_profiles, tid + " unexpected comparison profile")
            measured_profiles.add(pid)
            profile = profiles[pid]
            require(profile["status"] == "frozen", tid + " comparison profile is not frozen: " + pid)
            require(timestamp(profile["frozen_at_utc"], pid) <= started,
                    tid + " comparison profile frozen after trial")
            refs(profile["baseline_evidence_ids"], pid + " frozen baseline", "device_android", controlled=True)
            require(timestamp(comparison["threshold_frozen_utc"], tid + ": " + pid) <= started,
                    tid + " metric threshold frozen after trial")
            require(nonempty(comparison.get("metric")) and nonempty(comparison.get("unit"))
                    and comparison.get("target") is not None and comparison.get("actual") is not None
                    and comparison.get("uncertainty") is not None and comparison.get("met") is True,
                    tid + " comparison lacks measured result/target/uncertainty")
            require(type(comparison.get("paired_trials")) is int
                    and comparison["paired_trials"] >= profile["minimum_paired_trials"],
                    tid + " comparison has too few paired trials")
            refs(comparison["baseline_evidence_ids"], tid + " comparison baseline", "device_android", controlled=True)
            refs(comparison["linux_evidence_ids"], tid + " comparison Linux", "device_linux", run)
        require(measured_profiles == required_profiles, tid + " comparisons incomplete")

    counts = Counter(case["result"]["status"] for case in tests.values())
    runs = {case["result"]["run"]["id"] for case in tests.values() if case["result"].get("run")}
    accepted = all(not case["required_for_best"] or case["result"]["status"] in {"pass", "not_applicable"}
                   for case in tests.values())
    decision = plan["decision"]
    require(decision["owner_linux_pass_count"] == counts["pass"], "decision pass count differs from ledger")
    require(decision["owner_linux_run_count"] == len(runs), "decision run count differs from ledger")
    require(decision["state"] == ("accepted" if accepted else "not_accepted"),
            "decision contradicts individual gates")
    if accepted:
        used_stacks = {case["result"]["run"]["stack_id"] for case in tests.values()
                       if case["required_for_best"] and case["result"]["status"] == "pass"}
        require(len(used_stacks) == 1, "whole-device result must use one final stack")
    return {"validation": "valid_accepted" if accepted else "valid_pending",
            "hardware_accepted": accepted, "tests": len(tests),
            "status_counts": dict(sorted(counts.items())), "owner_linux_runs": len(runs),
            "evidence_files_checked": check_files,
            "limit": "Structural/provenance checks only; no hardware command was executed or result independently authenticated."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT)
    parser.add_argument("--check-files", action="store_true", help="verify every referenced repository file SHA256")
    parser.add_argument("--require-accepted", action="store_true", help="exit 2 when valid but hardware gates remain pending")
    args = parser.parse_args()
    try:
        require(args.plan.is_file() and args.plan.stat().st_size <= MAX_PLAN_BYTES,
                "plan missing or exceeds 5 MiB")
        plan = json.loads(args.plan.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
        summary = validate(plan, check_files=args.check_files)
    except (Invalid, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        print(json.dumps({"validation": "invalid", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 2 if args.require_accepted and not summary["hardware_accepted"] else 0


if __name__ == "__main__":
    sys.exit(main())
