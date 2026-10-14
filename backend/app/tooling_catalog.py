"""Versioned workbook data shared by the API, recommendation and sizing engines."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    path = Path(__file__).with_name("data") / "tooling_v4.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["schema_version"] != 1 or len(data["blocks"]) != 354:
        raise RuntimeError("Tooling V4 catalog is missing or incompatible. Deploy app/data/tooling_v4.json.")
    return data


def is_workbook_process(process):
    return any(p["code"] == process for p in catalog()["processes"])


def process_definition(process):
    for definition in catalog()["processes"]:
        if definition["code"] == process:
            return definition
    raise ValueError(f"No workbook process named '{process}'.")


def quantity_grade(process, quantity):
    if quantity < 1:
        raise ValueError("Lifetime quantity must be a positive integer.")
    for grade in catalog()["grades"]:
        if (grade["process"] == process and quantity >= grade["quantity_min"]
                and (grade["quantity_max"] is None or quantity <= grade["quantity_max"])):
            return grade
    raise ValueError(f"No quantity-grade rule for '{process}'.")


def block_records(process, quantity):
    grade = quantity_grade(process, quantity)
    return [b for b in catalog()["blocks"] if b["process"] == process and b["band"] == grade["band"]]


def public_catalog():
    # Provenance stays in the versioned dataset, not in the user interface.
    data = catalog()
    return {
        "processes": data["processes"],
        "quantity_bands": [
            {k: g[k] for k in ("band", "quantity_min", "quantity_max")}
            for g in data["grades"] if g["process"] == "bending"
        ],
        "glossary": [r["cells"][:3] for r in data["sizing_guide"] if 6 <= r["row"] <= 12],
        "sizing_steps": [r["cells"][:3] for r in data["sizing_guide"] if 16 <= r["row"] <= 22],
        "review_checklist": [r["cells"][:3] for r in data["sizing_guide"] if 39 <= r["row"] <= 44],
        "worked_example": data["worked_example"],
    }
