"""Import the Industrialisation Process & Tooling Matrix into versioned JSON.

Usage: python scripts/import_process_matrix.py path/to/Industrialisation_Process_Tooling_Matrix_EN.xlsx
Writes app/data/process_matrix.json. The runtime reads the JSON, never the workbook.

Each matrix cell reads "<process route> | <tooling>". Both halves are kept verbatim;
the mapping to calculator processes and tooling-material families lives in
app/process_matrix.py so it can be reviewed and tested separately.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from openpyxl import load_workbook

BANDS = [
    ("1–20", 1, 20), ("21–100", 21, 100), ("101–1,000", 101, 1_000),
    ("1,001–10,000", 1_001, 10_000), ("10,001–100,000", 10_001, 100_000), ("Above 100,000", 100_001, None),
]
EXPECTED_HEADER = ["Part material", "Form / family", "1–20 pcs", "21–100 pcs", "101–1,000 pcs",
                   "1,001–10,000 pcs", "10,001–100,000 pcs", ">100,000 pcs", "Comments / criteria"]
GRADE_HEADER = ["Tool grade / family", "Typical use", "Indicative hardness / treatment", "Steel / Fe index %",
                "Aluminium index %", "Copper index %", "Nickel index %", "Molybdenum index %", "Tungsten index %",
                "Other alloying index %", "TOTAL %", "Costing note"]
INDEX_KEYS = ["steel", "aluminium", "copper", "nickel", "molybdenum", "tungsten", "other"]


def slug(*parts):
    return re.sub(r"[^a-z0-9]+", "_", " ".join(parts).lower()).strip("_")


def split_cell(text, where):
    if not isinstance(text, str) or "|" not in text:
        raise ValueError(f"{where}: expected '<route> | <tooling>', got {text!r}")
    route, tooling = (part.strip() for part in text.split("|", 1))
    return {"route": route, "tooling": tooling}


def build(path):
    workbook = load_workbook(path, data_only=True, read_only=True)
    matrix = workbook["Process & Tool Matrix"]
    rows = list(matrix.iter_rows(values_only=True))
    if [str(c).strip() for c in rows[0][:9]] != EXPECTED_HEADER:
        raise ValueError(f"Unexpected matrix header: {rows[0]}")
    entries = []
    for number, row in enumerate(rows[1:], start=2):
        if not row[0]:
            continue
        material, form = str(row[0]).strip(), str(row[1]).strip()
        entries.append({
            "id": slug(material, form),
            "material": material,
            "form": form,
            "bands": [split_cell(row[2 + i], f"row {number}, {BANDS[i][0]}") for i in range(6)],
            "comment": str(row[8] or "").strip(),
            "source_row": number,
        })
    if len({e["id"] for e in entries}) != len(entries):
        raise ValueError("Matrix rows must have unique material/form pairs.")

    grades_sheet = workbook["Tool Grade Index Split"]
    grade_rows = list(grades_sheet.iter_rows(values_only=True))
    if [str(c).strip() for c in grade_rows[0][:12]] != GRADE_HEADER:
        raise ValueError(f"Unexpected grade header: {grade_rows[0]}")
    grades = []
    for row in grade_rows[1:]:
        if not row[0]:
            continue
        index = dict(zip(INDEX_KEYS, (float(v or 0) for v in row[3:10])))
        if abs(sum(index.values()) - 1) > 1e-6:
            raise ValueError(f"Index split for {row[0]} does not total 100%.")
        grades.append({"name": str(row[0]).strip(), "typical_use": str(row[1]).strip(),
                       "hardness": str(row[2]).strip(), "index_split": index, "note": str(row[11] or "").strip()})

    sources = workbook["Index Sources"]
    basket = {}
    for row in list(sources.iter_rows(values_only=True))[1:]:
        if row[0]:
            basket[str(row[0]).strip()] = {"weight": float(row[1] or 0),
                                           "sources": [str(s) for s in row[2:5] if s]}

    return {
        "schema_version": 1,
        "source": {"filename": Path(path).name, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()},
        "bands": [{"band": b, "quantity_min": lo, "quantity_max": hi} for b, lo, hi in BANDS],
        "rows": entries,
        "grades": grades,
        "index_basket": basket,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "app" / "data" / "process_matrix.json"))
    args = parser.parse_args()
    data = build(args.workbook)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['rows'])} matrix rows and {len(data['grades'])} tool grades to {args.out}")
