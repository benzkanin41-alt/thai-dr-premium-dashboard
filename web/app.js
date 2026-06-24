let dashboard = null;
let visibleRows = [];
let isLoading = false;

const rowsEl = document.getElementById("rows");
const noticeEl = document.getElementById("notice");
const priceBtn = document.getElementById("priceBtn");
const dashboardTab = document.getElementById("dashboardTab");
const converterTab = document.getElementById("converterTab");
const dashboardView = document.getElementById("dashboardView");
const converterView = document.getElementById("converterView");
const searchInput = document.getElementById("searchInput");
const statusFilter = document.getElementById("statusFilter");
const sortSelect = document.getElementById("sortSelect");
const converterSearch = document.getElementById("converterSearch");
const converterSelect = document.getElementById("converterSelect");
const converterSummary = document.getElementById("converterSummary");
const underlyingPriceInput = document.getElementById("underlyingPriceInput");
const drPriceInput = document.getElementById("drPriceInput");
const underlyingCurrencyLabel = document.getElementById("underlyingCurrencyLabel");
const fairDrOutput = document.getElementById("fairDrOutput");
const impliedUnderlyingOutput = document.getElementById("impliedUnderlyingOutput");
const impliedCurrencyLabel = document.getElementById("impliedCurrencyLabel");
const supportsServerApi = ["127.0.0.1", "localhost"].includes(window.location.hostname);
const githubWorkflowUrl = "https://github.com/benzkanin41-alt/thai-dr-premium-dashboard/actions/workflows/update-dashboard.yml";
const autoRefreshMs = 5 * 60 * 1000;

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

function fmtFx(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const digits = Math.abs(Number(value)) < 0.01 ? 6 : 4;
  return fmt(value, digits);
}

function extendedLabel(row) {
  if (!row.underlying_ext_price) return "ไม่มีราคา Pre/Post";
  return row.underlying_ext_session || "Extended hours";
}

function statusLabel(status) {
  if (status === "premium") return "Premium";
  if (status === "discount") return "Discount";
  if (status === "ok") return "Near fair";
  return "Needs mapping";
}

