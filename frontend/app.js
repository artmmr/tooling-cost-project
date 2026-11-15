let currentToolingDefaults = null;
let currentToolingMaterialFamily = null;
let currentCountryDefaults = null;


/* =========================================================
   Countries
   ========================================================= */

async function loadCountries() {
  const response = await fetch(
    `${API_BASE_URL}/api/countries`,
  );

  if (!response.ok) {
    throw new Error(
      "Could not load manufacturing countries.",
    );
  }

  const countries =
    await response.json();

  const select =
    document.getElementById(
      "inp-country",
    );

  select.innerHTML = countries
    .map(
      (country) => `
        <option value="${country.code}">
          ${country.name}
        </option>
      `,
    )
    .join("");
}


async function loadCountryDefaults(countryCode) {
  const token = ++countryRevision;
  countryLoading = true;
  invalidateEstimate();
  setStatus("Loading country benchmark assumptions…");
  try {
    const response = await fetch(`${API_BASE_URL}/api/countries/${countryCode}`);
    if (!response.ok) throw new Error("Could not load country benchmark assumptions.");
    const profile = await response.json();
    await ensureEcbRate();
    if (token !== countryRevision) return;
    captureMoney();
    currentCountryDefaults = profile;
    // China and India are costed in USD; their default rates are USD amounts.
    countryCurrency = profile.currency || (EUROPEAN_COUNTRIES.has(countryCode) ? "EUR" : "USD");
    displayCurrency = countryCurrency;
    applyEcbRate();
    updateCurrencyDisplay();
    applyCountryDefaults(profile);
    countryLoading = false;
    setStatus(currencyFactor()
      ? `${profile.name} defaults loaded. Prices in ${displayCurrency}.`
      : "The exchange rate could not be loaded. Enter a EUR/USD rate and its date to calculate in USD.");
    scheduleCalculation();
  } catch (error) {
    if (token !== countryRevision) return;
    countryLoading = false;
    currentCountryDefaults = null;
    throw error;
  }
}

function applyCountryDefaultsRaw(
  profile,
) {
  document.getElementById(
    "inp-engineering-rate",
  ).value =
    profile.engineering_rate;

  document.getElementById(
    "inp-assembly-rate",
  ).value =
    profile.assembly_rate;

  document.getElementById(
    "inp-cnc3-rate",
  ).value =
    profile.cnc_3_axis_rate;

  document.getElementById(
    "inp-cnc5-rate",
  ).value =
    profile.cnc_5_axis_rate;

  document.getElementById(
    "inp-edm-rate",
  ).value =
    profile.edm_rate;

  document.getElementById(
    "inp-grinding-rate",
  ).value =
    profile.grinding_rate;

  document.getElementById(
    "inp-electricity",
  ).value =
    profile.electricity_eur_kwh;

  document.getElementById(
    "inp-machine-efficiency",
  ).value =
    profile.machine_efficiency * 100;

  document.getElementById(
    "inp-operator-efficiency",
  ).value =
    profile.operator_efficiency * 100;

  document.getElementById(
    "inp-overhead-rate",
  ).value =
    profile.overhead_rate * 100;

  document.getElementById(
    "inp-margin-rate",
  ).value =
    profile.margin_rate * 100;
}


/* =========================================================
   Tooling material defaults
   ========================================================= */

function applyToolingMaterialDefaultsRaw(
  profile,
) {
  document.getElementById(
    "inp-tool-density",
  ).value =
    profile.density_kg_m3;

  document.getElementById(
    "inp-tool-price",
  ).value =
    profile.block_price_per_tonne;

  document.getElementById(
    "inp-tool-mrr",
  ).value =
    profile.removal_rate_cm3_min;

  document.getElementById(
    "inp-milling-volume-factor",
  ).value =
    profile.milling_volume_factor;

  document.getElementById(
    "inp-milling-tool-price",
  ).value =
    profile.milling_tool_price;

  document.getElementById(
    "inp-heat-treatment",
  ).value =
    profile.heat_treatment_eur_per_kg;

  document.getElementById(
    "inp-route-cnc3",
  ).value =
    profile.route.cnc_3_axis_share * 100;

  document.getElementById(
    "inp-route-cnc5",
  ).value =
    profile.route.cnc_5_axis_share * 100;

  document.getElementById(
    "inp-route-edm",
  ).value =
    profile.route.edm_share * 100;

  document.getElementById(
    "inp-route-grinding",
  ).value =
    profile.route.grinding_share * 100;

  updateRouteTotal();
}


/* =========================================================
   Manufacturing route total
   ========================================================= */

function getRouteTotal() {
  const cnc3 =
    Number.parseFloat(
      document.getElementById(
        "inp-route-cnc3",
      ).value,
    ) || 0;

  const cnc5 =
    Number.parseFloat(
      document.getElementById(
        "inp-route-cnc5",
      ).value,
    ) || 0;

  const edm =
    Number.parseFloat(
      document.getElementById(
        "inp-route-edm",
      ).value,
    ) || 0;

  const grinding =
    Number.parseFloat(
      document.getElementById(
        "inp-route-grinding",
      ).value,
    ) || 0;

  return (
    cnc3 +
    cnc5 +
    edm +
    grinding
  );
}


function updateRouteTotal() {
  const total =
    getRouteTotal();

  const element =
    document.getElementById(
      "route-total",
    );

  element.textContent =
    `${total.toFixed(0)}%`;

  element.classList.toggle(
    "err",
    Math.abs(total - 100) > 0.01,
  );
}


/* =========================================================
   Process-specific material choices
   ========================================================= */

function updateWorkpieceMaterials() {
  const process =
    document.getElementById(
      "inp-process",
    ).value;

  const materialSelect =
    document.getElementById(
      "inp-workpiece-material",
    );

  if (
    PLASTIC_PROCESSES.has(
      process,
    )
  ) {
    fillSelect(
      "inp-workpiece-material",
      PLASTIC_MATERIALS,
    );

    materialSelect.value =
      "standard_thermoplastic";
  } else {
    fillSelect(
      "inp-workpiece-material",
      METAL_MATERIALS,
    );

    materialSelect.value =
      "mild_steel";
  }

  updateThicknessField();
}


function updateThicknessField() {
  const process =
    document.getElementById(
      "inp-process",
    ).value;

  const field =
    document.getElementById(
      "material-thickness-field",
    );

  const isMetal =
    METAL_PROCESSES.has(
      process,
    );

  field.classList.toggle(
    "field-muted",
    !isMetal,
  );
}


/* =========================================================
   Cycle band → suggested expected cycles
   ========================================================= */

/* The quantity band is derived from the quantity; it is no longer a separate input. */
function syncLegacyBand() {
  if (WorkbookUI.current()) return;
  const quantity = Number(document.getElementById("inp-expected-cycles").value);
  if (Number.isInteger(quantity) && quantity > 0) document.getElementById("inp-cycles").value = legacyBandFor(quantity);
}

function syncExpectedCycles() {
  if (WorkbookUI.chooseBand()) return;
  const cycleBand =
    document.getElementById(
      "inp-cycles",
    ).value;

  const recommendedValue =
    CYCLE_DEFAULTS[cycleBand];

  if (recommendedValue) {
    document.getElementById(
      "inp-expected-cycles",
    ).value =
      recommendedValue;
  }
}


/* =========================================================
   Read calculator state
   ========================================================= */

