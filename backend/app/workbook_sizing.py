"""Exact V4 stock formulas, with explicit optional custom-part starting estimates."""
from decimal import Decimal, ROUND_CEILING
from math import hypot, pi

from app.tooling_catalog import block_records


SIZING_KEYS = (
    "nominal_length_mm", "nominal_width_mm", "nominal_depth_mm", "enlargement_ratio",
    "side_reserve_x_mm", "side_reserve_y_mm", "backing_mm", "allowance_mm", "rounding_mm",
)


def stock_dimensions(inputs, stock_form):
    """Decimal prevents binary noise at an exact ROUNDUP purchasing boundary."""
    d = {key: Decimal(str(inputs[key])) for key in SIZING_KEYS}
    scale = 1 + d["enlargement_ratio"]
    finished_l = d["nominal_length_mm"] * scale + 2 * d["side_reserve_x_mm"]
    finished_w = d["nominal_width_mm"] * scale + 2 * d["side_reserve_y_mm"]
    finished_h = d["nominal_depth_mm"] * scale + d["backing_mm"]

    def stock(value):
        increment = d["rounding_mm"]
        return float(((value + 2 * d["allowance_mm"]) / increment).to_integral_value(rounding=ROUND_CEILING) * increment)

    return {
        "finished_length_mm": float(finished_l),
        "finished_width_mm": None if stock_form == "Round billet" else float(finished_w),
        "finished_height_mm": float(finished_h),
        "raw_length_mm": stock(finished_l),
        "raw_width_mm": None if stock_form == "Round billet" else stock(finished_w),
        "raw_height_mm": stock(finished_h),
    }


def volume(length, width, height, stock_form):
    area = pi * length**2 / 4 if stock_form == "Round billet" else length * width
    return area * height / 1_000_000_000


def custom_envelope(record, part, thickness):
    """Application assumptions, not new formulas attributed to the workbook.

    Stock reserves and mounting lengths stay fixed. Continuous-process cut length
    never scales the extrusion/calibration/cure tooling length. Local pins and
    machine interfaces remain editable instead of being inferred from a bounding box.
    """
    process = record["process"]
    index = int(record["component_id"].split("C")[1])
    l, w, h = part.length_mm, part.width_mm, part.height_mm
    t = thickness
    x, y, z = (record["inputs"][k] for k in SIZING_KEYS[:3])
    if process == "bending":
        x = l
        if index == 2:
            y, z = 8 * t, 4 * t
    elif process == "metal_extrusion":
        diameter = 57 * hypot(w, h) / hypot(40, 40)
        x = y = diameter if index != 3 else diameter + 123
    elif process in {"die_casting", "compression_molding"}:
        x, y, z = (l, w, h) if index == 1 else (l - 2*t, w - 2*t, h - t)
    elif process in {"sand_casting", "investment_casting", "closed_die_forging", "rotational_molding"}:
        x, y, z = l, w, h / 2
        if process == "sand_casting" and index == 2:
            x, y, z = l + 70, w + 70, 20
        elif process == "closed_die_forging" and index != 1:
            x, y, z = l * 1.01, w * 1.01, 30 if index == 2 else 10
            if index == 2:
                x = y = max(x, y)
    elif process == "plastic_extrusion":
        x, y = (w - 2*t, h - 2*t) if index == 2 else (w, h)
    elif process == "blow_molding" and index == 1:
        x, y, z = l, h, w / 2
    elif process in {"transfer_molding", "metal_injection_molding"}:
        if (process == "transfer_molding" and index == 1) or (process == "metal_injection_molding" and index <= 2):
            x, y, z = l, w, h / 2
    elif process == "powder_metallurgy":
        diameter = max(l, w)
        x = y = diameter * ({3: 0.75, 5: 0.5}.get(index, 1))
        if index == 1:
            z = 2 * h
    elif process == "composite_molding":
        x, y, z = l, w, h
    elif process == "pultrusion":
        if index == 1:
            y, z = w, h / 2
        else:
            y, z = w - 2*t, h - 2*t
    elif process in {"punching_blanking", "fine_blanking"}:
        if index in (1, 2) or (process == "fine_blanking" and index == 3):
            x, y = l, w
            if record["stock_form"] == "Round billet":
                x = y = max(l, w)
        if (process == "punching_blanking" and index == 3) or (process == "fine_blanking" and index == 5):
            x, y = l + 70, w + 70
    elif process == "progressive_die_stamping":
        if index <= 2:
            x, y = 4 * (l + 10), w + 2*h + 30
        elif index in (3, 4):
            x, y = l, w + 2*h
        elif index in (5, 6):
            x, y = l, w
            z = h + 10 if index == 5 else h
    elif process == "tube_hydroforming":
        if index == 1:
            x, y, z = l, w, h / 2
        else:
            x = y = 0.75 * max(w, h)
    elif process == "sheet_hydroforming":
        if index == 1:
            x, y, z = l - 2*t, w - 2*t, h - t
        elif index == 2:
            x, y = l + 100, w + 100
    elif process == "spinning" and index == 1:
        x = y = max(l, w) - 2*t
        z = h - t
    return dict(zip(SIZING_KEYS[:3], (x, y, z)))


