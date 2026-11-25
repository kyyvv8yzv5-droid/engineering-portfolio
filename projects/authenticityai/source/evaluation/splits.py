"""Family-safe standard and leave-one-family-out benchmark suites."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from evaluation.leakage import build_families


def _bucket(value, seed):
    digest = hashlib.sha256(f"{seed}|{value}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def assign_standard_splits(records, validation_fraction=0.2, test_fraction=0.2, seed=2026):
    if validation_fraction <= 0 or test_fraction <= 0 or validation_fraction + test_fraction >= 1:
        raise ValueError("validation and test fractions must be positive and sum to less than one")
    family_by_sample, _families, _relations = build_families(records)
    output = []
    for record in records:
        value = _bucket(family_by_sample[record["sample_id"]], seed)
        split = "test" if value < test_fraction else "validation" if value < test_fraction + validation_fraction else "train"
        output.append({**record, "split": split})
    return output


def _family_name(record, field, fallback):
    value = record.get(field) or record.get(fallback)
    if not value:
        return None
    return str(value).split(":", 1)[0].strip().casefold()


def leave_one_family_out(records, kind, seed=2026):
    if kind == "generator":
        candidates = sorted({_family_name(record, "generator_family", "generator") for record in records if record.get("label") == "ai"} - {None})
        field, fallback, label = "generator_family", "generator", "ai"
    elif kind == "camera":
        candidates = sorted({_family_name(record, "camera_family", "camera_device") for record in records if record.get("label") == "real"} - {None})
        field, fallback, label = "camera_family", "camera_device", "real"
    else:
        raise ValueError("kind must be generator or camera")
    suites = []
    family_by_sample, _families, _relations = build_families(records)
    for held_out in candidates:
        case = []
        for record in records:
            family = _family_name(record, field, fallback)
            if record.get("label") == label and family == held_out:
                split = "test"
            else:
                value = _bucket(family_by_sample[record["sample_id"]], seed)
                if record.get("label") != label and value < 0.2:
                    split = "test"
                elif value < 0.4:
                    split = "validation"
                else:
                    split = "train"
            case.append({**record, "split": split})
        suites.append({"held_out": held_out, "records": case})
    return suites


def content_category_suites(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record.get("content_category", "other")].append(record)
    return dict(grouped)
