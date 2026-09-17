const state = {
  csrf: null,
  config: null,
  catalog: [],
  displays: [],
  sourceTemplates: [],
  sourceTestController: null,
  sourceGeneration: 0,
  previewIndex: 0,
  dirty: false,
  authConfigured: false,
  persistedCustomIds: new Set(),
  integrationsStatus: {},
  pomodoro: null,
  pomodoroBusy: false,
  pomodoroGeneration: 0,
  dockerGeneration: 0,
  mqttGeneration: 0,
  mqttCredential: {},
  activeDisplayProfile: "st7789-240x240",
  previewProfile: "",
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
  $("#mqttUsername").value = "";
  $("#mqttPassword").value = "";
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
  state.pomodoroGeneration++;
  state.dockerGeneration++;
  state.mqttGeneration++;
  $("#checkMqtt").disabled = false;
  $("#mqttStatus").textContent = "Não consultado. A consulta usa apenas os ajustes já aplicados.";
  $("#checkDocker").disabled = false;
  $("#dockerStatus").textContent = "Não consultado. Os filtros só entram em vigor após Aplicar alterações.";
  const [catalog, config, integrations, mqttCredential] = await Promise.all([
    requestJSON("/api/catalog"),
    requestJSON("/api/config"),
    requestJSON("/api/integrations/status"),
    requestJSON("/api/mqtt/credential/status").catch(error => ({error: error.message})),
  ]);
  state.catalog = catalog.pages;
  state.displays = catalog.displays || [];
  state.activeDisplayProfile = catalog.activeDisplayProfile;
  state.previewProfile = "";
  state.mqttCredential = mqttCredential;
  state.sourceTemplates = catalog.sourceTemplates || [];
  state.config = config;
  state.authConfigured = true;
  state.integrationsStatus = integrations;
  state.persistedCustomIds = new Set(config.customPages.map((item) => item.id));
  state.previewIndex = 0;
  state.dirty = false;
  $("#saveState").textContent = "Configuração aplicada";
  authScreen.hidden = true;
  app.hidden = false;
  $("#connectionBadge").classList.add("online");
  $("#connectionBadge").innerHTML = "<span></span> Conectado";
  renderSettings();
  renderSourceTemplates();
  refreshPreview();
  refreshDisplayState();
  refreshPomodoro();
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
  $("#dockerNames").value = state.config.docker.names.join(", ");
  const dockerPage = state.config.pages.find(page => page.id === "docker");
  const dockerRefresh = $("#dockerRefresh");
  dockerRefresh.querySelector('[data-existing-refresh]')?.remove();
  if (![15, 30, 60].includes(dockerPage.refreshSeconds)) {
    const option = document.createElement("option");
    option.value = dockerPage.refreshSeconds;
    option.textContent = `A cada ${dockerPage.refreshSeconds} segundos`;
    option.dataset.existingRefresh = "true";
    dockerRefresh.append(option);
  }
  dockerRefresh.value = dockerPage.refreshSeconds;
  renderMqttSettings();
  renderDisplayProfiles();
  renderCustomPages();
  renderIntegrations();
  $("#clockTimezone").value = state.config.clock.timezone;
  $("#clockShowSeconds").checked = state.config.clock.showSeconds;
  $("#clockHour24").checked = state.config.clock.hour24;
  $("#pomodoroMinutes").value = state.config.pomodoro.minutes;
}

$("#clockTimezone").addEventListener("change", event => {
  state.config.clock.timezone = event.target.value.trim();
  markDirty();
});
for (const [id, option] of [["clockShowSeconds", "showSeconds"], ["clockHour24", "hour24"]]) {
  $(`#${id}`).addEventListener("change", event => { state.config.clock[option] = event.target.checked; markDirty(); });
}
$("#pomodoroMinutes").addEventListener("change", event => {
  if (!event.target.reportValidity()) return;
  state.config.pomodoro.minutes = Number(event.target.value);
  markDirty();
});

const pomodoroLabels = {idle: "Pronto para focar", running: "Foco em andamento", paused: "Pausado",
  completed: "Ciclo concluído", interrupted: "Pi reiniciado · inicie outro ciclo"};

