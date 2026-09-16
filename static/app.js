const state = {
  csrf: null,
  config: null,
  catalog: [],
  displays: [],
  previewIndex: 0,
  dirty: false,
  authConfigured: false,
  persistedCustomIds: new Set(),
};

const $ = (selector) => document.querySelector(selector);
const app = $("#app");
const authScreen = $("#authScreen");

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function requestJSON(url, options = {}) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (state.csrf && options.method && options.method !== "GET") {
    headers["X-CSRF-Token"] = state.csrf;
  }
  const response = await fetch(url, {...options, headers, cache: "no-store"});
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Erro ${response.status}`);
  return payload;
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast visible${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.className = "toast", 3200);
}

async function bootstrap() {
  try {
    const auth = await requestJSON("/api/auth/status");
    state.authConfigured = auth.configured;
    if (!auth.authenticated) return showAuth(auth.configured);
    state.csrf = auth.csrfToken;
    await loadApplication();
  } catch (error) {
    showAuth(true);
    $("#authError").textContent = error.message;
  }
}

function showAuth(configured) {
  app.hidden = true;
  authScreen.hidden = false;
  $("#authTitle").textContent = configured ? "Acessar painel" : "Proteja seu painel";
  $("#authDescription").textContent = configured
    ? "Digite o PIN local para configurar o display."
    : "Crie um PIN local. Ele será exigido para alterar o display.";
  $("#authButton").textContent = configured ? "Entrar" : "Criar PIN";
  $("#pinInput").autocomplete = configured ? "current-password" : "new-password";
  $("#pinInput").focus();
}

$("#authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#authError").textContent = "";
  const button = $("#authButton");
  button.disabled = true;
  try {
    const endpoint = state.authConfigured ? "/api/auth/login" : "/api/auth/setup";
    const payload = await requestJSON(endpoint, {
      method: "POST",
      body: JSON.stringify({pin: $("#pinInput").value}),
    });
    state.csrf = payload.csrfToken;
    $("#pinInput").value = "";
    await loadApplication();
  } catch (error) {
    $("#authError").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

async function loadApplication() {
  const [catalog, config] = await Promise.all([
    requestJSON("/api/catalog"),
    requestJSON("/api/config"),
  ]);
  state.catalog = catalog.pages;
  state.displays = catalog.displays || [];
  state.config = config;
  state.persistedCustomIds = new Set(config.customPages.map((item) => item.id));
  state.previewIndex = 0;
  state.dirty = false;
  authScreen.hidden = true;
  app.hidden = false;
  $("#connectionBadge").classList.add("online");
  $("#connectionBadge").innerHTML = "<span></span> Conectado";
  renderSettings();
  refreshPreview();
  refreshDisplayState();
}

function catalogEntry(id) {
  return state.catalog.find((item) => item.id === id) || {title: id, description: ""};
}

function enabledPages() {
  return state.config.pages.filter((page) => page.enabled);
}

function renderSettings() {
  const list = $("#pageList");
  list.textContent = "";
  state.config.pages.forEach((page, index) => {
    const meta = catalogEntry(page.id);
    const row = document.createElement("div");
    row.className = `page-row${page.enabled ? "" : " disabled"}`;
    row.innerHTML = `
      <input class="page-check" type="checkbox" ${page.enabled ? "checked" : ""} aria-label="Ativar ${escapeHTML(meta.title)}">
      <div><strong>${escapeHTML(meta.title)}</strong><small>${escapeHTML(meta.description)}</small></div>
      <div class="page-actions">
        <button type="button" data-direction="-1" aria-label="Subir" ${index === 0 ? "disabled" : ""}>↑</button>
        <button type="button" data-direction="1" aria-label="Descer" ${index === state.config.pages.length - 1 ? "disabled" : ""}>↓</button>
      </div>`;
    row.querySelector(".page-check").addEventListener("change", (event) => {
      const activeCount = enabledPages().length;
      if (!event.target.checked && activeCount === 1 && page.enabled) {
        event.target.checked = true;
        return toast("Ao menos uma página deve permanecer ativa.", true);
      }
      page.enabled = event.target.checked;
      markDirty();
      renderSettings();
      clampPreview();
      refreshPreview();
    });
    row.querySelectorAll("[data-direction]").forEach((button) => {
      button.addEventListener("click", () => movePage(index, Number(button.dataset.direction)));
    });
    list.appendChild(row);
  });

  $("#carouselEnabled").checked = state.config.carousel.enabled;
  $("#intervalSeconds").value = state.config.carousel.intervalSeconds;
  $("#resumeSeconds").value = state.config.carousel.resumeAfterSeconds;
  $("#intervalValue").textContent = `${state.config.carousel.intervalSeconds}s`;
  $("#resumeValue").textContent = `${state.config.carousel.resumeAfterSeconds}s`;
  $("#temperatureWarning").value = state.config.thresholds.temperatureWarning;
  $("#temperatureCritical").value = state.config.thresholds.temperatureCritical;
  $("#temperatureUnit").value = state.config.temperatureUnit;
  $("#weatherLocation").value = state.config.weather.locationName || "";
  $("#weatherLatitude").value = state.config.weather.latitude ?? "";
  $("#weatherLongitude").value = state.config.weather.longitude ?? "";
  $("#weatherRefresh").value = String(state.config.weather.refreshMinutes);
  $("#sysopsServices").value = state.config.sysops.services.join(", ");
  renderDisplayProfiles();
  renderCustomPages();
}

function renderDisplayProfiles() {
  const select = $("#displayProfile");
  select.textContent = "";
  state.displays.forEach((display) => {
    const option = document.createElement("option");
    option.value = display.id;
    option.textContent = display.label;
    option.disabled = !display.available;
    option.selected = display.id === state.config.displayProfile;
    select.appendChild(option);
  });
}

function customCatalogEntry(definition) {
  return {
    id: definition.id,
    title: definition.title,
    description: definition.description || "Fonte HTTP/JSON personalizada.",
    kind: "custom",
    removable: true,
  };
}

function syncCustomCatalog() {
  state.catalog = state.catalog
    .filter((item) => item.kind !== "custom")
    .concat(state.config.customPages.map(customCatalogEntry));
}

function renderCustomPages() {
  const list = $("#customPageList");
  list.textContent = "";
  $("#customEmpty").hidden = state.config.customPages.length > 0;
  const accentVariables = {
    blue: "var(--blue)", cyan: "var(--cyan)", green: "var(--green)",
    orange: "var(--orange)", purple: "#af78ff", red: "var(--danger)",
  };
  state.config.customPages.forEach((definition) => {
    const row = document.createElement("div");
    row.className = "custom-source-row";
    row.innerHTML = `
      <span class="accent-dot" style="background:${accentVariables[definition.accent] || "var(--cyan)"}"></span>
      <div class="source-copy"><strong>${escapeHTML(definition.title)}</strong><small>${escapeHTML(definition.source.url)} · ${escapeHTML(definition.source.valuePath)}</small></div>
      <div class="row-buttons">
        <button class="edit-source" type="button">Editar</button>
        <button class="remove-source" type="button">Remover</button>
      </div>`;
    row.querySelector(".edit-source").addEventListener("click", () => openCustomDialog(definition));
    row.querySelector(".remove-source").addEventListener("click", () => removeCustomPage(definition.id));
    list.appendChild(row);
  });
}

function movePage(index, direction) {
  const target = index + direction;
  if (target < 0 || target >= state.config.pages.length) return;
  [state.config.pages[index], state.config.pages[target]] = [state.config.pages[target], state.config.pages[index]];
  markDirty();
  renderSettings();
  clampPreview();
  refreshPreview();
}

function clampPreview() {
  const pages = enabledPages();
  if (!pages.length) state.previewIndex = 0;
  else state.previewIndex = Math.min(state.previewIndex, pages.length - 1);
}

function markDirty() {
  state.dirty = true;
  $("#saveState").textContent = "Alterações não aplicadas";
}

function refreshPreview() {
  const pages = enabledPages();
  if (!pages.length) return;
  clampPreview();
  const page = pages[state.previewIndex];
  const meta = catalogEntry(page.id);
  $("#previewTitle").textContent = meta.title;
  $("#previewPosition").textContent = `${state.previewIndex + 1} de ${pages.length}`;
  const isUnsavedCustom = page.id.startsWith("custom:") && !state.persistedCustomIds.has(page.id);
  $("#previewPlaceholder").hidden = !isUnsavedCustom;
  $("#previewImage").hidden = isUnsavedCustom;
  if (isUnsavedCustom) return;
  $("#previewImage").src = `/api/preview?page=${encodeURIComponent(page.id)}&t=${Date.now()}`;
}

$("#previousPage").addEventListener("click", () => {
  const count = enabledPages().length;
  state.previewIndex = (state.previewIndex - 1 + count) % count;
  refreshPreview();
});

$("#nextPage").addEventListener("click", () => {
  const count = enabledPages().length;
  state.previewIndex = (state.previewIndex + 1) % count;
  refreshPreview();
});

$("#carouselEnabled").addEventListener("change", (event) => {
  state.config.carousel.enabled = event.target.checked;
  markDirty();
});

$("#intervalSeconds").addEventListener("input", (event) => {
  state.config.carousel.intervalSeconds = Number(event.target.value);
  $("#intervalValue").textContent = `${event.target.value}s`;
  markDirty();
});

$("#resumeSeconds").addEventListener("input", (event) => {
  state.config.carousel.resumeAfterSeconds = Number(event.target.value);
  $("#resumeValue").textContent = `${event.target.value}s`;
  markDirty();
});

$("#temperatureWarning").addEventListener("change", (event) => {
  state.config.thresholds.temperatureWarning = Number(event.target.value);
  markDirty();
  refreshPreview();
});

$("#temperatureCritical").addEventListener("change", (event) => {
  state.config.thresholds.temperatureCritical = Number(event.target.value);
  markDirty();
  refreshPreview();
});

$("#temperatureUnit").addEventListener("change", (event) => {
  state.config.temperatureUnit = event.target.value;
  markDirty();
  refreshPreview();
});

function nullableNumber(value) {
  return value === "" ? null : Number(value);
}

$("#weatherLocation").addEventListener("change", (event) => {
  state.config.weather.locationName = event.target.value.trim();
  markDirty();
});

$("#weatherLatitude").addEventListener("change", (event) => {
  state.config.weather.latitude = nullableNumber(event.target.value);
  markDirty();
});

$("#weatherLongitude").addEventListener("change", (event) => {
  state.config.weather.longitude = nullableNumber(event.target.value);
  markDirty();
});

$("#weatherRefresh").addEventListener("change", (event) => {
  state.config.weather.refreshMinutes = Number(event.target.value);
  markDirty();
});

$("#sysopsServices").addEventListener("change", (event) => {
  state.config.sysops.services = event.target.value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  markDirty();
});

$("#displayProfile").addEventListener("change", (event) => {
  state.config.displayProfile = event.target.value;
  markDirty();
  refreshPreview();
});

function customFormValue() {
  const id = $("#customId").value || makeCustomId($("#customTitle").value);
  let hostname = "Fonte HTTP/JSON personalizada.";
  try { hostname = `Dados de ${new URL($("#customUrl").value).hostname}`; } catch (_) {}
  return {
    id,
    title: $("#customTitle").value.trim(),
    description: hostname,
    layout: $("#customLayout").value,
    valueLabel: $("#customValueLabel").value.trim(),
    unit: $("#customUnit").value.trim(),
    accent: $("#customAccent").value,
    source: {
      type: "http-json",
      url: $("#customUrl").value.trim(),
      valuePath: $("#customValuePath").value.trim(),
      secondaryPath: $("#customSecondaryPath").value.trim(),
    },
  };
}

function makeCustomId(title) {
  const base = title.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24) || "fonte";
  let candidate = `custom:${base}`;
  let number = 2;
  const used = new Set(state.config.customPages.map((item) => item.id));
  while (used.has(candidate)) candidate = `custom:${base.slice(0, 20)}-${number++}`;
  return candidate;
}

function openCustomDialog(definition = null) {
  $("#customForm").reset();
  $("#sourceTestResult").textContent = "";
  $("#sourceTestResult").className = "source-test-result";
  $("#customDialogTitle").textContent = definition ? "Editar fonte" : "Adicionar fonte";
  $("#customId").value = definition?.id || "";
  $("#customTitle").value = definition?.title || "";
  $("#customValueLabel").value = definition?.valueLabel || "";
  $("#customUrl").value = definition?.source.url || "";
  $("#customValuePath").value = definition?.source.valuePath || "";
  $("#customSecondaryPath").value = definition?.source.secondaryPath || "";
  $("#customUnit").value = definition?.unit || "";
  $("#customLayout").value = definition?.layout || "metric";
  $("#customAccent").value = definition?.accent || "cyan";
  $("#customDialog").showModal();
  $("#customTitle").focus();
}

function closeCustomDialog() {
  $("#customDialog").close();
}

function removeCustomPage(id) {
  state.config.customPages = state.config.customPages.filter((item) => item.id !== id);
  state.config.pages = state.config.pages.filter((item) => item.id !== id);
  syncCustomCatalog();
  markDirty();
  clampPreview();
  renderSettings();
  refreshPreview();
}

$("#addCustomPage").addEventListener("click", () => openCustomDialog());
$("#closeCustomDialog").addEventListener("click", closeCustomDialog);
$("#cancelCustomSource").addEventListener("click", closeCustomDialog);

$("#testCustomSource").addEventListener("click", async () => {
  const result = $("#sourceTestResult");
  result.className = "source-test-result";
  result.textContent = "Testando…";
  try {
    const payload = await requestJSON("/api/sources/test", {
      method: "POST",
      body: JSON.stringify(customFormValue()),
    });
    const detail = payload.secondary == null ? "" : ` · ${payload.secondary}`;
    result.textContent = `Conexão aprovada: ${payload.value}${detail}`;
  } catch (error) {
    result.className = "source-test-result error";
    result.textContent = error.message;
  }
});

$("#customForm").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!event.target.reportValidity()) return;
  const definition = customFormValue();
  const index = state.config.customPages.findIndex((item) => item.id === definition.id);
  if (index >= 0) state.config.customPages[index] = definition;
  else {
    if (state.config.customPages.length >= 8) return toast("Limite de oito fontes personalizadas.", true);
    state.config.customPages.push(definition);
    state.config.pages.push({id: definition.id, enabled: true, refreshSeconds: 60});
  }
  syncCustomCatalog();
  markDirty();
  closeCustomDialog();
  renderSettings();
  refreshPreview();
});

$("#saveButton").addEventListener("click", async () => {
  const button = $("#saveButton");
  button.disabled = true;
  try {
    state.config = await requestJSON("/api/config", {
      method: "PUT",
      body: JSON.stringify(state.config),
    });
    state.persistedCustomIds = new Set(state.config.customPages.map((item) => item.id));
    syncCustomCatalog();
    state.dirty = false;
    $("#saveState").textContent = "Configuração aplicada";
    renderSettings();
    refreshPreview();
    toast("Display atualizado com sucesso.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#showOnDisplay").addEventListener("click", async () => {
  const page = enabledPages()[state.previewIndex];
  if (!page) return;
  try {
    await requestJSON("/api/display/page", {
      method: "POST",
      body: JSON.stringify({pageId: page.id}),
    });
    toast(`${catalogEntry(page.id).title} selecionada no display.`);
    setTimeout(refreshDisplayState, 700);
  } catch (error) {
    toast(error.message, true);
  }
});

async function refreshDisplayState() {
  if (app.hidden) return;
  try {
    const display = await requestJSON("/api/display/state");
    const element = $("#displayState");
    if (display.error) {
      element.textContent = "Display com erro";
      return;
    }
    element.textContent = display.currentPage
      ? `Exibindo ${catalogEntry(display.currentPage).title}`
      : "Aguardando display";
  } catch (_) {
    $("#displayState").textContent = "Estado indisponível";
  }
}

$("#logoutButton").addEventListener("click", async () => {
  try {
    await requestJSON("/api/auth/logout", {method: "POST", body: "{}"});
  } finally {
    state.csrf = null;
    showAuth(true);
  }
});

setInterval(() => {
  if (!app.hidden) {
    refreshPreview();
    refreshDisplayState();
  }
}, 5000);

bootstrap();
