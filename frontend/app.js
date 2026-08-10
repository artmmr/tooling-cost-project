const API_BASE_URL =
  "https://tooling-cost-project.onrender.com";


let currentToolingDefaults = null;
let currentToolingMaterialFamily = null;
let currentCountryDefaults = null;


/* =========================================================
   Lists
   ========================================================= */

const LISTS = {
  cycles: [
    {
      value: "up_to_10000",
      label: "Up to 10,000 cycles",
    },
    {
      value: "10000_to_100000",
      label: "10,000 to 100,000 cycles",
    },
    {
      value: "100000_to_250000",
      label: "100,000 to 250,000 cycles",
    },
  ],

  processes: [
    {
      value: "plastic_molding",
      label: "Plastic Molding",
    },
    {
      value: "plastic_injection",
      label: "Plastic Injection",
    },
    {
      value: "foaming",
      label: "Foaming",
    },
    {
      value: "thermoforming",
      label: "Thermoforming",
    },
    {
      value: "metal_molding",
      label: "Metal Molding",
    },
    {
      value: "stamping",
      label: "Stamping",
    },
    {
      value: "forming",
      label: "Forming",
    },
    {
      value: "deep_drawing",
      label: "Deep Drawing",
    },
  ],

  partsPerMold: Array.from(
    { length: 30 },
    (_, i) => i + 1,
  ),

  cooling: [
    {
      value: "false",
      label: "No",
    },
    {
      value: "true",
      label: "Yes",
    },
  ],
};


const PLASTIC_PROCESSES = new Set([
  "plastic_molding",
  "plastic_injection",
  "foaming",
  "thermoforming",
]);


const METAL_PROCESSES = new Set([
  "metal_molding",
  "stamping",
  "forming",
  "deep_drawing",
]);


const PLASTIC_MATERIALS = [
  {
    value: "standard_thermoplastic",
    label: "Standard thermoplastic",
  },
  {
    value: "glass_filled_thermoplastic",
    label: "Glass-filled thermoplastic",
  },
  {
    value: "mineral_filled_thermoplastic",
    label: "Mineral-filled thermoplastic",
  },
  {
    value: "corrosive_polymer",
    label: "Corrosive / aggressive polymer",
  },
  {
    value: "thermoset",
    label: "Thermoset",
  },
  {
    value: "elastomer",
    label: "Elastomer",
  },
  {
    value: "other",
    label: "Other",
  },
];


const METAL_MATERIALS = [
  {
    value: "mild_steel",
    label: "Mild steel",
  },
  {
    value: "high_strength_steel",
    label: "High-strength steel",
  },
  {
    value: "advanced_high_strength_steel",
    label: "Advanced high-strength steel (AHSS)",
  },
  {
    value: "stainless_steel",
    label: "Stainless steel",
  },
  {
    value: "aluminum_sheet",
    label: "Aluminum",
  },
  {
    value: "copper_brass",
    label: "Copper / brass",
  },
  {
    value: "other",
    label: "Other",
  },
];


const CYCLE_DEFAULTS = {
  up_to_10000: 5000,
  "10000_to_100000": 50000,
  "100000_to_250000": 150000,
};


/* =========================================================
   Formatting
   ========================================================= */

function fmt(number, decimals = 2) {
  if (
    typeof number !== "number" ||
    Number.isNaN(number)
  ) {
    return "—";
  }

  return number.toLocaleString(
    undefined,
    {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    },
  );
}


/* =========================================================
   Generic select helper
   ========================================================= */

function fillSelect(id, options) {
  const element =
    document.getElementById(id);

  element.innerHTML = options
    .map((option) => {
      if (typeof option === "object") {
        return `
          <option value="${option.value}">
            ${option.label}
          </option>
        `;
      }

      return `
        <option value="${option}">
          ${option}
        </option>
      `;
    })
    .join("");
}


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


async function loadCountryDefaults(
  countryCode,
) {
  setStatus(
    "Loading country benchmark assumptions...",
  );

  const response = await fetch(
    `${API_BASE_URL}/api/countries/${countryCode}`,
  );

  if (!response.ok) {
    throw new Error(
      "Could not load country benchmark assumptions.",
    );
  }

  const profile =
    await response.json();

  currentCountryDefaults =
    profile;

  applyCountryDefaults(
    profile,
  );

  setStatus(
    `${profile.name} benchmark assumptions loaded.`,
  );
}