function renderPomodoro(snapshot) {
  state.pomodoro = snapshot;
  const seconds = snapshot.remainingSeconds;
  $("#pomodoroCountdown").textContent = seconds == null ? "--:--"
    : `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  const label = pomodoroLabels[snapshot.status] || "Estado indisponível";
  if ($("#pomodoroStatus").textContent !== label) $("#pomodoroStatus").textContent = label;
  $("#pomodoroProgress").value = snapshot.progress || 0;
  $("#pomodoroStart").disabled = state.pomodoroBusy || !["idle", "completed", "interrupted"].includes(snapshot.status);
  $("#pomodoroPause").disabled = state.pomodoroBusy || snapshot.status !== "running";
  $("#pomodoroResume").disabled = state.pomodoroBusy || snapshot.status !== "paused";
  $("#pomodoroReset").disabled = state.pomodoroBusy;
}

async function refreshPomodoro() {
  if (app.hidden || state.pomodoroBusy || refreshPomodoro.pending) return;
  const generation = state.pomodoroGeneration;
  refreshPomodoro.pending = true;
  try {
    const snapshot = await requestJSON("/api/pomodoro/state");
    if (generation === state.pomodoroGeneration && !state.pomodoroBusy && !app.hidden) renderPomodoro(snapshot);
  } catch (error) {
    if (generation !== state.pomodoroGeneration || state.pomodoroBusy || app.hidden) return;
    $("#pomodoroStatus").textContent = error.message;
    document.querySelectorAll("[data-pomodoro-action]").forEach(button => { button.disabled = true; });
  } finally { refreshPomodoro.pending = false; }
}

document.querySelectorAll("[data-pomodoro-action]").forEach(button => {
  button.addEventListener("click", async () => {
    const action = button.dataset.pomodoroAction;
    if (state.pomodoroBusy) return;
    if (action === "start" && state.dirty) return toast("Aplique ou descarte os ajustes antes de iniciar o próximo ciclo.", true);
    if (action === "reset" && state.pomodoro?.status !== "idle" && !confirm("Descartar o ciclo atual e voltar ao início?")) return;
    const generation = ++state.pomodoroGeneration;
    state.pomodoroBusy = true;
    if (state.pomodoro) renderPomodoro(state.pomodoro);
    try {
      const snapshot = await requestJSON("/api/pomodoro/command", {method: "POST", body: JSON.stringify({action})});
      if (generation === state.pomodoroGeneration && !app.hidden) {
        renderPomodoro(snapshot);
        refreshPreview();
      }
    } catch (error) { toast(error.message, true); }
    finally {
      state.pomodoroBusy = false;
      if (generation === state.pomodoroGeneration && state.pomodoro && !app.hidden) renderPomodoro(state.pomodoro);
      refreshPomodoro();
    }
  });
});

const integrationNames = {pihole: "Pi-hole", homeassistant: "Home Assistant"};

function renderIntegrations() {
  Object.keys(integrationNames).forEach((id) => {
    const settings = state.config.integrations[id];
    const metadata = state.integrationsStatus[id] || {};
    const matches = metadata.credentialConfigured && metadata.credentialBaseUrl === settings.baseUrl;
    $(`#${id}Status`).textContent = metadata.error || (!settings.baseUrl ? "Não configurado"
      : !matches ? "Credencial pendente para este endereço" : "Configurado · teste a conexão no assistente");
  });
}

function integrationFormValue() {
  const id = $("#integrationId").value;
  const url = new URL($("#integrationUrl").value.trim());
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("Use um endereço HTTP/HTTPS sem senha, parâmetros ou fragmentos.");
  }
  const settings = {baseUrl: url.href.replace(/\/+$/, ""), allowInsecureHttp: $("#integrationAllowHttp").checked};
  if (id === "homeassistant") {
    settings.entities = $("#integrationEntities").value.split(",").map((value) => value.trim()).filter(Boolean);
    if (settings.entities.length > 4 || new Set(settings.entities).size !== settings.entities.length
      || settings.entities.some((value) => value.length > 120 || !/^[a-z0-9_]+\.[a-z0-9_]+$/.test(value))) {
      throw new Error("Escolha até quatro entidades diferentes, no formato sensor.temperatura.");
    }
  }
  return {id, settings};
}

