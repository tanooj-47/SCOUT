/**
 * frontend/app.js
 * Interactive client for SCOUT Geospatial Intelligence & Spatial Risk Engine.
 */

const API_BASE = "/api/v1/geospatial";

document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  setupEventListeners();
});

async function checkHealth() {
  const pill = document.getElementById("engine-status-pill");
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      if (data.status === "operational") {
        pill.textContent = `Operational (PostGIS: ${data.postgis_connected ? "Connected" : "Offline / Pure-Python"})`;
        pill.className = "status-pill status-ready";
      } else {
        pill.textContent = "Degraded (Limited Subsystems)";
        pill.className = "status-pill status-degraded";
      }
    } else {
      pill.textContent = "Service Offline";
      pill.className = "status-pill status-degraded";
    }
  } catch (err) {
    pill.textContent = "API Unreachable";
    pill.className = "status-pill status-degraded";
  }
}

function setupEventListeners() {
  const btnValidate = document.getElementById("btn-validate");
  const form = document.getElementById("geospatial-form");

  btnValidate.addEventListener("click", handleValidate);
  form.addEventListener("submit", handleAnalyze);
}

async function handleValidate() {
  const lat = parseFloat(document.getElementById("latitude").value);
  const lon = parseFloat(document.getElementById("longitude").value);
  const card = document.getElementById("validation-card");
  const badge = document.getElementById("val-badge");
  const sridEl = document.getElementById("val-srid");
  const utmEl = document.getElementById("val-utm");
  const errRow = document.getElementById("val-error-row");
  const errMsg = document.getElementById("val-error-msg");

  card.classList.remove("hidden");

  try {
    const res = await fetch(`${API_BASE}/validate-coordinate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ latitude: lat, longitude: lon }),
    });

    const data = await res.json();
    if (data.is_valid) {
      badge.textContent = "VALID";
      badge.style.backgroundColor = "var(--success)";
      sridEl.textContent = `EPSG:${data.srid}`;
      utmEl.textContent = data.utm_epsg ? `EPSG:${data.utm_epsg}` : "N/A";
      errRow.classList.add("hidden");
    } else {
      badge.textContent = "INVALID";
      badge.style.backgroundColor = "var(--danger)";
      sridEl.textContent = "N/A";
      utmEl.textContent = "N/A";
      errMsg.textContent = data.error_message || "Coordinate out of physical bounds";
      errRow.classList.remove("hidden");
    }
  } catch (err) {
    badge.textContent = "ERROR";
    badge.style.backgroundColor = "var(--danger)";
    errMsg.textContent = err.message;
    errRow.classList.remove("hidden");
  }
}

async function handleAnalyze(e) {
  e.preventDefault();
  const lat = parseFloat(document.getElementById("latitude").value);
  const lon = parseFloat(document.getElementById("longitude").value);
  const radius = parseFloat(document.getElementById("radius").value);
  const disasterType = document.getElementById("disaster-type").value;
  const btn = document.getElementById("btn-analyze");

  btn.disabled = true;
  btn.textContent = "Analyzing Spatial Exposure...";

  try {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latitude: lat,
        longitude: lon,
        search_radius_meters: radius,
        disaster_type: disasterType,
        include_geometry: false,
      }),
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error ? errData.error.message : "Analysis request failed.");
    }

    const data = await res.json();
    renderResults(data);
  } catch (err) {
    alert(`Geospatial Analysis Error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Spatial Exposure Analysis";
  }
}

function renderResults(data) {
  const section = document.getElementById("results-section");
  section.classList.remove("hidden");

  // Metrics
  document.getElementById("metric-total-features").textContent = data.exposure_summary.total_features_found;
  if (data.exposure_summary.closest_feature_distance_meters !== null) {
    document.getElementById("metric-closest-dist").textContent = `${data.exposure_summary.closest_feature_distance_meters.toFixed(0)}m`;
    document.getElementById("metric-closest-name").textContent = data.exposure_summary.closest_feature_name || "Feature";
  } else {
    document.getElementById("metric-closest-dist").textContent = "N/A";
    document.getElementById("metric-closest-name").textContent = "None within radius";
  }
  document.getElementById("metric-provider").textContent = data.data_provider;

  // Category breakdown
  const chipsContainer = document.getElementById("category-chips");
  chipsContainer.innerHTML = "";
  const counts = data.exposure_summary.category_counts;
  if (Object.keys(counts).length === 0) {
    chipsContainer.innerHTML = "<span class='hint'>No categorized features detected</span>";
  } else {
    for (const [cat, count] of Object.entries(counts)) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = `${cat}: ${count}`;
      chipsContainer.appendChild(chip);
    }
  }

  // Contributing Factors
  const factorsList = document.getElementById("contributing-factors-list");
  factorsList.innerHTML = "";
  data.contributing_factors.forEach(factor => {
    const li = document.createElement("li");
    li.textContent = factor;
    factorsList.appendChild(li);
  });

  // Features Table
  const tbody = document.getElementById("features-table-body");
  tbody.innerHTML = "";
  if (data.features.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--text-muted); padding: 1.5rem;">No features found in the current spatial catalog within ${data.incident_context.search_radius_meters}m.</td></tr>`;
  } else {
    data.features.forEach(feat => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${feat.name}</strong></td>
        <td><span class="chip">${feat.category}</span></td>
        <td>${feat.distance_meters.toFixed(0)} m</td>
        <td>${feat.relationship}</td>
        <td><small class="hint">${feat.source_dataset}</small></td>
      `;
      tbody.appendChild(tr);
    });
  }

  // Missing Layers
  const missingList = document.getElementById("missing-layers-list");
  missingList.innerHTML = "";
  if (data.missing_data_indicators.length === 0) {
    missingList.innerHTML = "<li>All queried domain layers registered</li>";
  } else {
    data.missing_data_indicators.forEach(layer => {
      const li = document.createElement("li");
      li.textContent = layer;
      missingList.appendChild(li);
    });
  }

  // Limitations
  const limitsList = document.getElementById("limitations-list");
  limitsList.innerHTML = "";
  data.assessment_limitations.forEach(limit => {
    const li = document.createElement("li");
    li.textContent = limit;
    limitsList.appendChild(li);
  });
}