function applyCountryDefaults(
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

async function loadToolingMaterialDefaults(
  materialCode,
) {
  const response = await fetch(
    `${API_BASE_URL}/api/tooling-materials/${materialCode}`,
  );

  if (!response.ok) {
    throw new Error(
      "Could not load tooling material defaults.",
    );
  }

  const profile =
    await response.json();

  currentToolingDefaults =
    profile;

  currentToolingMaterialFamily =
    materialCode;

  applyToolingMaterialDefaults(
    profile,
  );
}


function applyToolingMaterialDefaults(
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

function syncExpectedCycles() {
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

function readState() {
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
      Number.parseInt(
        document.getElementById(
          "inp-expected-cycles",
        ).value,
        10,
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

    sea_distance_km:
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
    !Number.isFinite(
      state.expected_cycles,
    ) ||
    state.expected_cycles <= 0
  ) {
    throw new Error(
      "Expected cycles must be greater than zero.",
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
      state.sea_distance_km,
    ) ||
    state.sea_distance_km < 0
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
      "Parts per mold must be between 1 and 30.",
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
      "EDM rate",
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
        "EDM share",
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
  state,
) {
  const response = await fetch(
    `${API_BASE_URL}/api/calculate`,
    {
      method: "POST",

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
    [
      "Tooling weight [kg]",
      result.tooling_weight_kg,
    ],

    [
      "Outside machining volume [m³]",
      result.outside_machining_volume_m3,
    ],

    [
      "Inside machining volume [m³]",
      result.inside_machining_volume_m3,
    ],

    [
      "Milling time index",
      result.milling_time_index,
    ],

    [
      "Volume removed / tool lifetime [min]",
      result.removed_volume_time_min,
    ],

    [
      "Tooling material cost",
      result.material_cost,
    ],

    [
      "Raw material transformation cost",
      result.transformation_cost,
    ],

    [
      "Outside machining cost",
      result.outside_machining_cost,
    ],

    [
      "Inside machining cost",
      result.inside_machining_cost,
    ],

    [
      "Milling tool cost",
      result.milling_tool_cost,
    ],

    [
      "Heat treatment cost",
      result.heat_treatment_cost,
    ],

    [
      "Cooling system cost",
      result.cooling_cost,
    ],

    [
      "Margin",
      result.margin,
    ],

    [
      "Handling cost",
      result.handling_cost,
    ],

    [
      "Transport & packaging",
      result.transport_cost,
    ],
  ];

  const tbody =
    document.querySelector(
      "#out-main tbody",
    );

  tbody.innerHTML = rows
    .map(
      ([label, value]) => `
        <tr>
          <th>${label}</th>

          <td class="num">
            ${fmt(value)}
          </td>
        </tr>
      `,
    )
    .join("");

  document.getElementById(
    "out-total",
  ).textContent =
    fmt(result.total_price);

  await renderRecommendation(
    result,
  );
}


/* =========================================================
   Recommendation rendering
   ========================================================= */

async function renderRecommendation(
  result,
) {
  document.getElementById(
    "rec-material",
  ).textContent =
    result.recommended_material ||
    "—";

  if (
    result.recommended_material_family
  ) {
    await loadToolingMaterialDefaults(
      result.recommended_material_family,
    );
  }

  const confidence =
    result.recommendation_confidence ||
    "—";

  const confidenceElement =
    document.getElementById(
      "rec-confidence",
    );

  confidenceElement.textContent =
    confidence === "—"
      ? confidence
      : confidence
          .charAt(0)
          .toUpperCase() +
        confidence.slice(1);

  confidenceElement.dataset.level =
    confidence.toLowerCase();

  renderList(
    "rec-failure-modes",
    result.failure_modes,
    "No major failure mode identified.",
  );

  renderList(
    "rec-reasons",
    result.recommendation_reasons,
    "No recommendation reasons available.",
  );

  renderList(
    "rec-operations",
    result.recommended_operations,
    "No manufacturing route available.",
  );
}


function renderList(
  id,
  items,
  emptyMessage,
) {
  const element =
    document.getElementById(id);

  if (
    !Array.isArray(items) ||
    items.length === 0
  ) {
    element.innerHTML =
      `<li>${emptyMessage}</li>`;

    return;
  }

  element.innerHTML = items
    .map(
      (item) =>
        `<li>${item}</li>`,
    )
    .join("");
}


/* =========================================================
   Status
   ========================================================= */

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

  status.classList.toggle(
    "err",
    isError,
  );
}


/* =========================================================
   Calculate
   ========================================================= */

async function calculateAndRender() {
  try {
    setLoading(true);

    setStatus(
      "Sending calculation to server...",
    );

    const state =
      readState();

    validateState(
      state,
    );

    const result =
      await requestCalculation(
        state,
      );

    await renderResult(
      result,
    );

    setStatus(
      "Calculation and tooling recommendation complete.",
    );
  } catch (error) {
    console.error(error);

    setStatus(
      error.message ||
        "Unable to calculate tooling cost.",
      true,
    );
  } finally {
    setLoading(false);
  }
}


/* =========================================================
   Tabs
   ========================================================= */

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
  document
    .getElementById(
      "calculate-btn",
    )
    .addEventListener(
      "click",
      calculateAndRender,
    );

  document
    .getElementById(
      "inp-process",
    )
    .addEventListener(
      "change",
      updateWorkpieceMaterials,
    );

  document
    .getElementById(
      "inp-cycles",
    )
    .addEventListener(
      "change",
      syncExpectedCycles,
    );

  document
    .getElementById(
      "inp-country",
    )
    .addEventListener(
      "change",
      async (event) => {
        try {
          await loadCountryDefaults(
            event.target.value,
          );
        } catch (error) {
          console.error(
            error,
          );

          setStatus(
            error.message,
            true,
          );
        }
      },
    );

  document
    .getElementById(
      "reset-country-defaults",
    )
    .addEventListener(
      "click",
      () => {
        if (
          currentCountryDefaults
        ) {
          applyCountryDefaults(
            currentCountryDefaults,
          );

          setStatus(
            `${currentCountryDefaults.name} benchmark assumptions restored.`,
          );
        }
      },
    );


  /* Manufacturing route live total */

  [
    "inp-route-cnc3",
    "inp-route-cnc5",
    "inp-route-edm",
    "inp-route-grinding",
  ].forEach(
    (id) => {
      document
        .getElementById(id)
        .addEventListener(
          "input",
          updateRouteTotal,
        );
    },
  );


  /* Reset tooling defaults */

  document
    .getElementById(
      "reset-tooling-defaults",
    )
    .addEventListener(
      "click",
      () => {
        if (
          currentToolingDefaults
        ) {
          applyToolingMaterialDefaults(
            currentToolingDefaults,
          );

          setStatus(
            `${currentToolingDefaults.name} tooling assumptions restored.`,
          );
        }
      },
    );
}


/* =========================================================
   Initialization
   ========================================================= */

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
      "19800";

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


    /* Events */

    setupEvents();

    setupTabs();


    setStatus(
      "Ready to calculate.",
    );
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

document.addEventListener(
  "DOMContentLoaded",
  init,
);