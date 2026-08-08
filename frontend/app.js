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


function readState() {
  return {
    cycle_band:
      document.getElementById("inp-cycles").value,

    process:
      document.getElementById("inp-process").value,

    parts_per_mold: Number.parseInt(
      document.getElementById("inp-pqty").value,
      10,
    ),

    truck_distance_km: Number.parseFloat(
      document.getElementById("inp-truck").value,
    ),

    sea_distance_km: Number.parseFloat(
      document.getElementById("inp-sea").value,
    ),

    includes_cooling:
      document.getElementById("inp-cooling").value ===
      "true",

    part: {
      length_mm: Number.parseFloat(
        document.getElementById("inp-l").value,
      ),

      width_mm: Number.parseFloat(
        document.getElementById("inp-w").value,
      ),

      height_mm: Number.parseFloat(
        document.getElementById("inp-h").value,
      ),
    },
  };
}


function validateState(state) {
  if (
    !Number.isFinite(state.part.length_mm) ||
    state.part.length_mm <= 0
  ) {
    throw new Error(
      "Part length must be greater than zero.",
    );
  }

  if (
    !Number.isFinite(state.part.width_mm) ||
    state.part.width_mm <= 0
  ) {
    throw new Error(
      "Part width must be greater than zero.",
    );
  }

  if (
    !Number.isFinite(state.part.height_mm) ||
    state.part.height_mm <= 0
  ) {
    throw new Error(
      "Part height must be greater than zero.",
    );
  }

  if (
    !Number.isFinite(state.truck_distance_km) ||
    state.truck_distance_km < 0
  ) {
    throw new Error(
      "Truck distance cannot be negative.",
    );
  }

  if (
    !Number.isFinite(state.sea_distance_km) ||
    state.sea_distance_km < 0
  ) {
    throw new Error(
      "Sea distance cannot be negative.",
    );
  }
}


async function requestCalculation(state) {
  const response = await fetch(
    `${API_BASE_URL}/api/calculate`,
    {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify(state),
    },
  );

  if (!response.ok) {
    let errorMessage =
      `Calculation failed (${response.status}).`;

    try {
      const errorBody = await response.json();

      if (errorBody.detail) {
        errorMessage =
          typeof errorBody.detail === "string"
            ? errorBody.detail
            : JSON.stringify(errorBody.detail);
      }
    } catch {
      // Keep the default error message.
    }

    throw new Error(errorMessage);
  }

  return response.json();
}


function renderResult(result) {
  document.getElementById(
    "out-c12",
  ).textContent = result.tooling_material;

  document.getElementById(
    "out-c13",
  ).textContent =
    `${fmt(result.gross_length_mm, 0)} × ` +
    `${fmt(result.gross_width_mm, 0)} × ` +
    `${fmt(result.gross_height_mm, 0)} mm`;

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
    document.querySelector("#out-main tbody");

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
  ).textContent = fmt(result.total_price);
}


function setLoading(isLoading) {
  const button =
    document.getElementById("calculate-btn");

  button.disabled = isLoading;

  button.textContent = isLoading
    ? "Calculating..."
    : "Calculate tooling cost";
}


function setStatus(message, isError = false) {
  const status =
    document.getElementById("calc-status");

  status.textContent = message;

  status.classList.toggle(
    "err",
    isError,
  );
}


async function calculateAndRender() {
  try {
    setLoading(true);

    setStatus(
      "Sending calculation to server..."
    );

    const state = readState();

    validateState(state);

    const result =
      await requestCalculation(state);

    renderResult(result);

    setStatus("Calculation complete.");
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


function setupTabs() {
  document
    .querySelectorAll("nav.tabs button")
    .forEach((button) => {
      button.addEventListener("click", () => {
        const tab = button.dataset.tab;

        document
          .querySelectorAll("nav.tabs button")
          .forEach((item) => {
            item.setAttribute(
              "aria-selected",
              item.dataset.tab === tab,
            );
          });

        document
          .querySelectorAll(".panel")
          .forEach((panel) => {
            panel.classList.toggle(
              "active",
              panel.id === `panel-${tab}`,
            );
          });
      });
    });
}


function init() {
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


  // Default example values.
  document.getElementById(
    "inp-cycles",
  ).value = "10000_to_100000";

  document.getElementById(
    "inp-process",
  ).value = "stamping";

  document.getElementById(
    "inp-pqty",
  ).value = "2";

  document.getElementById(
    "inp-truck",
  ).value = "1700";

  document.getElementById(
    "inp-sea",
  ).value = "19800";

  document.getElementById(
    "inp-cooling",
  ).value = "false";

  document.getElementById(
    "inp-l",
  ).value = "300";

  document.getElementById(
    "inp-w",
  ).value = "300";

  document.getElementById(
    "inp-h",
  ).value = "40";


  document
    .getElementById("calculate-btn")
    .addEventListener(
      "click",
      calculateAndRender,
    );

  setupTabs();
}


document.addEventListener(
  "DOMContentLoaded",
  init,
);