function readStateRaw() {
  const toolingData =
    currentToolingMaterialFamily
      ? {
          tooling_material_family:
            currentToolingMaterialFamily,

          tooling_material_assumptions: {
            density_kg_m3:
              Number.parseFloat(
                document.getElementById(
                  "inp-tool-density",
                ).value,
              ),

            block_price_per_tonne:
              Number.parseFloat(
                document.getElementById(
                  "inp-tool-price",
                ).value,
              ),

            removal_rate_cm3_min:
              Number.parseFloat(
                document.getElementById(
                  "inp-tool-mrr",
                ).value,
              ),

            milling_volume_factor:
              Number.parseFloat(
                document.getElementById(
                  "inp-milling-volume-factor",
                ).value,
              ),

            milling_tool_price:
              Number.parseFloat(
                document.getElementById(
                  "inp-milling-tool-price",
                ).value,
              ),

            heat_treatment_eur_per_kg:
              Number.parseFloat(
                document.getElementById(
                  "inp-heat-treatment",
                ).value,
              ),
          },

          manufacturing_route: {
            cnc_3_axis_share:
              Number.parseFloat(
                document.getElementById(
                  "inp-route-cnc3",
                ).value,
              ) / 100,

            cnc_5_axis_share:
              Number.parseFloat(
                document.getElementById(
                  "inp-route-cnc5",
                ).value,
              ) / 100,

            edm_share:
              Number.parseFloat(
                document.getElementById(
                  "inp-route-edm",
                ).value,
              ) / 100,

            grinding_share:
              Number.parseFloat(
                document.getElementById(
                  "inp-route-grinding",
                ).value,
              ) / 100,
          },
        }
      : {};

  return {
    cycle_band:
      document.getElementById(
        "inp-cycles",
      ).value,

    process:
      document.getElementById(
        "inp-process",
      ).value,

    expected_cycles:
      Number(
        document.getElementById(
          "inp-expected-cycles",
        ).value,
      ),

    workpiece_material:
      document.getElementById(
        "inp-workpiece-material",
      ).value,

    material_thickness_mm:
      Number.parseFloat(
        document.getElementById(
          "inp-material-thickness",
        ).value,
      ),

    tolerance_level:
      document.getElementById(
        "inp-tolerance",
      ).value,

    surface_finish:
      document.getElementById(
        "inp-surface-finish",
      ).value,

    abrasive_material:
      document.getElementById(
        "inp-abrasive",
      ).value === "true",

    corrosive_environment:
      document.getElementById(
        "inp-corrosive",
      ).value === "true",

    parts_per_mold:
      Number.parseInt(
        document.getElementById(
          "inp-pqty",
        ).value,
        10,
      ),

    manufacturing_country:
      document.getElementById(
        "inp-country",
      ).value,

    truck_distance_km:
      Number.parseFloat(
        document.getElementById(
          "inp-truck",
        ).value,
      ),

    sea_distance_nm:
      Number.parseFloat(
        document.getElementById(
          "inp-sea",
        ).value,
      ),

    includes_cooling:
      document.getElementById(
        "inp-cooling",
      ).value === "true",

    part: {
      length_mm:
        Number.parseFloat(
          document.getElementById(
            "inp-l",
          ).value,
        ),

      width_mm:
        Number.parseFloat(
          document.getElementById(
            "inp-w",
          ).value,
        ),

      height_mm:
        Number.parseFloat(
          document.getElementById(
            "inp-h",
          ).value,
        ),
    },

    assumptions: {
      engineering_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-engineering-rate",
          ).value,
        ),

      assembly_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-assembly-rate",
          ).value,
        ),

      cnc_3_axis_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-cnc3-rate",
          ).value,
        ),

      cnc_5_axis_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-cnc5-rate",
          ).value,
        ),

      edm_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-edm-rate",
          ).value,
        ),

      grinding_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-grinding-rate",
          ).value,
        ),

      electricity_eur_kwh:
        Number.parseFloat(
          document.getElementById(
            "inp-electricity",
          ).value,
        ),

      machine_efficiency:
        Number.parseFloat(
          document.getElementById(
            "inp-machine-efficiency",
          ).value,
        ) / 100,

      operator_efficiency:
        Number.parseFloat(
          document.getElementById(
            "inp-operator-efficiency",
          ).value,
        ) / 100,

      overhead_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-overhead-rate",
          ).value,
        ) / 100,

      margin_rate:
        Number.parseFloat(
          document.getElementById(
            "inp-margin-rate",
          ).value,
        ) / 100,
    },

    ...toolingData,
  };
}


/* =========================================================
   Validation
   ========================================================= */

function validateState(state) {
  if (
    !Number.isInteger(
      state.expected_cycles,
    ) ||
    state.expected_cycles <= 0
  ) {
    throw new Error(
      WorkbookUI.current() ? "Lifetime quantity must be a positive whole number." : "Expected cycles must be a positive whole number.",
    );
  }

  if (!state.workpiece_material) {
    throw new Error(
      "Please select a workpiece material.",
    );
  }

  if (
    !Number.isFinite(
      state.material_thickness_mm,
    ) ||
    state.material_thickness_mm <= 0
  ) {
    throw new Error(
      "Material thickness must be greater than zero.",
    );
  }

  if (
    !Number.isFinite(
      state.part.length_mm,
    ) ||
    state.part.length_mm <= 0
  ) {
    throw new Error(
      "Part length must be greater than zero.",
    );
  }

  if (
    !Number.isFinite(
      state.part.width_mm,
    ) ||
    state.part.width_mm <= 0
  ) {
    throw new Error(
      "Part width must be greater than zero.",
    );
  }

  if (
    !Number.isFinite(
      state.part.height_mm,
    ) ||
    state.part.height_mm <= 0
  ) {
    throw new Error(
      "Part height must be greater than zero.",
    );
  }

  if (
    !Number.isFinite(
      state.truck_distance_km,
    ) ||
    state.truck_distance_km < 0
  ) {
    throw new Error(
      "Truck distance cannot be negative.",
    );
  }

  if (
    !Number.isFinite(
      state.sea_distance_nm,
    ) ||
    state.sea_distance_nm < 0
  ) {
    throw new Error(
      "Sea distance cannot be negative.",
    );
  }

  if (
    !Number.isInteger(
      state.parts_per_mold,
    ) ||
    state.parts_per_mold < 1 ||
    state.parts_per_mold > 30
  ) {
    throw new Error(
      WorkbookUI.current() ? "Tool sets must be a whole number from 1 to 30." : "Parts per mold must be a whole number from 1 to 30.",
    );
  }


  /* Country cost assumptions */

  const assumptions =
    state.assumptions;

  if (!assumptions) {
    throw new Error(
      "Manufacturing cost assumptions are missing.",
    );
  }

  const positiveFields = [
    [
      "Engineering rate",
      assumptions.engineering_rate,
    ],
    [
      "Assembly rate",
      assumptions.assembly_rate,
    ],
    [
      "CNC 3-axis rate",
      assumptions.cnc_3_axis_rate,
    ],
    [
      "CNC 5-axis rate",
      assumptions.cnc_5_axis_rate,
    ],
    [
      "Electro-Discharge Machining rate",
      assumptions.edm_rate,
    ],
    [
      "Grinding rate",
      assumptions.grinding_rate,
    ],
    [
      "Electricity price",
      assumptions.electricity_eur_kwh,
    ],
  ];

  positiveFields.forEach(
    ([label, value]) => {
      if (
        !Number.isFinite(value) ||
        value <= 0
      ) {
        throw new Error(
          `${label} must be greater than zero.`,
        );
      }
    },
  );


  /* Efficiency */

  if (
    !Number.isFinite(
      assumptions.machine_efficiency,
    ) ||
    assumptions.machine_efficiency <= 0 ||
    assumptions.machine_efficiency > 1
  ) {
    throw new Error(
      "Machine efficiency must be between 1% and 100%.",
    );
  }

  if (
    !Number.isFinite(
      assumptions.operator_efficiency,
    ) ||
    assumptions.operator_efficiency <= 0 ||
    assumptions.operator_efficiency > 1
  ) {
    throw new Error(
      "Operator efficiency must be between 1% and 100%.",
    );
  }


  /* Commercial assumptions */

  if (
    !Number.isFinite(
      assumptions.overhead_rate,
    ) ||
    assumptions.overhead_rate < 0 ||
    assumptions.overhead_rate > 1
  ) {
    throw new Error(
      "Overhead must be between 0% and 100%.",
    );
  }

  if (
    !Number.isFinite(
      assumptions.margin_rate,
    ) ||
    assumptions.margin_rate < 0 ||
    assumptions.margin_rate > 1
  ) {
    throw new Error(
      "Supplier margin must be between 0% and 100%.",
    );
  }


  /* Tooling material assumptions */

  if (
    state.tooling_material_assumptions
  ) {
    const tooling =
      state.tooling_material_assumptions;

    if (
      !Number.isFinite(
        tooling.density_kg_m3,
      ) ||
      tooling.density_kg_m3 <= 0
    ) {
      throw new Error(
        "Tooling density must be greater than zero.",
      );
    }

    if (
      !Number.isFinite(
        tooling.block_price_per_tonne,
      ) ||
      tooling.block_price_per_tonne <= 0
    ) {
      throw new Error(
        "Tooling material price must be greater than zero.",
      );
    }

    if (
      !Number.isFinite(
        tooling.removal_rate_cm3_min,
      ) ||
      tooling.removal_rate_cm3_min <= 0
    ) {
      throw new Error(
        "Removal rate must be greater than zero.",
      );
    }

    if (
      !Number.isFinite(
        tooling.milling_volume_factor,
      ) ||
      tooling.milling_volume_factor <= 0
    ) {
      throw new Error(
        "Milling volume factor must be greater than zero.",
      );
    }

    if (
      !Number.isFinite(
        tooling.milling_tool_price,
      ) ||
      tooling.milling_tool_price < 0
    ) {
      throw new Error(
        "Milling tool price cannot be negative.",
      );
    }

    if (
      !Number.isFinite(
        tooling.heat_treatment_eur_per_kg,
      ) ||
      tooling.heat_treatment_eur_per_kg < 0
    ) {
      throw new Error(
        "Heat treatment cost cannot be negative.",
      );
    }
  }


  /* Manufacturing route */

  if (state.manufacturing_route) {
    const route =
      state.manufacturing_route;

    const routeFields = [
      [
        "CNC 3-axis share",
        route.cnc_3_axis_share,
      ],
      [
        "CNC 5-axis share",
        route.cnc_5_axis_share,
      ],
      [
        "Electro-Discharge Machining share",
        route.edm_share,
      ],
      [
        "Grinding share",
        route.grinding_share,
      ],
    ];

    routeFields.forEach(
      ([label, value]) => {
        if (
          !Number.isFinite(value) ||
          value < 0 ||
          value > 1
        ) {
          throw new Error(
            `${label} must be between 0% and 100%.`,
          );
        }
      },
    );

    const routeTotal =
      route.cnc_3_axis_share +
      route.cnc_5_axis_share +
      route.edm_share +
      route.grinding_share;

    if (
      Math.abs(
        routeTotal - 1,
      ) > 0.001
    ) {
      throw new Error(
        `Manufacturing route allocation must equal 100%. Current total: ${(routeTotal * 100).toFixed(1)}%.`,
      );
    }
  }
}


