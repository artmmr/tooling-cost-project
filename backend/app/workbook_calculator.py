"""Cost the workbook's component bill of materials using editable app benchmarks.

V4 has no cost, density, removal-rate or load-validation formulas. Such values
remain application assumptions and are not presented as workbook facts.
"""
from dataclasses import asdict
from math import ceil

from app.models import CalculationResponse, ToolingBlockComponentResponse
from app.tooling_catalog import process_definition, quantity_grade
from app.tooling_materials import TOOLING_MATERIALS
from app.workbook_sizing import size_blocks


def costing_family(record):
    note = record["material"].lower()
    # Specific mixed construction is deliberately not costed as solid carbide.
    if "if loading permits" in note:
        return "pre_hardened_mold_steel"
    if "aluminum" in note or note.startswith("6061"):
        return "aluminum_tooling"
    if note.startswith("p20"):
        return "pre_hardened_mold_steel"
    if note.startswith("h13") or note.startswith("hardened h13"):
        return "hardened_mold_steel"
    if "corrosion" in note or "stainless" in note:
        return "corrosion_resistant_mold_steel"
    if note.startswith(("42crmo4", "4140")):
        return "pre_hardened_mold_steel"
    if any(term in note for term in ("pm tool", "pm-steel", "carbide", "m2", "vanadis", "wear-resistant")):
        return "high_wear_cold_work_steel"
    if "tough" in note or "premium" in note:
        return "high_toughness_cold_work_steel"
    return "cold_work_tool_steel"