function updateCredentialStatus() {
  const id = $("#integrationId").value;
  const metadata = state.integrationsStatus[id] || {};
  $("#integrationCredentialStatus").textContent = metadata.error || (!metadata.credentialConfigured
    ? "Nenhuma credencial guardada."
    : `Credencial guardada para ${metadata.credentialBaseUrl}. Ela não será exibida novamente.`);
  $("#removeIntegrationCredential").disabled = !metadata.credentialConfigured;
}

function openIntegrationDialog(id) {
  const settings = state.config.integrations[id];
  $("#integrationForm").reset();
  $("#integrationId").value = id;
  $("#integrationDialogTitle").textContent = `Configurar ${integrationNames[id]}`;
  $("#integrationUrl").value = settings.baseUrl;
  $("#integrationEntitiesField").hidden = id !== "homeassistant";
  $("#integrationEntities").value = (settings.entities || []).join(", ");
  $("#integrationSecretLabel").textContent = id === "pihole" ? "Senha de aplicativo do Pi-hole 6" : "Token de acesso de longa duração";
  $("#integrationHelp").textContent = id === "pihole"
    ? "No Pi-hole 6, gere uma senha de aplicativo nas configurações de API. Informe a raiz do serviço, por exemplo http://pi.hole, sem /admin ou /api."
    : "No seu perfil do Home Assistant, crie um token de acesso de longa duração. Informe a raiz do serviço e os IDs das entidades, encontrados em Ferramentas do desenvolvedor → Estados.";
  $("#integrationAllowHttp").checked = settings.allowInsecureHttp;
  $("#integrationActivate").checked = state.config.pages.find((page) => page.id === id).enabled;
  $("#integrationTestResult").textContent = "";
  $("#integrationTestResult").className = "source-test-result";
  updateCredentialStatus();
  $("#integrationDialog").showModal();
  $("#integrationUrl").focus();
}

function closeIntegrationDialog() { $("#integrationDialog").close(); }
$("#integrationDialog").addEventListener("close", () => { $("#integrationSecret").value = ""; });
$("#closeIntegrationDialog").addEventListener("click", closeIntegrationDialog);
$("#cancelIntegrationDialog").addEventListener("click", closeIntegrationDialog);
document.querySelectorAll("[data-configure-integration]").forEach((button) => {
  button.addEventListener("click", () => openIntegrationDialog(button.dataset.configureIntegration));
});

function integrationFeedback(message, error = false) {
  $("#integrationTestResult").textContent = message;
  $("#integrationTestResult").className = `source-test-result${error ? " error" : ""}`;
}

async function storeIntegrationCredential() {
  const {id, settings} = integrationFormValue();
  if (!$("#integrationSecret").value) throw new Error("Digite uma nova credencial para guardá-la.");
  const receipt = await requestJSON(`/api/integrations/${id}/credential`, {
    method: "PUT", body: JSON.stringify({baseUrl: settings.baseUrl, secret: $("#integrationSecret").value}),
  });
  $("#integrationSecret").value = "";
  state.integrationsStatus[id] = receipt;
  $("#integrationUrl").value = receipt.credentialBaseUrl;
  updateCredentialStatus();
  renderIntegrations();
}

// Serialize modal actions: a late reply must never populate another connector's dialog.
async function integrationAction(action) {
  const buttons = $("#integrationForm").querySelectorAll("button");
  buttons.forEach((button) => { button.disabled = true; });
  try { await action(); } catch (error) { integrationFeedback(error.message, true); }
  finally { buttons.forEach((button) => { button.disabled = false; }); updateCredentialStatus(); }
}

