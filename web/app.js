let dashboard = null;
let visibleRows = [];

const rowsEl = document.getElementById("rows");
const noticeEl = document.getElementById("notice");
const refreshBtn = document.getElementById("refreshBtn");
const forceBtn = document.getElementById("forceBtn");
const exportLink = document.getElementById("exportLink");
const searchInput = document.getElementById("searchInput");
const statusFilter = document.getElementById("statusFilter");
const sortSelect = document.getElementById("sortSelect");
const supportsServerApi = ["127.0.0.1", "localhost"].includes(window.location.hostname);

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const sign = Number(value) > 0 ? "+" : "";
  return `${sign}${fmt(value, 2)}%`;
}

function statusLabel(status) {
  if (status === "premium") return "Premium";
  if (status === "discount") return "Discount";
  if (status === "ok") return "Near fair";
  return "Needs mapping";
}

function setLoading(isLoading, message = "") {
  refreshBtn.disabled = isLoading;
  forceBtn.disabled = isLoading;
  if (message) noticeEl.textContent = message;
}

async function loadDashboard({ refresh = false, forceProfiles = false } = {}) {
  setLoading(true, forceProfiles ? "Refreshing all SET profile factsheets. First run can take a few minutes..." : "Refreshing dashboard...");
  noticeEl.classList.remove("error");
  try {
    const params = new URLSearchParams();
    let url = "data/dashboard.json";
    if (supportsServerApi) {
      if (refresh) params.set("refresh", "1");
      if (forceProfiles) params.set("force_profiles", "1");
      url = `/api/dashboard?${params.toString()}`;
    } else {
      params.set("ts", Date.now().toString());
      url = `data/dashboard.json?${params.toString()}`;
    }
    const response = await fetch(url);
    dashboard = await response.json();
    if (!response.ok || dashboard.error) throw new Error(dashboard.error || "Failed to load dashboard");
    updateMetrics();
    applyFilters();
    const mode = supportsServerApi ? "Local server" : "GitHub Pages static data";
    noticeEl.textContent = `${mode}. Generated ${dashboard.generated_at}. Confirmed ${dashboard.counts.confirmed_dr} DR. ${dashboard.counts.needs_mapping} rows still need mapping or live quote.`;
  } catch (error) {
    noticeEl.textContent = error.message;
    noticeEl.classList.add("error");
  } finally {
    setLoading(false);
  }
}

function updateMetrics() {
  const rows = dashboard?.rows || [];
  document.getElementById("confirmedCount").textContent = dashboard?.counts?.confirmed_dr ?? "-";
  document.getElementById("withDiffCount").textContent = dashboard?.counts?.with_diff ?? "-";
  document.getElementById("premiumCount").textContent = rows.filter((row) => row.status === "premium").length;
  document.getElementById("discountCount").textContent = rows.filter((row) => row.status === "discount").length;
}

function applyFilters() {
  const query = searchInput.value.trim().toLowerCase();
  const status = statusFilter.value;
  visibleRows = (dashboard?.rows || []).filter((row) => {
    const haystack = [
      row.symbol,
      row.company_name,
      row.underlying,
      row.underlying_name,
      row.issuer,
      row.underlying_exchange,
      row.yahoo_symbol,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return (!query || haystack.includes(query)) && (status === "all" || row.status === status);
  });
  sortRows();
  renderRows();
}

function sortRows() {
  const sort = sortSelect.value;
  const val = (row) => (row.diff_pct === null || row.diff_pct === undefined ? null : Number(row.diff_pct));
  visibleRows.sort((a, b) => {
    if (sort === "symbol") return String(a.symbol).localeCompare(String(b.symbol));
    if (sort === "diffAsc") return (val(a) ?? Infinity) - (val(b) ?? Infinity);
    if (sort === "diffDesc") return (val(b) ?? -Infinity) - (val(a) ?? -Infinity);
    return Math.abs(val(b) ?? -1) - Math.abs(val(a) ?? -1);
  });
}

function renderRows() {
  rowsEl.innerHTML = "";
  const fragment = document.createDocumentFragment();
  for (const row of visibleRows) {
    const tr = document.createElement("tr");
    const ratio = row.conversion_ratio || (row.dr_per_underlying ? `${fmt(row.dr_per_underlying, 0)} : 1` : "-");
    tr.innerHTML = `
      <td>
        <div>${row.symbol}</div>
        <div class="muted">${row.issuer || ""}</div>
      </td>
      <td>
        <div>${row.underlying || "-"}</div>
        <div class="muted">${row.yahoo_symbol || "mapping required"} · ${row.underlying_exchange || ""}</div>
      </td>
      <td class="price-cell">
        <div class="price-main">${fmt(row.dr_last, 3)}</div>
        <div class="muted">บาทต่อ 1 DR</div>
      </td>
      <td class="price-cell fair-price">
        <div class="price-main">${fmt(row.fair_dr, 3)}</div>
        <div class="muted">บาทต่อ 1 DR</div>
      </td>
      <td class="price-cell">
        <div class="price-main">${fmt(row.underlying_price, 3)} ${row.underlying_currency || ""}</div>
        <div class="muted">${row.yahoo_symbol || "-"}</div>
      </td>
      <td class="${row.diff_pct > 0 ? "premium" : row.diff_pct < 0 ? "discount" : ""}">
        <div class="price-main">${fmtPct(row.diff_pct)}</div>
        <div class="muted">${row.diff_pct > 0 ? "DR แพงกว่า" : row.diff_pct < 0 ? "DR ถูกกว่า" : "ใกล้เคียง"}</div>
      </td>
      <td class="price-cell">
        <div class="price-main">${fmt(row.implied_underlying, 3)}</div>
        <div class="muted">${row.underlying_currency || ""} ต่อหุ้นแม่</div>
      </td>
      <td>${fmt(row.fx_to_thb, 4)}</td>
      <td>${ratio}</td>
      <td class="status"><span class="pill ${row.status}">${statusLabel(row.status)}</span></td>
    `;
    fragment.appendChild(tr);
  }
  rowsEl.appendChild(fragment);
}

refreshBtn.addEventListener("click", () => loadDashboard({ refresh: true }));
forceBtn.addEventListener("click", () => loadDashboard({ refresh: true, forceProfiles: true }));
searchInput.addEventListener("input", applyFilters);
statusFilter.addEventListener("change", applyFilters);
sortSelect.addEventListener("change", applyFilters);

loadDashboard();

if (!supportsServerApi) {
  forceBtn.disabled = true;
  forceBtn.title = "GitHub Pages updates by scheduled GitHub Actions every 15 minutes";
  exportLink.href = "data/dashboard.csv";
}