def calculate_workbook(request):
    # Imported here so the legacy calculator can dispatch without a module cycle.
    from app.calculator import calculate_cooling_cost, validate_route

    if request.tooling_material_assumptions is not None or request.manufacturing_route is not None or request.tooling_material_family is not None:
        raise ValueError("Detailed processes use component-specific costing. Submit material and route changes through block_overrides.")

    process = request.process.value
    quantity = request.expected_quantity or request.expected_cycles
    definition = process_definition(process)
    grade = quantity_grade(process, quantity)
    sized = size_blocks(request)
    warnings = [
        "Working components only. The listed reserves are planning assumptions, not pressure/load-rated minimums.",
        definition["scope"],
        "Grade candidates are alternatives, not a bill of materials. Costs use the selected block construction and editable material-family benchmarks, not grade-specific supplier quotations.",
        "Machining volumes are envelope estimates. Positive contours, holes, shell exteriors, runners and local features need CAD-derived removal volumes for detailed costing.",
        "Heat-treatment benchmarks do not separately price nitriding, coatings, polishing, heaters or controls. Obtain quotes for the specified treatments and excluded hardware.",
    ]
    if request.sizing_mode == "part_scaled":
        warnings.append("Custom-part starting estimates adapt the reference geometry. Reserves, pins, mounting sections, station count and process lengths still need review in the component editor.")
    else:
        warnings.append("Reference mode uses the workbook's working envelopes. Changing part dimensions does not change these envelopes; switch to custom-part mode or edit component inputs.")
    if request.parts_per_mold > 1:
        warnings.append("Multiple sets repeat the complete component package. This does not design a shared multi-cavity layout or enlarge individual blocks.")

    costs = {key: 0.0 for key in ("material", "transformation", "outside", "inside", "milling", "heat", "purchased")}
    total_weight = total_outside = total_inside = total_minutes = 0.0
    milling_index = 0
    complete = True
    outputs = []
    profiles_used = []
    for block in sized:
        override = block["override"]
        count = block["pieces"]
        base = dict(
            component_id=block["component_id"], record_id=block["record_id"], component=block["component"],
            role=block["role"], pieces=count, pieces_per_set=block["pieces_per_set"],
            stock_form=block["stock_form"], material_note=block["material"], heating_cooling=block["thermal"],
            assumption=block["assumption"], sizing_inputs=block["sizing_inputs"], purchased=block["purchased"],
            machining_basis=block["machining_basis"], modified=block["modified"],
        )
        if block["purchased"]:
            quote = override.get("purchased_unit_cost_eur")
            mass = override.get("purchased_unit_weight_kg")
            if quote is None or mass is None:
                complete = False
                warnings.append(f"{block['component']}: supplier price and shipping weight are required. Missing amounts are excluded from the subtotal and freight.")
            purchased_cost = None if quote is None else quote * count
            weight = (mass or 0) * count
            costs["purchased"] += purchased_cost or 0
            total_weight += weight
            outputs.append(ToolingBlockComponentResponse(
                **base, raw_stock="Purchased assembly; no milling block", weight_kg=weight,
                cost_before_commercial=purchased_cost, purchased_unit_cost_eur=quote, purchased_unit_weight_kg=mass,
            ))
            continue
        family = override.get("material_family", costing_family(block))
        if family not in TOOLING_MATERIALS:
            raise ValueError(f"Unknown costing material family '{family}'.")
        profile = TOOLING_MATERIALS[family]
        defaults = asdict(profile)
        material = {k: defaults[k] for k in (
            "density_kg_m3", "block_price_per_tonne", "removal_rate_cm3_min", "milling_volume_factor",
            "milling_tool_price", "heat_treatment_eur_per_kg",
        )}
        material.update(override.get("tooling_material_assumptions", {}))
        route = override.get("manufacturing_route", defaults["route"])
        validate_route(**route)
        profiles_used.append(family)
        raw = block["raw_volume_m3"] * count
        outside = block["outside_volume_m3"] * count
        inside = block["inside_volume_m3"] * count
        weight = raw * material["density_kg_m3"]
        total_weight += weight
        total_outside += outside
        total_inside += inside
        minutes_out = outside * 1e6 / material["removal_rate_cm3_min"]
        minutes_in = inside * 1e6 / material["removal_rate_cm3_min"]
        total_minutes += minutes_out + minutes_in
        machine_rate = sum(getattr(request.assumptions, key.replace("_share", "_rate")) * value for key, value in route.items())
        minute_rate = (machine_rate / request.assumptions.machine_efficiency
                       + request.assumptions.assembly_rate / request.assumptions.operator_efficiency) / 60
        index = ceil((outside + inside) / material["milling_volume_factor"])
        milling_index += index
        # Existing commercial/material allowances retained; quantities are counted once.
        material_cost = weight * material["block_price_per_tonne"] / 1000 * 2 * 1.4
        component_costs = dict(material=material_cost, transformation=material_cost * 0.5,
                               outside=minutes_out * minute_rate * 1.25, inside=minutes_in * minute_rate * 1.25,
                               milling=index * material["milling_tool_price"],
                               heat=weight * material["heat_treatment_eur_per_kg"])
        for key, value in component_costs.items():
            costs[key] += value
        raw_label = (f"Diameter {block['raw_length_mm']:g} x {block['raw_height_mm']:g} mm"
                     if block["stock_form"] == "Round billet" else
                     f"{block['raw_length_mm']:g} x {block['raw_width_mm']:g} x {block['raw_height_mm']:g} mm")
        outputs.append(ToolingBlockComponentResponse(
            **base, **{k: block[k] for k in ("raw_length_mm", "raw_width_mm", "raw_height_mm",
                                            "finished_length_mm", "finished_width_mm", "finished_height_mm")},
            raw_stock=raw_label, raw_volume_m3=raw, finished_volume_m3=block["finished_volume_m3"] * count,
            machining_volume_m3=block["machining_volume_m3"] * count, weight_kg=weight,
            material_family=family, costing_material=f"{profile.name} (cost proxy)",
            material_assumptions=material, manufacturing_route=route, cost_before_commercial=sum(component_costs.values()),
        ))
    cooling = calculate_cooling_cost(total_weight, request.includes_cooling)
    base_cost = sum(costs.values()) + cooling
    margin, handling = base_cost * 0.2, base_cost * 0.05
    logistics = request.logistics
    sea_nm = request.sea_distance_nm if request.sea_distance_nm is not None else request.sea_distance_km / 1.852

    def load(capacity):
        share = total_weight / capacity
        return ceil(share) if logistics.allocation == "whole_load" else share

    road = request.truck_distance_km * logistics.road_rate_eur_per_km * load(logistics.road_load_kg) * logistics.road_journeys
    sea = sea_nm * logistics.sea_rate_eur_per_nm * load(logistics.sea_load_kg) * logistics.sea_journeys
    subtotal = base_cost + margin + handling + road + sea
    machined = [b for b in outputs if not b.purchased]
    reasons = [f"Lifetime quantity {quantity:,} selects {grade['band']}: {grade['concept']}.",
               grade["conditions"], f"Treatment guidance: {grade['treatment']}.",
               "The costed component materials are listed individually; support plates, pins and working inserts can use different grades."]
    if request.workpiece_material.value == "other":
        warnings.append("Part material is unspecified; qualify tooling grade, dimensional compensation and operating temperature before manufacture.")
    if request.abrasive_material or request.workpiece_material.value in {"glass_filled_thermoplastic", "mineral_filled_thermoplastic", "thermoset", "fiber_composite", "metal_powder"}:
        reasons.append("Abrasive workpiece conditions require review of local wear inserts and treatments at every quantity.")
    if request.corrosive_environment or request.workpiece_material.value == "corrosive_polymer":
        reasons.append("Corrosive conditions require review of corrosion-resistant working surfaces; benchmark block grades have not been silently substituted.")
    reasons.append(f"Requested {request.tolerance_level.value.replace('_', ' ')} tolerance and {request.surface_finish.value} finish require grade, finishing and inspection review.")
    return CalculationResponse(
        calculation_basis="workbook_v4", expected_quantity=quantity,
        tooling_material="Component-specific material benchmarks",
        gross_length_mm=max(b.raw_length_mm for b in machined),
        gross_width_mm=max(b.raw_width_mm or b.raw_length_mm for b in machined),
        gross_height_mm=max(b.raw_height_mm for b in machined), tooling_weight_kg=total_weight,
        tooling_quantity_band=grade["band"], tooling_concept=grade["concept"],
        tooling_sizing_basis=("Finished body = enlarged working envelope + reserves. Raw stock = finished body + two face allowances, rounded upward. Dimensions below are per piece; counts and costs include all selected sets."),
        tooling_blocks=outputs, total_machined_blocks=sum(b.pieces for b in machined),
        total_purchased_assemblies=sum(b.pieces for b in outputs if b.purchased),
        grade_candidates=grade["candidates"], grade_treatment=grade["treatment"], grade_scope=grade["scope"],
        selection_conditions=grade["conditions"], tooling_scope=definition["scope"], estimate_warnings=warnings,
        estimate_complete=complete, purchased_assemblies_cost=costs["purchased"],
        outside_machining_volume_m3=total_outside, inside_machining_volume_m3=total_inside,
        milling_time_index=milling_index, removed_volume_time_min=total_minutes,
        material_cost=costs["material"], transformation_cost=costs["transformation"],
        outside_machining_cost=costs["outside"], inside_machining_cost=costs["inside"], milling_tool_cost=costs["milling"],
        cooling_cost=cooling, heat_treatment_cost=costs["heat"], margin=margin, handling_cost=handling,
        road_transport_cost=road, sea_transport_cost=sea, transport_cost=road + sea, final_markup=subtotal * 0.1,
        total_price=subtotal * 1.1, recommended_material=grade["candidates"],
        recommended_material_family=profiles_used[0], recommendation_confidence="review_required",
        recommendation_confidence_explanation="The process and quantity match a workbook rule. Geometry, pressure, temperature, grade suitability and tool life have not been validated by these planning values.",
        failure_modes=["dimensional drift", "surface degradation", "high mechanical loading"],
        recommendation_reasons=reasons,
        recommended_operations=["Confirm construction, loads, stock reserves and machine interfaces.",
                                "Purchase the individual stock blocks and any supplier-rated assemblies.",
                                "Machine working features using the component-specific route allocations.",
                                f"Qualify and apply treatment: {grade['treatment']}.",
                                "Finish, inspect, assemble and qualify the tool under production conditions."],
        cost_model_note="V4 supplies sizing and selection guidance, not costs. Existing app allowances remain: material x2 x1.4, transformation 50%, machining 25%, margin 20%, handling 5%, final markup 10%. Engineering, electricity, overhead and supplier-margin controls are not applied. Tool bases, machine services and excluded hardware are additional.",
    )