$("#integrationDialog").addEventListener("cancel", (event) => {
  if ($("#testIntegration").disabled) event.preventDefault();
});
$("#storeIntegrationCredential").addEventListener("click", () => integrationAction(async () => {
  await storeIntegrationCredential();
  integrationFeedback("Credencial guardada localmente. Os ajustes ainda precisam ser aplicados.");
}));
$("#removeIntegrationCredential").addEventListener("click", () => integrationAction(async () => {
  if (!confirm("Remover somente a credencial local? O token no serviço de origem não será revogado.")) return;
  const id = $("#integrationId").value;
  await requestJSON(`/api/integrations/${id}/credential`, {method: "DELETE"});
  state.integrationsStatus[id] = {};
  $("#integrationSecret").value = "";
  renderIntegrations();
  integrationFeedback("Credencial local removida. Se necessário, revogue-a também no serviço de origem.");
}));
$("#testIntegration").addEventListener("click", () => integrationAction(async () => {
  if (!$("#integrationForm").reportValidity()) return;
  const {id, settings} = integrationFormValue();
  const payload = {settings};
  if ($("#integrationSecret").value) payload.secret = $("#integrationSecret").value;
  integrationFeedback("Testando conexão somente de leitura…");
  const response = await requestJSON(`/api/integrations/${id}/test`, {method: "POST", body: JSON.stringify(payload)});
  integrationFeedback(id === "pihole"
    ? `Conexão aprovada: ${response.result.blockedQueries} consultas bloqueadas (${response.result.blockedPercent.toFixed(1)}%).`
    : `Conexão concluída: ${response.result.entities.filter((entity) => entity.available).length} de ${response.result.entities.length} entidades com dados. Nenhum estado foi alterado.`);
}));
$("#integrationForm").addEventListener("submit", (event) => {
  event.preventDefault();
  integrationAction(async () => {
    if (!event.target.reportValidity()) return;
    if ($("#integrationSecret").value) await storeIntegrationCredential();
    const {id, settings} = integrationFormValue();
    if (id === "homeassistant" && $("#integrationActivate").checked && !settings.entities.length) {
      throw new Error("Selecione ao menos uma entidade para ativar a página Casa.");
    }
    const page = state.config.pages.find((entry) => entry.id === id);
    if (!$("#integrationActivate").checked && page.enabled && enabledPages().length === 1) {
      throw new Error("Ao menos uma página deve permanecer ativa.");
    }
    state.config.integrations[id] = settings;
    page.enabled = $("#integrationActivate").checked;
    markDirty();
    renderSettings();
    clampPreview();
    refreshPreview();
    closeIntegrationDialog();
    toast("Ajustes guardados no rascunho. Clique em Aplicar alterações.");
  });
});

$("#importConfigButton").addEventListener("click", () => $("#importConfigFile").click());
$("#importConfigFile").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  try {
    if (file.size > 64 * 1024) throw new Error("O backup deve ter no máximo 64 KB.");
    const config = JSON.parse(await file.text());
    if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("Backup inválido.");
    if (!confirm("Restaurar a configuração e substituir os ajustes atuais, inclusive o rascunho? PIN e credenciais locais serão preservados.")) return;
    await requestJSON("/api/config/import", {method: "POST", body: JSON.stringify(config)});
    await loadApplication();
    toast("Configuração restaurada. PIN e credenciais foram preservados.");
  } catch (error) { toast(error.message, true); }
});

function renderDisplayProfiles() {
  const select = $("#displayProfile");
  select.textContent = "";
  state.displays.forEach((display) => {
    const option = document.createElement("option");
    option.value = display.id;
    option.textContent = display.label;
    option.disabled = !display.available;
    option.selected = display.id === state.activeDisplayProfile;
    select.appendChild(option);
  });
  select.disabled = true;
  const preview = $("#previewProfile");
  preview.innerHTML = '<option value="">Display físico configurado</option>';
  state.displays.forEach(display => {
    const option = document.createElement("option");
    option.value = display.id;
    option.textContent = `Simular ${display.label}`;
    preview.appendChild(option);
  });
  preview.value = state.previewProfile;
}

function renderMqttSettings() {
  $("#mqttBroker").value = state.config.mqtt.brokerUrl;
  $("#mqttAllowPlain").checked = state.config.mqtt.allowInsecureMqtt;
  $("#mqttRefresh").value = state.config.pages.find(page => page.id === "mqtt").refreshSeconds;
  $("#mqttSensors").innerHTML = Array.from({length: 4}, (_, index) => {
    const sensor = state.config.mqtt.sensors[index] || {label: "", topic: "", format: "text", valuePath: "", unit: ""};
    return `<section class="integration-card mqtt-sensor" data-mqtt-sensor="${index}">
      <strong>Sensor ${index + 1}</strong>
      <label class="compact-field"><span>Nome</span><input class="text-input" data-mqtt-field="label" maxlength="18" value="${escapeHTML(sensor.label)}"></label>
      <label class="compact-field"><span>Tópico exato</span><input class="text-input" data-mqtt-field="topic" maxlength="200" value="${escapeHTML(sensor.topic)}" placeholder="casa/sala/temperatura"></label>
      <label class="select-field"><span>Formato</span><select data-mqtt-field="format"><option value="text" ${sensor.format === "text" ? "selected" : ""}>Texto simples</option><option value="json" ${sensor.format === "json" ? "selected" : ""}>JSON</option></select></label>
      <label class="compact-field"><span>Caminho JSON</span><input class="text-input" data-mqtt-field="valuePath" maxlength="120" value="${escapeHTML(sensor.valuePath)}" placeholder="sensor.value" ${sensor.format === "text" ? "disabled" : ""}></label>
      <label class="compact-field"><span>Unidade</span><input class="text-input" data-mqtt-field="unit" maxlength="10" value="${escapeHTML(sensor.unit)}" placeholder="°C"></label>
    </section>`;
  }).join("");
  renderMqttCredential();
}