function numeric(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function setActiveView(view) {
  const showConverter = view === "converter";
  dashboardView.hidden = showConverter;
  converterView.hidden = !showConverter;
  dashboardTab.classList.toggle("active", !showConverter);
  dashboardTab.classList.toggle("ghost", showConverter);
  converterTab.classList.toggle("active", showConverter);
  converterTab.classList.toggle("ghost", !showConverter);
}

function converterEligibleRows() {
  return (dashboard?.rows || []).filter((row) => row.symbol && row.dr_per_underlying && row.fx_to_thb);
}

function converterHaystack(row) {
  return [
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
}

function renderConverterOptions() {
  if (!converterSelect) return;
  const query = converterSearch.value.trim().toLowerCase();
  const current = converterSelect.value;
  const rows = converterEligibleRows().filter((row) => !query || converterHaystack(row).includes(query));
  converterSelect.innerHTML = "";
  for (const row of rows) {
    const option = document.createElement("option");
    option.value = row.symbol;
    option.textContent = `${row.symbol} · ${row.underlying || "-"} · ${row.issuer || "-"}`;
    converterSelect.appendChild(option);
  }
  if (rows.some((row) => row.symbol === current)) {
    converterSelect.value = current;
  } else if (rows[0]) {
    converterSelect.value = rows[0].symbol;
    fillConverterInputs(rows[0]);
  }
  updateConverter();
}

function selectedConverterRow() {
  const symbol = converterSelect?.value;
  return converterEligibleRows().find((row) => row.symbol === symbol) || null;
}

function fillConverterInputs(row) {
  if (!row) return;
  underlyingPriceInput.value = row.underlying_price ? Number(row.underlying_price).toFixed(4).replace(/\.?0+$/, "") : "";
  drPriceInput.value = row.dr_last ? Number(row.dr_last).toFixed(4).replace(/\.?0+$/, "") : "";
}

function selectConverterRow(symbol, focusMode = null) {
  if (!symbol || !converterSelect) return;
  const row = converterEligibleRows().find((item) => item.symbol === symbol);
  if (!row) return;
  converterSearch.value = "";
  renderConverterOptions();
  converterSelect.value = symbol;
  fillConverterInputs(row);
  updateConverter();
  setActiveView("converter");
  if (focusMode === "underlying") underlyingPriceInput.focus();
  if (focusMode === "dr") drPriceInput.focus();
}

function updateConverter() {
  const row = selectedConverterRow();
  if (!row) {
    converterSummary.textContent = "No DR selected";
    underlyingCurrencyLabel.textContent = "-";
    impliedCurrencyLabel.textContent = "- ต่อหุ้นแม่";
    fairDrOutput.textContent = "-";
    impliedUnderlyingOutput.textContent = "-";
    return;
  }

  const ratio = numeric(row.dr_per_underlying);
  const fx = numeric(row.fx_to_thb);
  const currency = row.underlying_currency || "-";
  underlyingCurrencyLabel.textContent = currency;
  impliedCurrencyLabel.textContent = `${currency} ต่อหุ้นแม่`;
  converterSummary.textContent = `${row.symbol} · ${row.underlying || "-"} · FX ${fmtFx(fx)} · Ratio ${row.conversion_ratio || `${fmt(ratio, 0)} : 1`}`;

  const underlyingPrice = numeric(underlyingPriceInput.value);
  const drPrice = numeric(drPriceInput.value);
  const fairDr = underlyingPrice && fx && ratio ? (underlyingPrice * fx) / ratio : null;
  const impliedUnderlying = drPrice && fx && ratio ? (drPrice * ratio) / fx : null;
  fairDrOutput.textContent = fairDr ? fmt(fairDr, 4) : "-";
  impliedUnderlyingOutput.textContent = impliedUnderlying ? fmt(impliedUnderlying, 4) : "-";
}

function populateConverter() {
  if (!converterSelect) return;
  const current = converterSelect.value;
  renderConverterOptions();
  if (current) converterSelect.value = current;
  if (!converterSelect.value && converterEligibleRows()[0]) {
    converterSelect.value = converterEligibleRows()[0].symbol;
    fillConverterInputs(converterEligibleRows()[0]);
  }
  updateConverter();
}

function setLoading(isLoading, message = "") {
  if (priceBtn) priceBtn.disabled = isLoading;
  if (message) noticeEl.textContent = message;
}

async function loadDashboard({ updatePrices = false } = {}) {
  if (isLoading) return;
  isLoading = true;
  const message = updatePrices
    ? "Updating DR prices from SET official data, refreshing underlying prices and FX, then recalculating..."
    : "Loading dashboard...";
  setLoading(true, message);
  noticeEl.classList.remove("error");
  try {
    if (updatePrices && !supportsServerApi) {
      const opened = window.open(githubWorkflowUrl, "_blank", "noopener,noreferrer");
      if (!opened) window.location.href = githubWorkflowUrl;
      noticeEl.textContent = "Opened GitHub Actions manual update. After the workflow deploys, reload this page for the newest SET DR prices, underlying quotes, FX, and recalculated formulas.";
      return;
    }
    const params = new URLSearchParams();
    let url = "data/dashboard.json";
    if (supportsServerApi) {
      if (updatePrices) {
        params.set("refresh", "1");
        params.set("update_prices", "1");
      }
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
    populateConverter();
    const mode = supportsServerApi ? "Local server" : "GitHub Pages static data";
    const updateLabel = dashboard.manual_price_update
      ? " Manual price update complete: SET DR prices, underlying quotes, FX, and formulas recalculated."
      : "";
    noticeEl.textContent = `${mode}. Generated ${dashboard.generated_at}. Confirmed ${dashboard.counts.confirmed_dr} DR. ${dashboard.counts.needs_mapping} rows still need mapping or live quote.${updateLabel}`;
  } catch (error) {
    noticeEl.textContent = error.message;
    noticeEl.classList.add("error");
  } finally {
    isLoading = false;
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
    tr.dataset.symbol = row.symbol;
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
      <td class="price-cell convert-link" data-convert="dr" title="Convert this DR price to underlying price">
        <div class="price-main">${fmt(row.dr_last, 3)}</div>
        <div class="muted">บาทต่อ 1 DR</div>
      </td>
      <td class="price-cell fair-price">
        <div class="price-main">${fmt(row.fair_dr, 3)}</div>
        <div class="muted">บาทต่อ 1 DR</div>
      </td>
      <td class="price-cell convert-link" data-convert="underlying" title="Convert this underlying price to DR price">
        <div class="price-main">${fmt(row.underlying_price, 3)} ${row.underlying_currency || ""}</div>
        <div class="muted">${row.yahoo_symbol || "-"}</div>
      </td>
      <td class="price-cell extended-price">
        <div class="price-main">${fmt(row.underlying_ext_price, 3)} ${row.underlying_currency || ""}</div>
        <div class="muted">${extendedLabel(row)}</div>
      </td>
      <td class="${row.diff_pct > 0 ? "premium" : row.diff_pct < 0 ? "discount" : ""}">
        <div class="price-main">${fmtPct(row.diff_pct)}</div>
        <div class="muted">${row.diff_pct > 0 ? "DR แพงกว่า" : row.diff_pct < 0 ? "DR ถูกกว่า" : "ใกล้เคียง"}</div>
      </td>
      <td class="price-cell">
        <div class="price-main">${fmt(row.implied_underlying, 3)}</div>
        <div class="muted">${row.underlying_currency || ""} ต่อหุ้นแม่</div>
      </td>
      <td>
        <div>${fmtFx(row.fx_to_thb)}</div>
        <div class="muted">${row.fx_source_symbol || ""}</div>
      </td>
      <td>${ratio}</td>
      <td class="status"><span class="pill ${row.status}">${statusLabel(row.status)}</span></td>
    `;
    fragment.appendChild(tr);
  }
  rowsEl.appendChild(fragment);
}

if (priceBtn) {
  priceBtn.addEventListener("click", () => loadDashboard({ updatePrices: true }));
}
dashboardTab.addEventListener("click", () => setActiveView("dashboard"));
converterTab.addEventListener("click", () => setActiveView("converter"));
searchInput.addEventListener("input", applyFilters);
statusFilter.addEventListener("change", applyFilters);
sortSelect.addEventListener("change", applyFilters);
converterSearch.addEventListener("input", renderConverterOptions);
converterSelect.addEventListener("change", () => {
  fillConverterInputs(selectedConverterRow());
  updateConverter();
});
underlyingPriceInput.addEventListener("input", updateConverter);
drPriceInput.addEventListener("input", updateConverter);
rowsEl.addEventListener("click", (event) => {
  const target = event.target.closest("[data-convert]");
  if (!target) return;
  const symbol = target.closest("tr")?.dataset?.symbol;
  selectConverterRow(symbol, target.dataset.convert);
});

loadDashboard();

window.setInterval(() => {
  if (!document.hidden) loadDashboard();
}, autoRefreshMs);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) loadDashboard();
});

if (!supportsServerApi) {
  if (priceBtn) {
    priceBtn.title = "Open the GitHub Actions workflow to run the same SET DR, underlying, and FX update online";
  }
}