def size_blocks(request):
    process = request.process.value
    quantity = request.expected_quantity or request.expected_cycles
    records = block_records(process, quantity)
    valid_ids = {b["component_id"] for b in records}
    overrides = {}
    for override in request.block_overrides:
        if override.component_id not in valid_ids:
            raise ValueError(f"Component '{override.component_id}' does not belong to this process.")
        if override.component_id in overrides:
            raise ValueError(f"Duplicate component override: {override.component_id}.")
        overrides[override.component_id] = override.model_dump(exclude_none=True)
    result = []
    for record in records:
        override = overrides.get(record["component_id"], {})
        pieces_per_set = override.get("pieces", record["pieces"])
        item = dict(record, pieces_per_set=pieces_per_set, pieces=pieces_per_set * request.parts_per_mold,
                    modified=bool(override), override=override)
        inputs = dict(record["inputs"])
        if record["purchased"]:
            invalid = set(override) - {"component_id", "pieces", "purchased_unit_cost_eur", "purchased_unit_weight_kg"}
            if invalid:
                raise ValueError("The rated pressure chamber is a purchased assembly, not a milling block.")
            item.update(raw_volume_m3=0, finished_volume_m3=0, machining_volume_m3=0,
                        outside_volume_m3=0, inside_volume_m3=0, sizing_inputs=inputs,
                        machining_basis="Purchased assembly; no invented billet or machining volume.")
            result.append(item)
            continue
        if "purchased_unit_cost_eur" in override or "purchased_unit_weight_kg" in override:
            raise ValueError("Purchased assembly quotes cannot be applied to a machined block.")
        if request.sizing_mode == "part_scaled":
            # Missing sheet thickness has a defined reference value only for solid examples.
            thickness = request.material_thickness_mm
            inputs.update(custom_envelope(record, request.part, thickness))
        inputs.update({k: override[k] for k in SIZING_KEYS if k in override})
        if any(inputs[k] <= 0 for k in SIZING_KEYS[:3]):
            raise ValueError(f"{record['component']}: working envelope must be positive. Check part dimensions and wall thickness.")
        stock_form = override.get("stock_form", record["stock_form"])
        dimensions = stock_dimensions(inputs, stock_form)
        raw_volume = volume(dimensions["raw_length_mm"], dimensions["raw_width_mm"], dimensions["raw_height_mm"], stock_form)
        body_volume = volume(dimensions["finished_length_mm"], dimensions["finished_width_mm"], dimensions["finished_height_mm"], stock_form)
        outside = raw_volume - body_volume
        scale = 1 + inputs["enlargement_ratio"]
        envelope = volume(inputs["nominal_length_mm"] * scale, inputs["nominal_width_mm"] * scale,
                          inputs["nominal_depth_mm"] * scale, stock_form)
        # A male protrusion is retained, not a pocket to remove. Envelopes alone
        # do not define its outside contour. Keep that uncertainty visible.
        inside = envelope if record["role"].startswith("FEMALE") else 0
        machining = outside + inside
        basis = "Stock-to-body allowance plus female working-envelope removal; not a CAD volume."
        if not record["role"].startswith("FEMALE"):
            basis = "Stock-to-body allowance only; positive contours, holes and local features need a machining-volume override."
        if process == "rotational_molding":
            basis += " Exterior shell/flange machining is not defined by the stock formulas; enter a CAD-derived removal volume."
        if "machining_volume_m3" in override:
            machining = override["machining_volume_m3"]
            if machining > raw_volume:
                raise ValueError(f"{record['component']}: removed volume cannot exceed raw stock volume per piece.")
            outside = min(outside, machining)
            inside = machining - outside
            basis = "User-entered total removal volume per piece, including outside allowance."
        item.update(dimensions, stock_form=stock_form, sizing_inputs=inputs,
                    raw_volume_m3=raw_volume, finished_volume_m3=body_volume,
                    outside_volume_m3=outside, inside_volume_m3=inside,
                    machining_volume_m3=machining, machining_basis=basis)
        result.append(item)
    return result
