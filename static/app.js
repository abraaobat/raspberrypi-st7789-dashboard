const state = {
  csrf: null,
  config: null,
  catalog: [],
  previewIndex: 0,
  dirty: false,
  authConfigured: false,
};

const $ = (selector) => document.querySelector(selector);
const app = $("#app");
const authScreen = $("#authScreen");

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
  state.config = config;
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
      <input class="page-check" type="checkbox" ${page.enabled ? "checked" : ""} aria-label="Ativar ${meta.title}">
      <div><strong>${meta.title}</strong><small>${meta.description}</small></div>
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

$("#saveButton").addEventListener("click", async () => {
  const button = $("#saveButton");
  button.disabled = true;
  try {
    state.config = await requestJSON("/api/config", {
      method: "PUT",
      body: JSON.stringify(state.config),
    });
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