function renderMqttCredential() {
  const metadata = state.mqttCredential;
  $("#mqttCredentialStatus").textContent = metadata.error || (metadata.credentialConfigured
    ? `Credencial guardada para ${metadata.credentialBaseUrl}. Não será exibida novamente; confira se corresponde ao broker escolhido.`
    : "Sem credencial guardada; acesso anônimo.");
  $("#removeMqttCredential").disabled = !metadata.credentialConfigured;
}

$("#mqttSensors").addEventListener("change", event => {
  const row = event.target.closest("[data-mqtt-sensor]");
  if (!row) return;
  const format = row.querySelector('[data-mqtt-field="format"]').value;
  const path = row.querySelector('[data-mqtt-field="valuePath"]');
  path.disabled = format === "text";
  if (format === "text") path.value = "";
  state.config.mqtt.sensors = Array.from(document.querySelectorAll("[data-mqtt-sensor]")).map(element =>
    Object.fromEntries(Array.from(element.querySelectorAll("[data-mqtt-field]")).map(input => [input.dataset.mqttField, input.value]))
  ).filter(sensor => sensor.label || sensor.topic || sensor.valuePath || sensor.unit);
  markDirty();
});
$("#mqttBroker").addEventListener("change", event => { state.config.mqtt.brokerUrl = event.target.value.trim(); markDirty(); });
$("#mqttAllowPlain").addEventListener("change", event => { state.config.mqtt.allowInsecureMqtt = event.target.checked; markDirty(); });
$("#mqttRefresh").addEventListener("change", event => { state.config.pages.find(page => page.id === "mqtt").refreshSeconds = Number(event.target.value); markDirty(); });
$("#storeMqttCredential").addEventListener("click", async () => {
  const button = $("#storeMqttCredential");
  button.disabled = true;
  const generation = ++state.mqttGeneration;
  try {
    const metadata = await requestJSON("/api/mqtt/credential", {method: "PUT", body: JSON.stringify({
      brokerUrl: $("#mqttBroker").value.trim(), username: $("#mqttUsername").value, password: $("#mqttPassword").value,
    })});
    $("#mqttUsername").value = "";
    $("#mqttPassword").value = "";
    if (generation !== state.mqttGeneration || app.hidden) return;
    state.mqttCredential = metadata;
    renderMqttCredential();
    toast("Credencial MQTT guardada no cofre. Aplique os ajustes separadamente.");
  } catch (error) { if (!app.hidden) toast(error.message, true); }
  finally { button.disabled = false; }
});
$("#removeMqttCredential").addEventListener("click", async () => {
  if (!confirm("Remover a credencial MQTT guardada? O acesso anônimo só funcionará se o broker permitir.")) return;
  try {
    await requestJSON("/api/mqtt/credential", {method: "DELETE"});
    state.mqttGeneration++;
    state.mqttCredential = {};
    $("#mqttUsername").value = "";
    $("#mqttPassword").value = "";
    renderMqttCredential();
    toast("Credencial MQTT removida.");
  } catch (error) { toast(error.message, true); }
});
$("#checkMqtt").addEventListener("click", async () => {
  const generation = ++state.mqttGeneration;
  const button = $("#checkMqtt"), feedback = $("#mqttStatus");
  button.disabled = true;
  feedback.textContent = "Consultando os ajustes aplicados, sem publicar comandos…";
  try {
    const result = await requestJSON("/api/mqtt/state");
    if (generation !== state.mqttGeneration || app.hidden) return;
    feedback.textContent = !result.available ? (result.loading ? "Consultando em segundo plano. Consulte novamente em alguns segundos." : result.error || "MQTT indisponível.")
      : `${result.received} de ${result.sensors.length} sensor(es) com valor. ${result.missingTopics.length ? "Sem dados: " + result.missingTopics.join(", ") + ". " : ""}${result.stale || result.error ? "CACHE: a consulta atual não confirmou estes valores. " : ""}Recebido não significa medido agora; valores retidos podem ser antigos.`;
  } catch (error) { if (generation === state.mqttGeneration && !app.hidden) feedback.textContent = error.message; }
  finally { if (generation === state.mqttGeneration) button.disabled = false; }
});

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
  state.config.customPages.forEach((definition) => {
    const row = document.createElement("div");
    row.className = "custom-source-row";
    row.innerHTML = `
      <span class="accent-dot accent-${escapeHTML(definition.accent)}"></span>
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
  state.dockerGeneration++;
  state.mqttGeneration++;
  $("#checkMqtt").disabled = false;
  $("#mqttStatus").textContent = "A consulta usa apenas os ajustes já aplicados, não este rascunho.";
  $("#checkDocker").disabled = false;
  $("#dockerStatus").textContent = "Os filtros só entram em vigor após Aplicar alterações. A consulta usa os ajustes já aplicados.";
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
  const target = state.displays.find(display => display.id === (state.previewProfile || state.activeDisplayProfile));
  if (target) {
    $("#previewImage").width = target.width;
    $("#previewImage").height = target.height;
    $("#previewImage").classList.toggle("monochrome-preview", target.colorMode === "1");
  }
  $("#previewProfileNote").textContent = state.previewProfile
    ? "Simulação de layout: não troca o hardware. O botão abaixo envia somente a página ao display físico configurado."
    : `Perfil físico configurado: ${target?.label || state.activeDisplayProfile}.`;
  $("#previewImage").src = `/api/preview?page=${encodeURIComponent(page.id)}${state.previewProfile ? "&profile=" + encodeURIComponent(state.previewProfile) : ""}&t=${Date.now()}`;
}

$("#previewProfile").addEventListener("change", event => { state.previewProfile = event.target.value; refreshPreview(); });

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

$("#dockerNames").addEventListener("change", event => {
  state.config.docker.names = event.target.value.split(",").map(name => name.trim()).filter(Boolean);
  markDirty();
});
$("#dockerRefresh").addEventListener("change", event => {
  state.config.pages.find(page => page.id === "docker").refreshSeconds = Number(event.target.value);
  markDirty();
});
$("#checkDocker").addEventListener("click", async () => {
  const generation = ++state.dockerGeneration;
  const button = $("#checkDocker");
  const feedback = $("#dockerStatus");
  button.disabled = true;
  feedback.textContent = "Consultando a configuração aplicada, sem alterar contêineres…";
  try {
    const result = await requestJSON("/api/docker/state");
    if (generation !== state.dockerGeneration || app.hidden) return;
    if (!result.available) {
      feedback.textContent = result.loading ? "Coletando em segundo plano. Consulte novamente em alguns segundos." : result.error || "Docker local indisponível.";
    } else {
      let text = `${result.total} contêiner(es): ${result.running} rodando, ${result.stopped} parado(s), ${result.unhealthy} não saudável(is)`;
      if (result.other) text += `, ${result.other} em outros estados`;
      if (result.missingNames.length) text += `. Nomes ausentes: ${result.missingNames.join(", ")}`;
      if (result.stale || result.error) text += ". CACHE: dados antigos; a última consulta não confirmou estes estados";
      feedback.textContent = text + ".";
    }
  } catch (error) {
    if (generation === state.dockerGeneration && !app.hidden) feedback.textContent = error.message;
  } finally {
    if (generation === state.dockerGeneration) button.disabled = false;
  }
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

function renderSourceTemplates() {
  const select = $("#sourceTemplate");
  select.replaceChildren();
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Configuração livre";
  select.appendChild(blank);
  state.sourceTemplates.forEach((template) => {
    const option = document.createElement("option");
    option.value = template.id;
    option.textContent = template.name;
    select.appendChild(option);
  });
}

function invalidateSourceTest() {
  state.sourceTestController?.abort();
  state.sourceTestController = null;
  state.sourceGeneration++;
  $("#testCustomSource").disabled = false;
  $("#inspectSourceSample").disabled = false;
  $("#buildSourceUrl").disabled = false;
  $("#sourceUrlResult").textContent = "";
  $("#sourceUrlResult").className = "source-test-result";
  $("#sourceTestResult").textContent = "";
  $("#sourceTestResult").className = "source-test-result";
}

function selectedSourceTemplate() {
  return state.sourceTemplates.find((template) => template.id === $("#sourceTemplate").value);
}

function showSourceTemplateExample() {
  invalidateSourceTest();
  const template = selectedSourceTemplate();
  $("#sourceTemplateDescription").textContent = template
    ? `${template.description} Clique em Usar modelo para preencher os campos; URL e identificação serão preservadas.`
    : "Escolha um modelo ou preencha livremente. Os caminhos dependem do JSON que seu app fornece.";
  $("#applySourceTemplate").disabled = !template;
  $("#sourceSample").value = JSON.stringify(template?.sample || {}, null, 2);
  $("#sourceUrlBuilder").hidden = !template?.endpoint;
  $("#sourceBaseUrl").value = "";
  $("#sourceUrlParameters").replaceChildren();
  $("#sourceUrlHelp").textContent = template?.endpoint?.help || "";
  $("#sourceUrlDocs").removeAttribute("href");
  if (template?.endpoint) {
    $("#sourceUrlDocs").href = template.endpoint.docsUrl;
    for (const field of template.endpoint.parameters) {
      const label = document.createElement("label");
      label.className = "compact-field";
      const span = document.createElement("span");
      span.textContent = field.label;
      const input = document.createElement("input");
      input.id = `sourceParam-${field.name}`;
      input.dataset.parameter = field.name;
      input.className = "text-input";
      input.maxLength = field.maxLength;
      input.value = field.default;
      input.autocomplete = "off";
      label.append(span, input);
      $("#sourceUrlParameters").appendChild(label);
    }
  }
}

$("#buildSourceUrl").addEventListener("click", async () => {
  const template = selectedSourceTemplate();
  if (!template?.endpoint) return;
  invalidateSourceTest();
  const generation = state.sourceGeneration;
  const controller = new AbortController();
  state.sourceTestController = controller;
  $("#buildSourceUrl").disabled = true;
  const result = $("#sourceUrlResult");
  result.textContent = "Montando URL, sem consultar a origem…";
  const parameters = Object.fromEntries([...$("#sourceUrlParameters").querySelectorAll("input")].map(input => [input.dataset.parameter, input.value]));
  try {
    const payload = await requestJSON("/api/sources/build-url", {method: "POST", signal: controller.signal,
      body: JSON.stringify({templateId: template.id, baseUrl: $("#sourceBaseUrl").value, parameters})});
    if (generation !== state.sourceGeneration || !$("#customDialog").open) return;
    const previous = $("#customUrl").value;
    if (previous && previous !== payload.url && !confirm("Substituir a URL neste formulário? A identificação e os demais campos serão preservados. Nada será salvo ou enviado ao display agora.")) {
      result.textContent = "URL anterior preservada.";
      return;
    }
    $("#customUrl").value = payload.url;
    result.textContent = "URL preenchida, sem conexão. Use Usar modelo para os caminhos e confira a unidade antes de testar ou guardar.";
  } catch (error) {
    if (generation !== state.sourceGeneration || error.name === "AbortError") return;
    result.className = "source-test-result error";
    result.textContent = error.message;
  } finally {
    if (generation === state.sourceGeneration) {
      state.sourceTestController = null;
      $("#buildSourceUrl").disabled = false;
    }
  }
});

$("#sourceTemplate").addEventListener("change", showSourceTemplateExample);
$("#applySourceTemplate").addEventListener("click", () => {
  const template = selectedSourceTemplate();
  if (!template) return;
  if ([$("#customTitle"), $("#customValuePath"), $("#customSecondaryPath"), $("#customUnit"), $("#customValueLabel")].some((input) => input.value)
      && !confirm("Substituir título, rótulo, caminhos, unidade, layout e cor pelo modelo? A URL e a identificação da fonte serão preservadas. Nada será aplicado ao display agora.")) return;
  const fields = {
    title: "#customTitle", valueLabel: "#customValueLabel", unit: "#customUnit",
    layout: "#customLayout", accent: "#customAccent", valuePath: "#customValuePath", secondaryPath: "#customSecondaryPath",
  };
  for (const [field, selector] of Object.entries(fields)) $(selector).value = template.fields[field];
  invalidateSourceTest();
  $("#sourceSampleDetails").open = true;
  $("#customUrl").focus();
});

$("#customForm").addEventListener("input", invalidateSourceTest);
$("#customForm").addEventListener("change", invalidateSourceTest);

function openCustomDialog(definition = null) {
  $("#customForm").reset();
  invalidateSourceTest();
  $("#sourceTemplate").value = "";
  showSourceTemplateExample();
  $("#sourceSampleDetails").open = false;
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

$("#customDialog").addEventListener("close", () => {
  invalidateSourceTest();
  $("#sourceSample").value = "";
  $("#sourceBaseUrl").value = "";
  $("#sourceUrlParameters").replaceChildren();
});

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

async function runSourceTest(offline) {
  if (!offline && !$("#customForm").reportValidity()) return;
  invalidateSourceTest();
  const generation = state.sourceGeneration;
  const controller = new AbortController();
  state.sourceTestController = controller;
  $("#testCustomSource").disabled = true;
  $("#inspectSourceSample").disabled = true;
  const result = $("#sourceTestResult");
  result.className = "source-test-result";
  result.textContent = offline ? "Conferindo exemplo…" : "Testando conexão…";
  try {
    let candidate;
    if (offline) {
      const sample = $("#sourceSample").value;
      if (new TextEncoder().encode(sample).length > 32 * 1024) throw new Error("O exemplo deve ter no máximo 32 KiB.");
      try { candidate = {sample: JSON.parse(sample), valuePath: $("#customValuePath").value.trim(), secondaryPath: $("#customSecondaryPath").value.trim()}; }
      catch (_) { throw new Error("O exemplo não é um JSON válido."); }
    } else candidate = customFormValue();
    const payload = await requestJSON(offline ? "/api/sources/inspect" : "/api/sources/test", {
      method: "POST",
      body: JSON.stringify(candidate),
      signal: controller.signal,
    });
    if (generation !== state.sourceGeneration) return;
    const detail = payload.secondary == null ? "" : ` · ${payload.secondary}`;
    result.textContent = `${offline ? "Exemplo conferido, sem conexão" : "Conexão aprovada"}: ${payload.value}${detail}`;
  } catch (error) {
    if (generation !== state.sourceGeneration || error.name === "AbortError") return;
    result.className = "source-test-result error";
    result.textContent = error.message;
  } finally {
    if (generation === state.sourceGeneration) {
      state.sourceTestController = null;
      $("#testCustomSource").disabled = false;
      $("#inspectSourceSample").disabled = false;
    }
  }
}

$("#testCustomSource").addEventListener("click", () => runSourceTest(false));
$("#inspectSourceSample").addEventListener("click", () => runSourceTest(true));

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
  toast("Fonte guardada no rascunho. Use Aplicar alterações para enviar ao display.");
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
    state.pomodoroGeneration++;
    state.dockerGeneration++;
    state.mqttGeneration++;
    $("#checkMqtt").disabled = false;
    $("#mqttStatus").textContent = "Ajustes aplicados. Consulte novamente para conferir os sensores.";
    $("#checkDocker").disabled = false;
    $("#dockerStatus").textContent = "Ajustes aplicados. Consulte novamente para conferir os contêineres.";
    refreshPomodoro();
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
    closeCustomDialog();
    closeIntegrationDialog();
    state.integrationsStatus = {};
    state.pomodoro = null;
    state.pomodoroGeneration++;
    state.dockerGeneration++;
    state.mqttGeneration++;
    state.mqttCredential = {};
    showAuth(true);
  }
});

setInterval(() => {
  if (!app.hidden) {
    refreshPreview();
    refreshDisplayState();
  }
}, 5000);

setInterval(() => {
  if (!app.hidden) {
    refreshPomodoro();
    const pages = state.config ? enabledPages() : [];
    if (["clock", "pomodoro"].includes(pages[state.previewIndex]?.id)) refreshPreview();
  }
}, 1000);

bootstrap();