/* =========================================================
   API
   ========================================================= */

async function requestCalculation(
  state, signal,
) {
  const response = await fetch(
    `${API_BASE_URL}/api/calculate`,
    {
      method: "POST",
      signal,

      headers: {
        "Content-Type":
          "application/json",
      },

      body:
        JSON.stringify(state),
    },
  );

  if (!response.ok) {
    let errorMessage =
      `Calculation failed (${response.status}).`;

    try {
      const errorBody =
        await response.json();

      if (errorBody.detail) {
        errorMessage =
          typeof errorBody.detail ===
          "string"
            ? errorBody.detail
            : JSON.stringify(
                errorBody.detail,
              );
      }
    } catch {
      // Keep default error message.
    }

    throw new Error(
      errorMessage,
    );
  }

  return response.json();
}


/* =========================================================
   Result rendering
   ========================================================= */

async function renderResult(
  result,
) {
  document.getElementById(
    "out-c12",
  ).textContent =
    result.tooling_material;

  document.getElementById(
    "out-c13",
  ).textContent =
    `${fmt(
      result.gross_length_mm,
      0,
    )} × ` +
    `${fmt(
      result.gross_width_mm,
      0,
    )} × ` +
    `${fmt(
      result.gross_height_mm,
      0,
    )} mm`;

  const rows = [
    ["Machined blocks", result.total_machined_blocks || result.tooling_blocks?.reduce((sum, b) => sum + b.pieces, 0), "number"],
    ["Purchased assemblies", result.total_purchased_assemblies, "number"],
    ["Purchased assembly quotes", result.purchased_assemblies_cost, "money"],
    [
      "Tooling weight [kg]",
      result.tooling_weight_kg,
      "number",
    ],

    [
      "Quantity band",
      result.tooling_quantity_band,
      "text",
    ],

    [
      "Tooling concept",
      result.tooling_concept,
      "text",
    ],

    [
      "Outside machining volume [m³]",
      result.outside_machining_volume_m3,
      "number",
    ],

    [
      "Inside machining volume [m³]",
      result.inside_machining_volume_m3,
      "number",
    ],

    [
      "Milling time index",
      result.milling_time_index,
      "number",
    ],

    [
      "Volume removed / tool lifetime [min]",
      result.removed_volume_time_min,
      "number",
    ],

    [
      "Tooling material cost",
      result.material_cost,
      "money",
    ],

    [
      "Raw material transformation cost",
      result.transformation_cost,
      "money",
    ],

    [
      "Outside machining cost",
      result.outside_machining_cost,
      "money",
    ],

    [
      "Inside machining cost",
      result.inside_machining_cost,
      "money",
    ],

    [
      "Milling tool cost",
      result.milling_tool_cost,
      "money",
    ],

    [
      "Heat treatment cost",
      result.heat_treatment_cost,
      "money",
    ],

    ["Construction hours (programming, finishing, EDM, fitting) [h]", result.construction_hours, "number"],
    ["Construction cost", result.construction_cost, "money"],
    ["Working components subtotal", result.working_components_cost, "money"],
    [result.standard_parts_note || "Tool base and standard parts", result.standard_parts_cost, "money"],
    ["Cooling system cost", result.cooling_cost, "money"],
    ["Design and engineering [h]", result.design_hours, "number"],
    ["Design and engineering", result.design_cost, "money"],
    ["Assembly and tryout", result.assembly_tryout_cost, "money"],
    ["Machine energy", result.energy_cost, "money"],
    ["Overhead", result.overhead_cost, "money"],
    ["Supplier margin", result.margin, "money"],
    ["Transport & packaging", result.transport_cost, "money"],
  ];

  const tbody =
    document.querySelector(
      "#out-main tbody",
    );

  tbody.innerHTML = rows
    .map(
      ([label, value, type]) => `
        <tr>
          <th>${label}</th>

          <td class="num">
            ${
              type === "money"
                ? money(value)
                : type === "text"
                  ? WorkbookUI.escape(value || "—")
                  : fmt(value)
            }
          </td>
        </tr>
      `,
    )
    .join("");

  renderToolingBlocks(result);
  WorkbookUI.render(result);

  // Whole currency units: cents would be false precision for an estimate.
  document.getElementById("out-total").textContent = fmt(result.total_price * currencyFactor(), 0);
  document.getElementById("out-range").textContent =
    `Likely range ${money0(result.total_price * 0.8)} – ${money0(result.total_price * 1.3)}`;

  await renderRecommendation(
    result,
  );
}

