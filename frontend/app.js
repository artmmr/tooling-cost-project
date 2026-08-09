const API_BASE_URL =
  "https://tooling-cost-project.onrender.com";


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


let currentCountryDefaults = null;


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

  return number.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}


/* =========================================================
   Generic select helper
   ========================================================= */

function fillSelect(id, options) {
  const element = document.getElementById(id);

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

  const countries = await response.json();

  const select =
    document.getElementById("inp-country");

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

  const profile = await response.json();

  currentCountryDefaults = profile;

  applyCountryDefaults(profile);

  setStatus(
    `${profile.name} benchmark assumptions loaded.`,
  );
}


function applyCountryDefaults(profile) {
  document.getElementById(
    "inp-engineering-rate",
  ).value = profile.engineering_rate;

  document.getElementById(
    "inp-assembly-rate",
  ).value = profile.assembly_rate;

  document.getElementById(
    "inp-cnc3-rate",
  ).value = profile.cnc_3_axis_rate;

  document.getElementById(
    "inp-cnc5-rate",
  ).value = profile.cnc_5_axis_rate;

  document.getElementById(
    "inp-edm-rate",
  ).value = profile.edm_rate;

  document.getElementById(
    "inp-grinding-rate",
  ).value = profile.grinding_rate;

  document.getElementById(
    "inp-electricity",
  ).value = profile.electricity_eur_kwh;

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
   Read calculator state
   ========================================================= */

function readState() {
  return {
    cycle_band:
      document.getElementById(
        "inp-cycles",
      ).value,

    process:
      document.getElementById(
        "inp-process",
      ).value,

    parts_per_mold: Number.parseInt(
      document.getElementById(
        "inp-pqty",
      ).value,
      10,
    ),

    manufacturing_country:
      document.getElementById(
        "inp-country",
      ).value,

    truck_distance_km: Number.parseFloat(
      document.getElementById(
        "inp-truck",
      ).value,
    ),

    sea_distance_km: Number.parseFloat(
      document.getElementById(
        "inp-sea",
      ).value,
    ),

    includes_cooling:
      document.getElementById(
        "inp-cooling",
      ).value === "true",

    part: {
      length_mm: Number.parseFloat(
        document.getElementById(
          "inp-l",
        ).value,
      ),

      width_mm: Number.parseFloat(
        document.getElementById(
          "inp-w",
        ).value,
      ),

      height_mm: Number.parseFloat(
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
  };
}


/* =========================================================
   Validation
   ========================================================= */

function validateState(state) {
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


  const assumptions = state.assumptions;


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
}


/* =========================================================
   API calculation request
   ========================================================= */

async function requestCalculation(state) {
  const response = await fetch(
    `${API_BASE_URL}/api/calculate`,
    {
      method: "POST",

      headers: {
        "Content-Type":
          "application/json",
      },

      body: JSON.stringify(state),
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
      // Keep the default error message.
    }


    throw new Error(
      errorMessage,
    );
  }


  return response.json();
}


/* =========================================================
   Render result
   ========================================================= */

function renderResult(result) {
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
          <th>
            ${label}
          </th>

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
}


/* =========================================================
   Loading / status
   ========================================================= */

function setLoading(isLoading) {
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


    renderResult(
      result,
    );


    setStatus(
      "Calculation complete.",
    );
  } catch (error) {
    console.error(
      error,
    );


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
    .forEach((button) => {
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
    });
}


/* =========================================================
   Setup event listeners
   ========================================================= */

function setupCountryEvents() {
  const countrySelect =
    document.getElementById(
      "inp-country",
    );


  countrySelect.addEventListener(
    "change",
    async (event) => {
      try {
        await loadCountryDefaults(
          event.target.value,
        );
      } catch (error) {
        console.error(error);

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
}


/* =========================================================
   Initialization
   ========================================================= */

async function init() {
  try {
    /* -------------------------
       Static dropdowns
       ------------------------- */

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


    /* -------------------------
       Default calculator inputs
       ------------------------- */

    document.getElementById(
      "inp-cycles",
    ).value =
      "10000_to_100000";


    document.getElementById(
      "inp-process",
    ).value =
      "stamping";


    document.getElementById(
      "inp-pqty",
    ).value =
      "2";


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


    /* -------------------------
       Load countries
       ------------------------- */

    setStatus(
      "Loading manufacturing benchmarks...",
    );


    await loadCountries();


    const countrySelect =
      document.getElementById(
        "inp-country",
      );


    countrySelect.value =
      "DE";


    await loadCountryDefaults(
      "DE",
    );


    /* -------------------------
       Events
       ------------------------- */

    setupCountryEvents();


    document
      .getElementById(
        "calculate-btn",
      )
      .addEventListener(
        "click",
        calculateAndRender,
      );


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