function renderToolingBlocks(result) {
  document.getElementById("tooling-sizing-basis").textContent =
    result.tooling_sizing_basis || "No sizing explanation available.";

  const tbody = document.querySelector("#out-blocks tbody");
  const blocks = result.tooling_blocks || [];

  if (!blocks.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5">No tooling block sizing available.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = blocks
    .map((block) => `
      <tr>
        <td>
          <strong>${WorkbookUI.escape(block.component || "—")}</strong>
          <span>${WorkbookUI.escape(block.assumption || "")}</span>
        </td>
        <td>${WorkbookUI.escape(block.role || "—")}</td>
        <td class="num">${block.pieces ?? "—"}</td>
        <td class="num"><strong class="stock-size">${WorkbookUI.escape(block.raw_stock || "—")}</strong>
          <span>${block.finished_length_mm == null ? "" : "Finished envelope: " + (block.stock_form === "Round billet" ? "Diameter " : "") + [block.finished_length_mm, block.finished_width_mm, block.finished_height_mm].filter(v => v != null).map(v => fmt(v, 1)).join(" x ") + " mm"}</span>
          <span>${block.cost_before_commercial == null ? (block.purchased ? "Quote required" : "") : money(block.cost_before_commercial) + " before overhead and margin"}</span></td>
        <td>
          <strong>${WorkbookUI.escape(block.material_note || "—")}</strong>
          <span>${WorkbookUI.escape(block.heating_cooling || "")}</span>
          <span>${WorkbookUI.escape(block.costing_material || "")}</span>
        </td>
      </tr>
    `)
    .join("");
}


/* =========================================================
   Recommendation rendering
   ========================================================= */

async function renderRecommendation(result) {
  document.getElementById("rec-material").textContent = result.recommended_material || "—";
  const confidence = result.recommendation_confidence || "unknown";
  const badge = document.getElementById("rec-confidence");
  badge.textContent = confidence === "review_required" ? "Engineering review required" : `Confidence: ${sentenceCase(confidence)}`;
  badge.dataset.level = confidence;
  document.getElementById("confidence-explanation").textContent =
    result.recommendation_confidence_explanation || ((confidence === "high"
      ? "Your inputs trigger a specific selection rule for material durability, loading, corrosion, precision or finish. "
      : "This is a general recommendation for the selected production conditions. Exact grade and geometry may change the choice. ")
    + (result.recommendation_reasons || []).map(sentenceCase).join(" "));
  const risks = document.getElementById("rec-failure-modes");
  if (risks) risks.replaceChildren();
  const modes = result.failure_modes || [];
  if (!modes.length) {
    const li = document.createElement("li");
    li.textContent = "No specific elevated risk was identified by these rules. This does not mean production is risk-free.";
    risks?.append(li);
  }
  modes.forEach(mode => {
    const li = document.createElement("li");
    const strong = document.createElement("strong");
    strong.textContent = `${sentenceCase(mode)}: `;
    li.append(strong, document.createTextNode(RISK_HELP[mode] || "Review this risk against your tooling design and production conditions."));
    risks?.append(li);
  });
  renderList("rec-reasons", result.recommendation_reasons, "No selection reasons available.");
  renderList("rec-operations", result.recommended_operations, "No tooling manufacturing route available.");
}

function renderList(id, items, emptyMessage) {
  const element = document.getElementById(id);
  element.replaceChildren();
  (items?.length ? items : [emptyMessage]).forEach(item => {
    const li = document.createElement("li");
    li.textContent = sentenceCase(item);
    element.append(li);
  });
}

function setLoading(
  isLoading,
) {
  const button =
    document.getElementById(
      "calculate-btn",
    );

  button.disabled =
    isLoading;

  button.textContent =
    isLoading
      ? "Calculating..."
      : "Calculate tooling cost";
}


function setStatus(
  message,
  isError = false,
) {
  const status =
    document.getElementById(
      "calc-status",
    );

  status.textContent =
    message;
  document.getElementById("logistics-status").textContent = message;

  status.classList.toggle(
    "err",
    isError,
  );
}


/* =========================================================
   Calculate
   ========================================================= */

async function calculateAndRender() {
  clearTimeout(calculationTimer);
  const revision = ++inputRevision;
  activeCalculation?.abort();
  const controller = new AbortController();
  activeCalculation = controller;
  try {
    if (countryLoading) throw new Error("Wait for country defaults to finish loading.");
    if (!currentCountryDefaults || currentCountryDefaults.code !== document.getElementById("inp-country").value)
      throw new Error("Country defaults are unavailable. Select the country again.");
    if (!currencyFactor()) {
      // Point the visitor at the field: open Assumptions on the currency section.
      document.getElementById("assumptions").open = true;
      throw new Error(ecbRate
        ? "Enter a positive EUR/USD exchange rate and its date (Assumptions → Currency) to calculate in USD."
        : "The exchange rate could not be loaded. Enter a EUR/USD rate and its date under Assumptions → Currency to calculate in USD.");
    }
    const state = readState();
    validateState(state);
    validateLogistics(state.logistics);
    setLoading(true);
    markStale("Updating estimate…");
    setStatus("Updating estimate…");
    const {result, report} = await ReportUI.request(state, controller.signal);
    if (revision !== inputRevision) return;
    const targetFamily = forcedFamily || result.recommended_material_family;
    const familyChanged = currentToolingMaterialFamily !== targetFamily;
    const hadFamily = Boolean(currentToolingMaterialFamily);
    let profile;
    if (familyChanged) {
      const response = await fetch(`${API_BASE_URL}/api/tooling-materials/${targetFamily}`, {signal: controller.signal});
      if (!response.ok) throw new Error("Could not load the recommended tooling defaults.");
      profile = await response.json();
    }
    if (revision !== inputRevision) return;
    if (profile) {
      currentToolingDefaults = profile;
      currentToolingMaterialFamily = targetFamily;
      applyToolingMaterialDefaults(profile);
    }
    await renderResult(result);
    if (revision !== inputRevision) return;
    ReportUI.render(report, state);
    hasCalculated = true;
    AdvancedUI.onResult(result, report, state);
    const badge = document.getElementById("estimate-state");
    badge.textContent = "Up to date";
    badge.dataset.stale = "false";
    document.getElementById("freight-breakdown").textContent =
      `Road freight: ${money(result.road_transport_cost)} · Sea freight: ${money(result.sea_transport_cost)} · Total freight: ${money(result.transport_cost)}`;
    setStatus(familyChanged && hadFamily
      ? "Recommended material changed. Tooling defaults have been updated."
      : "Estimate updated. Further edits recalculate automatically.");
  } catch (error) {
    if (revision !== inputRevision || error.name === "AbortError") return;
    markStale(hasCalculated ? "Estimate out of date" : "Not calculated");
    setStatus(error.message || "Unable to calculate tooling cost.", true);
  } finally {
    if (revision === inputRevision) setLoading(false);
  }
}

function setupTabs() {
  document
    .querySelectorAll(
      "nav.tabs button",
    )
    .forEach(
      (button) => {
        button.addEventListener(
          "click",
          () => {
            const tab =
              button.dataset.tab;

            document
              .querySelectorAll(
                "nav.tabs button",
              )
              .forEach(
                (item) => {
                  item.setAttribute(
                    "aria-selected",
                    item.dataset.tab ===
                      tab,
                  );
                },
              );

            document
              .querySelectorAll(
                ".panel",
              )
              .forEach(
                (panel) => {
                  panel.classList.toggle(
                    "active",
                    panel.id ===
                      `panel-${tab}`,
                  );
                },
              );
          },
        );
      },
    );
}


/* =========================================================
   Events
   ========================================================= */

function setupEvents() {
  document.getElementById("calculate-btn").addEventListener("click", calculateAndRender);
  document.getElementById("inp-process").addEventListener("change", () => {
    currentToolingMaterialFamily = null;
    currentToolingDefaults = null;
    forcedFamily = null;
    updateWorkpieceMaterials();
    WorkbookUI.onProcessChange();
    syncLegacyBand();
  });
  document.getElementById("inp-cycles").addEventListener("change", syncExpectedCycles);
  document.getElementById("inp-expected-cycles").addEventListener("input", syncLegacyBand);
  document.getElementById("inp-country").addEventListener("change", async event => {
    try { await loadCountryDefaults(event.target.value); }
    catch (error) { setStatus(error.message, true); }
  });
  document.getElementById("reset-country-defaults").addEventListener("click", () => {
    if (currentCountryDefaults) {
      applyCountryDefaults(currentCountryDefaults);
      scheduleCalculation();
    }
  });
  document.getElementById("reset-tooling-defaults").addEventListener("click", () => {
    if (currentToolingDefaults) {
      applyToolingMaterialDefaults(currentToolingDefaults);
      scheduleCalculation();
    }
  });
  document.getElementById("inp-material-detail").addEventListener("change", () => {
    ProcessMatrix.syncWorkpiece("inp-material-detail", "inp-workpiece-material");
  });
  document.getElementById("fx-reset").addEventListener("click", () => {
    captureMoney();
    applyEcbRate(true);
    updateCurrencyDisplay();
    updateCountryFlags();
    scheduleCalculation();
  });
  document.getElementById("reset-logistics").addEventListener("click", () => {
    restoreLogistics();
    scheduleCalculation();
  });
  document.querySelectorAll("input, select").forEach(element => {
    // The drawing tab manages its own fields and forwards changes to Overview.
    if (element.type === "file" || element.closest("#panel-drawing")) return;
    if (element.type === "number") {
      element.step = "1";
      // Zero-based steps keep native arrows on whole units; decimal typing stays supported.
      if (Number(element.min) > 0 && Number(element.min) < 1) element.min = "0";
    }
    const eventName = element.tagName === "SELECT" ? "change" : "input";
    element.addEventListener(eventName, () => {
      if (element.id === "inp-country") return;
      if (element.id === "inp-fx" || element.id === "inp-fx-date") {
        fxEdited = true;
        captureMoney();
        updateCurrencyDisplay();
      } else if (MONEY_FIELDS.includes(element.id) && fieldFactor(element.id)) {
        canonicalMoney[element.id] = Number(element.value) / fieldFactor(element.id);
      }
      updateCountryFlags();
      updateRouteTotal();
      scheduleCalculation();
    });
  });
}

async function init() {
  try {
    fillSelect(
      "inp-cycles",
      LISTS.cycles,
    );

    fillSelect(
      "inp-process",
      LISTS.processes,
    );

    fillSelect(
      "inp-pqty",
      LISTS.partsPerMold,
    );

    fillSelect(
      "inp-cooling",
      LISTS.cooling,
    );


    /* Default test case */

    document.getElementById(
      "inp-cycles",
    ).value =
      "100000_to_250000";

    document.getElementById(
      "inp-process",
    ).value =
      "stamping";

    document.getElementById(
      "inp-pqty",
    ).value =
      "2";

    document.getElementById(
      "inp-expected-cycles",
    ).value =
      "150000";

    document.getElementById(
      "inp-material-thickness",
    ).value =
      "3";

    document.getElementById(
      "inp-tolerance",
    ).value =
      "high_precision";

    document.getElementById(
      "inp-surface-finish",
    ).value =
      "standard";

    document.getElementById(
      "inp-abrasive",
    ).value =
      "false";

    document.getElementById(
      "inp-corrosive",
    ).value =
      "false";

    document.getElementById(
      "inp-truck",
    ).value =
      "1700";

    document.getElementById(
      "inp-sea",
    ).value =
      String(19800 / 1.852);

    document.getElementById(
      "inp-cooling",
    ).value =
      "false";

    document.getElementById(
      "inp-l",
    ).value =
      "300";

    document.getElementById(
      "inp-w",
    ).value =
      "300";

    document.getElementById(
      "inp-h",
    ).value =
      "40";


    /* Process-specific materials */

    updateWorkpieceMaterials();

    document.getElementById(
      "inp-workpiece-material",
    ).value =
      "advanced_high_strength_steel";


    /* Countries */

    setStatus(
      "Loading manufacturing benchmarks...",
    );

    await loadCountries();

    document.getElementById(
      "inp-country",
    ).value =
      "DE";

    await loadCountryDefaults(
      "DE",
    );

    await WorkbookUI.init();
    try {
      await ProcessMatrix.load();
      ProcessMatrix.fill("inp-material-detail");
    } catch {
      // Route advice still uses the automatic mapping on the server.
    }
    document.getElementById("inp-process").value = "die_casting";
    WorkbookUI.onProcessChange();


    /* Events */

    setupEvents();
    setupDrawingImport();

    setupTabs();

    // A link from the quick-price page carries the part and calculates straight away.
    AdvancedUI.init();
    // Results first: calculate the default (or linked) part straight away.
    if (!(await ReportUI.applyUrlPrefill())) {
      setStatus("Ready to calculate.");
      await calculateAndRender();
    }
  } catch (error) {
    console.error(
      error,
    );

    setStatus(
      error.message ||
        "Unable to initialize calculator.",
      true,
    );
  }
}


/* =========================================================
   Start
   ========================================================= */

// The API's monetary contract remains EUR. Currency conversion is an explicit view layer.
const COUNTRY_FIELDS = {
  "inp-engineering-rate": "engineering_rate", "inp-assembly-rate": "assembly_rate",
  "inp-cnc3-rate": "cnc_3_axis_rate", "inp-cnc5-rate": "cnc_5_axis_rate",
  "inp-edm-rate": "edm_rate", "inp-grinding-rate": "grinding_rate",
  "inp-electricity": "electricity_eur_kwh", "inp-machine-efficiency": "machine_efficiency",
  "inp-operator-efficiency": "operator_efficiency", "inp-overhead-rate": "overhead_rate",
  "inp-margin-rate": "margin_rate"
};
const PERCENT_FIELDS = new Set(["inp-machine-efficiency", "inp-operator-efficiency", "inp-overhead-rate", "inp-margin-rate"]);
const MONEY_FIELDS = [...Object.keys(COUNTRY_FIELDS).filter(id => !PERCENT_FIELDS.has(id)),
  "inp-tool-price", "inp-milling-tool-price", "inp-heat-treatment", "road-rate", "sea-rate"];
const canonicalMoney = {"road-rate": 1400 / 250, "sea-rate": 8000 / 19800 * 1.852};
let displayCurrency = "EUR", countryCurrency = "EUR", shownFactor = 1;
// ECB reference rate loaded from the API; the visitor may override it with their own agreed rate.
let ecbRate = null, ecbRequest = null, fxEdited = false;
// Tooling family chosen with "Try this material" on a broad-process estimate.
let forcedFamily = null;
let hasCalculated = false, calculationTimer, inputRevision = 0, activeCalculation;
let countryRevision = 0, countryLoading = false;
const RISK_HELP = {
  "abrasive wear": "Abrasive material can wear tool surfaces and gradually affect part dimensions.",
  "corrosion": "Chemical attack can damage the tooling surface and affect part quality.",
  "surface degradation": "Tool surfaces can deteriorate, reducing the finish quality of produced parts.",
  "long-term wear": "Repeated production cycles can wear the tool and increase maintenance needs.",
  "dimensional drift": "Wear or deformation can gradually move parts outside their required tolerances.",
  "galling": "Workpiece material can stick to the tool, causing scratches or poor surface finish.",
  "chipping": "Small pieces can break away from tool edges under load.",
  "cracking": "Repeated or severe loads can cause cracks in the tool.",
  "plastic deformation": "High contact loads can permanently change the tool's shape.",
  "high mechanical loading": "High forces increase stress on punches, dies and forming surfaces.",
  "thermal fatigue": "Heating and cooling with every shot causes fine surface cracks (heat checking).",
  "soldering": "Molten aluminium can bond to the die steel and tear the part surface.",
  "erosion": "Fast metal flow at the gates can wash away die steel."
};
function sentenceCase(text) {
  const expanded = String(text).replace(/\bEDM\b/g, "Electro-Discharge Machining");
  return expanded.charAt(0).toUpperCase() + expanded.slice(1);
}
function currencyFactor() {
  if (displayCurrency === "EUR") return 1;
  const rate = Number(document.getElementById("inp-fx").value);
  return Number.isFinite(rate) && rate > 0 && document.getElementById("inp-fx-date").value ? rate : null;
}
function money0(euros) {
  const factor = currencyFactor();
  return factor && Number.isFinite(euros) ? `${displayCurrency === "EUR" ? "€" : "$"}${fmt(euros * factor, 0)}` : "—";
}
function money(euros) {
  const factor = currencyFactor();
  return factor && Number.isFinite(euros) ? `${displayCurrency} ${fmt(euros * factor)}` : "—";
}
/* Money fields keep their amount in their own currency: country rates in the country's
   costing currency (USD for China and India), benchmarks and freight in EUR. */
function isCountryMoney(id) {
  return id in COUNTRY_FIELDS && !PERCENT_FIELDS.has(id);
}
function fieldFactor(id) {
  return isCountryMoney(id) && countryCurrency === displayCurrency ? 1 : shownFactor;
}
function captureMoney() {
  MONEY_FIELDS.forEach(id => {
    const field = document.getElementById(id);
    const factor = fieldFactor(id);
    if (field.value !== "" && factor) canonicalMoney[id] = Number(field.value) / factor;
  });
}
function showMoneyFields(ids = MONEY_FIELDS) {
  ids.forEach(id => {
    const field = document.getElementById(id);
    const factor = fieldFactor(id);
    field.disabled = !factor;
    const base = canonicalMoney[id];
    field.value = factor && Number.isFinite(base) ? Number((base * factor).toPrecision(12)) : "";
  });
}
async function ensureEcbRate() {
  ecbRequest ||= fetchJson("/api/fx/eur-usd").then(rate => (ecbRate = rate)).catch(() => {
    ecbRequest = null; // Try again on the next country change.
    return null;
  });
  return ecbRequest;
}
function applyEcbRate(force = false) {
  if (!ecbRate || (fxEdited && !force)) return;
  document.getElementById("inp-fx").value = ecbRate.rate;
  document.getElementById("inp-fx-date").value = ecbRate.date;
  fxEdited = false;
}
function describeRate() {
  const rate = document.getElementById("inp-fx").value;
  const day = document.getElementById("inp-fx-date").value;
  const fromEcb = ecbRate && !fxEdited && Number(rate) === ecbRate.rate && day === ecbRate.date;
  document.getElementById("fx-source").textContent = fromEcb
    ? `Rate source: ${ecbRate.source}, ${ecbRate.date}${ecbRate.stale ? " (the ECB could not be reached just now, so this is the last rate loaded)" : ""}.`
    : rate && day ? `Your own rate, dated ${day}.${ecbRate ? ` The latest ECB rate is ${ecbRate.rate} (${ecbRate.date}).` : ""}`
      : "The ECB rate could not be loaded. Enter your agreed rate and its date.";
  document.getElementById("fx-reset").hidden = !ecbRate || fromEcb;
}
function updateCurrencyDisplay() {
  shownFactor = currencyFactor();
  showMoneyFields();
  document.querySelectorAll(".unit").forEach(label => {
    if (!label.dataset.eurLabel && label.textContent.includes("€")) label.dataset.eurLabel = label.textContent;
    if (label.dataset.eurLabel) label.textContent = label.dataset.eurLabel.replace("€", displayCurrency);
  });
  document.querySelector(".price-hero .currency").textContent = displayCurrency === "EUR" ? "€" : "$";
  document.getElementById("result-currency").textContent = displayCurrency;
  document.getElementById("currency-note").textContent = displayCurrency === "EUR"
    ? "This European country is costed in EUR. The rate below converts US-dollar countries in the report's country comparison."
    : shownFactor ? `This country is costed in USD: its labour and machine rates are US-dollar amounts. Tool steel, heat treatment and freight benchmarks are in EUR and are converted at 1 EUR = ${shownFactor} USD.`
      : "This country is costed in USD. Enter a EUR/USD rate and its date to continue.";
  describeRate();
  // Never relabel an old numeric result as a different currency.
  document.getElementById("out-total").textContent = "—";
  document.querySelector("#out-main tbody").replaceChildren();
  document.getElementById("freight-breakdown").textContent = "Recalculate to see freight in the selected currency.";
  updateCountryFlags();
  WorkbookUI.refresh();
}
function applyCountryDefaults(profile) {
  applyCountryDefaultsRaw(profile);
  Object.entries(COUNTRY_FIELDS).forEach(([id, key]) => {
    if (!PERCENT_FIELDS.has(id)) canonicalMoney[id] = profile[key];
  });
  showMoneyFields(Object.keys(COUNTRY_FIELDS).filter(id => !PERCENT_FIELDS.has(id)));
  updateCountryFlags();
}
function applyToolingMaterialDefaults(profile) {
  applyToolingMaterialDefaultsRaw(profile);
  canonicalMoney["inp-tool-price"] = profile.block_price_per_tonne;
  canonicalMoney["inp-milling-tool-price"] = profile.milling_tool_price;
  canonicalMoney["inp-heat-treatment"] = profile.heat_treatment_eur_per_kg;
  showMoneyFields(["inp-tool-price", "inp-milling-tool-price", "inp-heat-treatment"]);
}
function updateCountryFlags() {
  if (!currentCountryDefaults) return;
  let count = 0;
  Object.entries(COUNTRY_FIELDS).forEach(([id, key]) => {
    const field = document.getElementById(id);
    const value = PERCENT_FIELDS.has(id) ? Number(field.value) / 100 : canonicalMoney[id];
    const modified = !Number.isFinite(value) || Math.abs(value - currentCountryDefaults[key]) > 1e-8;
    field.classList.toggle("modified", modified);
    const base = currentCountryDefaults[key];
    field.title = `Country default: ${PERCENT_FIELDS.has(id) ? fmt(base * 100) + "%" : `${countryCurrency} ${fmt(base)}`}${modified ? " (modified)" : ""}`;
    if (modified) count++;
  });
  const flag = document.getElementById("country-defaults-flag");
  flag.textContent = count ? `Country defaults modified (${count})` : "Country defaults";
  flag.classList.toggle("modified", count > 0);
}
function readState() {
  const state = readStateRaw();
  const factor = currencyFactor();
  ["engineering_rate", "assembly_rate", "cnc_3_axis_rate", "cnc_5_axis_rate", "edm_rate", "grinding_rate", "electricity_eur_kwh"].forEach(key => state.assumptions[key] /= factor);
  if (state.tooling_material_assumptions) {
    ["block_price_per_tonne", "milling_tool_price", "heat_treatment_eur_per_kg"].forEach(key => state.tooling_material_assumptions[key] /= factor);
  }
  const number = id => Number.parseFloat(document.getElementById(id).value);
  state.logistics = {
    road_rate_eur_per_km: number("road-rate") / factor,
    sea_rate_eur_per_nm: number("sea-rate") / factor,
    road_load_kg: number("road-load"), sea_load_kg: number("sea-load"),
    road_journeys: number("road-journeys"), sea_journeys: number("sea-journeys"),
    allocation: document.getElementById("freight-allocation").value
  };
  const detail = document.getElementById("inp-material-detail").value;
  if (detail) state.part_material_detail = detail;
  if (forcedFamily && !WorkbookUI.current()) {
    state.tooling_material_family = forcedFamily;
    state.force_tooling_material = true;
  }
  const eurToUsd = Number(document.getElementById("inp-fx").value);
  if (Number.isFinite(eurToUsd) && eurToUsd > 0) state.eur_to_usd = eurToUsd;
  WorkbookUI.addState(state);
  return state;
}
function validateLogistics(logistics) {
  for (const [key, value] of Object.entries(logistics)) {
    if (key === "allocation") continue;
    const min = key.includes("rate") ? 0 : Number.EPSILON;
    if (!Number.isFinite(value) || value < min) throw new Error("Freight rates must be non-negative and load capacities must be positive.");
    if (key.includes("journeys") && (!Number.isInteger(value) || value < 1 || value > 100)) throw new Error("Charged journeys must be whole numbers from 1 to 100.");
  }
}
function restoreLogistics() {
  canonicalMoney["road-rate"] = 1400 / 250;
  canonicalMoney["sea-rate"] = 8000 / 19800 * 1.852;
  showMoneyFields(["road-rate", "sea-rate"]);
  document.getElementById("road-load").value = 18000;
  document.getElementById("sea-load").value = 27000;
  document.getElementById("road-journeys").value = 2;
  document.getElementById("sea-journeys").value = 2;
  document.getElementById("freight-allocation").value = "proportional";
}
/* =========================================================
   From drawing tab: upload a drawing, review the envelope, calculate
   ========================================================= */

const DRAWING_EXTENSIONS = ["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp", "gif"];
const DRAWING_MAX_BYTES = 15 * 1024 * 1024;
const DRAWING_CHECK_LABELS = {
  in_text_layer: "found in PDF text",
  not_in_text_layer: "not in PDF text: check",
  no_text_layer: "not cross-checked",
};
const drawing = {request: null, result: null, previewUrl: null, timer: null, materialChoice: null};

function setDrawingState(text) {
  document.getElementById("drawing-state").textContent = text;
}

function showDrawingSection(name) {
  for (const id of ["drawing-empty", "drawing-loading", "drawing-error", "drawing-fields"]) {
    document.getElementById(id).hidden = id !== `drawing-${name}`;
  }
}

/* --- Settings shared with Overview -------------------------------- */

function syncDrawingMirrors() {
  document.querySelectorAll("#panel-drawing [data-mirror]").forEach(element => {
    const source = document.getElementById(element.dataset.mirror);
    if (element.tagName === "SELECT") element.innerHTML = source.innerHTML;
    element.value = source.value;
  });
  document.querySelectorAll("#panel-drawing [data-label-from]").forEach(label => {
    label.textContent = document.getElementById(label.dataset.labelFrom).textContent;
  });
  const material = document.getElementById("drawing-material");
  const overviewMaterial = document.getElementById("inp-workpiece-material");
  material.innerHTML = overviewMaterial.innerHTML;
  const available = [...material.options].some(option => option.value === drawing.materialChoice);
  material.value = available ? drawing.materialChoice : overviewMaterial.value;
  updateDrawingMaterialSource();
}

function setupDrawingMirrors() {
  document.querySelectorAll("#panel-drawing [data-mirror]").forEach(element => {
    const source = document.getElementById(element.dataset.mirror);
    const eventName = element.tagName === "SELECT" ? "change" : "input";
    element.addEventListener(eventName, () => {
      source.value = element.value;
      source.dispatchEvent(new Event(eventName, {bubbles: true}));
      // Process changes rebuild other Overview lists (quantity bands, materials).
      syncDrawingMirrors();
      setTimeout(syncDrawingMirrors, 0);
      markDrawingCostStale();
    });
    source.addEventListener(eventName, () => setTimeout(syncDrawingMirrors, 0));
  });
  document.getElementById("inp-workpiece-material").addEventListener("change", () => setTimeout(syncDrawingMirrors, 0));
  document.getElementById("drawing-material").addEventListener("change", event => {
    drawing.materialChoice = event.target.value;
    updateDrawingMaterialSource();
    markDrawingCostStale();
  });
}

/* --- Upload --------------------------------------------------------- */

function drawingFileProblem(file) {
  const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
  const knownType = file.type === "application/pdf" || file.type.startsWith("image/");
  if (!DRAWING_EXTENSIONS.includes(extension) && !knownType) {
    return `"${file.name}" is not a supported drawing. Use PDF, PNG, JPG, WEBP, TIFF, BMP or GIF.`;
  }
  if (file.size > DRAWING_MAX_BYTES) return `"${file.name}" is larger than 15 MB.`;
  if (file.size === 0) return `"${file.name}" is empty.`;
  return null;
}

function showDrawingPreview(file) {
  if (drawing.previewUrl) URL.revokeObjectURL(drawing.previewUrl);
  drawing.previewUrl = URL.createObjectURL(file);
  const frame = document.getElementById("drawing-preview-frame");
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  const fallback = () => {
    frame.innerHTML = `<p class="preview-fallback">Preview not available for this file type in your browser. It can still be read.</p>`;
  };
  if (isPdf) {
    frame.innerHTML = `<iframe title="Drawing preview" src="${drawing.previewUrl}#toolbar=0&amp;view=Fit"></iframe>`;
  } else {
    const image = new Image();
    image.alt = "Drawing preview";
    image.onerror = fallback;
    image.src = drawing.previewUrl;
    frame.replaceChildren(image);
  }
  document.getElementById("drawing-file-name").textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  document.getElementById("drawing-preview").hidden = false;
  document.getElementById("drop-zone").classList.add("compact");
}

async function readDrawing(file) {
  const uploadError = document.getElementById("drawing-upload-error");
  const problem = drawingFileProblem(file);
  // A rejected file leaves the current drawing and its values untouched.
  uploadError.textContent = problem || "";
  uploadError.hidden = !problem;
  if (problem) return;
  drawing.request?.abort();
  const controller = new AbortController();
  drawing.request = controller;
  drawing.result = null;
  showDrawingPreview(file);
  showDrawingSection("loading");
  setDrawingState("Reading…");
  document.getElementById("drawing-calc-btn").disabled = true;
  document.getElementById("drawing-cost").hidden = true;
  document.getElementById("drawing-calc-status").textContent = "Waiting for the drawing to be read.";
  const started = Date.now();
  const loadingText = document.getElementById("drawing-loading-text");
  const tick = () => {
    loadingText.textContent = `Reading dimensions from ${file.name}… ${Math.round((Date.now() - started) / 1000)} s (usually 15–40 s)`;
  };
  tick();
  clearInterval(drawing.timer);
  drawing.timer = setInterval(tick, 1000);
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const response = await fetch(`${API_BASE_URL}/api/extract-dimensions`, {method: "POST", body: form, signal: controller.signal});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 404) throw new Error("This server does not support drawing import yet.");
      throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`);
    }
    if (drawing.request !== controller) return;
    drawing.result = body;
    renderDrawingResult(body);
  } catch (error) {
    if (error.name === "AbortError" || drawing.request !== controller) return;
    showDrawingSection("error");
    document.getElementById("drawing-error").textContent = `Could not read the drawing: ${error.message}`;
    setDrawingState("Failed");
    document.getElementById("drawing-calc-status").textContent = "Upload a drawing first, or enter dimensions under Manual input.";
  } finally {
    if (drawing.request === controller) {
      drawing.request = null;
      clearInterval(drawing.timer);
    }
  }
}

/* --- Review --------------------------------------------------------- */

function dimensionSourceHtml(dimension, fallback) {
  if (!dimension) return `<span class="missing">${fallback}</span>`;
  const printed = dimension.unit === "inch" ? `${dimension.as_printed} in → ${fmt(dimension.value_mm, 2)} mm` : `${dimension.as_printed} mm`;
  return `${escapeHtml(printed)} <span class="check-badge" data-check="${dimension.check}">${DRAWING_CHECK_LABELS[dimension.check]}</span>`
    + (dimension.evidence ? `<span class="evidence">${escapeHtml(dimension.evidence)}</span>` : "");
}

function updateDrawingMaterialSource() {
  const source = document.getElementById("drawing-material-source");
  const material = drawing.result?.material;
  if (!drawing.result) { source.textContent = ""; return; }
  if (!material) { source.innerHTML = `<span class="missing">Not stated on the drawing. Choose it by hand.</span>`; return; }
  const select = document.getElementById("drawing-material");
  const matched = material.workpiece_material && select.value === material.workpiece_material;
  source.innerHTML = `Drawing says <strong>${escapeHtml(material.as_printed)}</strong>`
    + (matched ? "" : ` <span class="check-badge" data-check="not_in_text_layer">choose the closest option</span>`);
}

function renderDrawingResult(result) {
  const round = value => Math.round(value * 100) / 100;
  for (const [key, id] of [["length", "l"], ["width", "w"], ["height", "h"]]) {
    document.getElementById(`drawing-${id}`).value = result[key] ? round(result[key].value_mm) : "";
    document.getElementById(`drawing-${id}-source`).innerHTML = dimensionSourceHtml(result[key], "Not dimensioned on the drawing. Enter it by hand.");
  }
  const thickness = document.getElementById("drawing-t");
  thickness.value = result.wall_thickness ? round(result.wall_thickness.value_mm) : document.getElementById("inp-material-thickness").value;
  document.getElementById("drawing-t-source").innerHTML = dimensionSourceHtml(result.wall_thickness, "Not a thin-walled part on the drawing; current Manual input value kept.");

  drawing.materialChoice = result.material?.workpiece_material || null;
  syncDrawingMirrors();

  document.getElementById("drawing-part-name").textContent =
    [result.part_name, result.shape !== "other" ? `${result.shape} part` : null].filter(Boolean).join(" · ");
  document.getElementById("drawing-warnings").innerHTML = result.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join("");
  document.getElementById("drawing-all-dims-summary").textContent = `All dimensions read (${result.dimensions_read.length})`;
  document.getElementById("drawing-all-dims").innerHTML = result.dimensions_read.map(d =>
    `<tr><td class="mono">${escapeHtml(d.printed)}</td><td>${escapeHtml(d.unit)}</td><td>${escapeHtml(d.view)}</td>`
    + `<td>${escapeHtml(d.measures)}</td><td><span class="check-badge" data-check="${d.check}">${DRAWING_CHECK_LABELS[d.check]}</span></td></tr>`
  ).join("") || `<tr><td colspan="5">The model did not list individual dimensions.</td></tr>`;
  document.getElementById("drawing-model").textContent =
    `Read by ${result.model} from ${result.source_kind === "pdf" ? `a ${result.pages}-page PDF` : "an image"}. Check each value against the drawing before relying on the estimate.`;

  showDrawingSection("fields");
  const complete = Boolean(result.length && result.width && result.height);
  setDrawingState(complete ? "Review values" : "Values missing");
  document.getElementById("drawing-calc-btn").disabled = false;
  document.getElementById("drawing-calc-status").textContent = complete
    ? "Check the values, choose the process and quantity, then calculate."
    : "Enter the missing dimensions, then calculate.";
}

function markDrawingCostStale() {
  const cost = document.getElementById("drawing-cost");
  if (!cost.hidden) {
    cost.classList.add("stale");
    document.getElementById("drawing-calc-status").textContent = "Values changed. Calculate again to update the price.";
  }
}

/* --- Calculate ------------------------------------------------------ */

function setOverviewField(id, value) {
  const element = document.getElementById(id);
  element.value = value;
  element.dispatchEvent(new Event(element.tagName === "SELECT" ? "change" : "input", {bubbles: true}));
}

async function calculateFromDrawing() {
  const status = document.getElementById("drawing-calc-status");
  const values = {};
  for (const [id, label] of [["l", "Length"], ["w", "Width"], ["h", "Height"], ["t", "Wall / material thickness"]]) {
    const value = Number.parseFloat(document.getElementById(`drawing-${id}`).value);
    if (!Number.isFinite(value) || value <= 0) {
      status.textContent = `${label} must be greater than zero.`;
      status.classList.add("err");
      document.getElementById(`drawing-${id}`).focus();
      return;
    }
    values[id] = value;
  }
  status.classList.remove("err");

  // Drawing values describe a custom part, never the workbook's reference example.
  const sizingMode = document.getElementById("inp-sizing-mode");
  if (sizingMode.value === "reference") setOverviewField("inp-sizing-mode", "part_scaled");
  setOverviewField("inp-l", values.l);
  setOverviewField("inp-w", values.w);
  setOverviewField("inp-h", values.h);
  setOverviewField("inp-material-thickness", values.t);
  const material = document.getElementById("drawing-material").value;
  if (material) setOverviewField("inp-workpiece-material", material);

  const button = document.getElementById("drawing-calc-btn");
  button.disabled = true;
  status.textContent = "Calculating…";
  try {
    await calculateAndRender();
  } finally {
    button.disabled = false;
  }
  const badge = document.getElementById("estimate-state");
  const overviewStatus = document.getElementById("calc-status");
  const cost = document.getElementById("drawing-cost");
  if (badge.dataset.stale !== "false") {
    status.textContent = overviewStatus.textContent || "The estimate could not be calculated.";
    status.classList.toggle("err", overviewStatus.classList.contains("err"));
    cost.hidden = true;
    return;
  }
  document.getElementById("drawing-cost-currency").textContent = document.querySelector(".price-hero .currency").textContent;
  document.getElementById("drawing-cost-total").textContent = document.getElementById("out-total").textContent;
  document.getElementById("drawing-cost-detail").textContent =
    `${fmt(values.l, 1)} × ${fmt(values.w, 1)} × ${fmt(values.h, 1)} mm · ${document.getElementById("inp-process").selectedOptions[0]?.textContent || ""} · Tooling material: ${document.getElementById("out-c12").textContent}`;
  document.getElementById("drawing-cost-scope").textContent = document.getElementById("estimate-scope").textContent;
  cost.classList.remove("stale");
  cost.hidden = false;
  setDrawingState("Estimated");
  status.textContent = "Estimate updated. The full breakdown and production report are under Manual input.";
}

function setupDrawingImport() {
  const input = document.getElementById("drawing-file");
  const zone = document.getElementById("drop-zone");
  const browse = () => input.click();
  zone.addEventListener("click", browse);
  zone.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); browse(); }
  });
  document.getElementById("drawing-replace").addEventListener("click", browse);
  input.addEventListener("change", () => {
    const file = input.files[0];
    input.value = "";
    if (file) readDrawing(file);
  });
  let dragDepth = 0;
  zone.addEventListener("dragenter", event => { event.preventDefault(); dragDepth++; zone.classList.add("dragging"); });
  zone.addEventListener("dragover", event => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; });
  zone.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; zone.classList.remove("dragging"); } });
  zone.addEventListener("drop", event => {
    event.preventDefault();
    dragDepth = 0;
    zone.classList.remove("dragging");
    const file = event.dataTransfer.files[0];
    if (file) readDrawing(file);
  });
  // A file dropped anywhere else would make the browser navigate away and lose all inputs.
  for (const type of ["dragover", "drop"]) {
    window.addEventListener(type, event => {
      if (event.dataTransfer?.types?.includes("Files") && !zone.contains(event.target)) event.preventDefault();
    });
  }
  document.addEventListener("paste", event => {
    if (!document.getElementById("panel-drawing").classList.contains("active")) return;
    const item = [...(event.clipboardData?.items || [])].find(entry => entry.kind === "file");
    const file = item?.getAsFile();
    if (!file) return;
    event.preventDefault();
    const extension = (file.type.split("/")[1] || "png").replace("jpeg", "jpg");
    readDrawing(file.name && file.name !== "image.png" ? file : new File([file], `pasted-drawing.${extension}`, {type: file.type}));
  });
  for (const id of ["drawing-l", "drawing-w", "drawing-h", "drawing-t"]) {
    document.getElementById(id).addEventListener("input", markDrawingCostStale);
  }
  document.getElementById("drawing-calc-btn").addEventListener("click", calculateFromDrawing);
  document.getElementById("drawing-open-breakdown").addEventListener("click", () => {
    document.querySelector('nav.tabs button[data-tab="calc"]').click();
    document.getElementById("price-heading").scrollIntoView({behavior: "smooth", block: "start"});
  });
  document.querySelector('nav.tabs button[data-tab="drawing"]').addEventListener("click", syncDrawingMirrors);
  setupDrawingMirrors();
}

function markStale(message = "Estimate out of date") {
  ReportUI.markStale();
  AdvancedUI.onStale(message);
  const badge = document.getElementById("estimate-state");
  badge.textContent = message;
  badge.dataset.stale = "true";
}
function invalidateEstimate() {
  ++inputRevision;
  activeCalculation?.abort();
  clearTimeout(calculationTimer);
  setLoading(false);
  if (hasCalculated) markStale();
}
function scheduleCalculation() {
  invalidateEstimate();
  if (!hasCalculated || countryLoading) return;
  setStatus("Inputs changed. Updating estimate shortly…");
  calculationTimer = setTimeout(calculateAndRender, 600);
}


document.addEventListener(
  "DOMContentLoaded",
  init,
);
