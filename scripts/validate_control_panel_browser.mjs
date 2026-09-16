import assert from "node:assert/strict";
import {createRequire} from "node:module";
import fs from "node:fs/promises";

const require = createRequire(import.meta.url);
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const origin = process.env.CONTROL_PANEL_URL || "http://127.0.0.1:8093";
const output = process.env.BROWSER_EVIDENCE_DIR;
const browser = await chromium.launch({headless: true, ...(process.env.BROWSER_CHANNEL ? {channel: process.env.BROWSER_CHANNEL} : {})});
const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
const page = await context.newPage();
const errors = [];
page.on("pageerror", error => errors.push(error.message));
page.on("console", message => { if (message.type() === "error" && !message.text().includes("400")) errors.push(message.text()); });
page.on("dialog", dialog => dialog.accept());
const fake = "browser-fixture-only";
try {
  await page.goto(origin);
  await page.locator("#authScreen").waitFor({state: "visible"});
  assert.match(await page.locator("#authTitle").innerText(), /Proteja/);
  await page.locator("#pinInput").fill("2468");
  await page.locator("#authButton").click();
  await page.locator("#app").waitFor({state: "visible"});
  assert.equal(await page.locator(".page-row").count(), 9);
  assert.equal(await page.getByRole("checkbox", {name: "Ativar Relógio", exact: true}).isChecked(), false);
  assert.equal(await page.getByRole("checkbox", {name: "Ativar Pomodoro", exact: true}).isChecked(), false);
  const fixture = await (await context.request.get(origin + "/fixture/status")).json();
  for (const id of ["pihole", "homeassistant"]) {
    await page.locator(`[data-configure-integration="${id}"]`).click();
    await page.locator("#integrationUrl").fill(fixture.baseUrl);
    await page.locator("#integrationSecret").fill(fake);
    if (id === "homeassistant") await page.locator("#integrationEntities").fill("sensor.temperature, binary_sensor.door");
    await page.locator("#testIntegration").click();
    await page.waitForFunction(() => document.querySelector("#integrationTestResult").textContent.includes("explicitamente"));
    await page.locator("#integrationAllowHttp").check();
    await page.locator("#testIntegration").click();
    await page.waitForFunction(() => /Conexão (aprovada|concluída)/.test(document.querySelector("#integrationTestResult").textContent));
    const status = await page.evaluate(async () => (await fetch("/api/integrations/status")).json());
    assert.equal(status[id].credentialConfigured, false, "Testing must not persist credentials");
    await page.locator("#storeIntegrationCredential").click();
    await page.waitForFunction(() => document.querySelector("#integrationTestResult").textContent.includes("Credencial guardada"));
    assert.equal(await page.locator("#integrationSecret").inputValue(), "");
    await page.locator("#integrationActivate").check();
    if (output) {
      await fs.mkdir(output, {recursive: true});
      await page.screenshot({path: `${output}/${id}-assistant.png`});
    }
    await page.locator("#saveIntegrationSettings").click();
    await page.locator("#integrationDialog").waitFor({state: "hidden"});
    await page.locator("#saveButton").click();
    await page.waitForFunction(() => document.querySelector("#saveState").textContent === "Configuração aplicada");
    await page.locator(`[data-configure-integration="${id}"]`).click();
    assert.equal(await page.locator("#integrationSecret").inputValue(), "");
    await page.locator("#integrationUrl").fill("http://127.0.0.1:1");
    await page.locator("#testIntegration").click();
    await page.waitForFunction(() => document.querySelector("#integrationTestResult").textContent.includes("para este endereço"));
    await page.locator("#cancelIntegrationDialog").click();
  }
  const config = await page.evaluate(async () => (await fetch("/api/config")).json());
  assert.equal(config.pages.filter(item => item.enabled).length, 5);
  for (const id of ["pihole", "homeassistant"]) {
    const preview = await context.request.get(origin + `/api/preview?page=${id}`);
    assert.equal(preview.status(), 200);
    assert.match(preview.headers()["content-type"], /image\/png/);
    // First frame may be loading; wait for actual provider output via the fixture requests.
    await page.waitForFunction(async id => {
      const fixture = await (await fetch("/fixture/status")).json();
      return fixture.calls.some(call => call.path.includes(id === "pihole" ? "/api/stats/summary" : "/api/states/"));
    }, id);
    const frame = await context.request.get(origin + `/api/preview?page=${id}`);
    if (output) await fs.writeFile(`${output}/${id}-preview.png`, await frame.body());
  }
  await page.getByRole("checkbox", {name: "Ativar Relógio", exact: true}).check();
  await page.getByRole("checkbox", {name: "Ativar Pomodoro", exact: true}).check();
  await page.locator("#clockTimezone").fill("America/Boa_Vista");
  await page.locator("#clockShowSeconds").uncheck();
  await page.locator("#clockHour24").uncheck();
  await page.locator("#pomodoroMinutes").fill("1");
  await page.locator("#clockTimezone").focus();
  await page.locator("#pomodoroStart").click();
  await page.waitForFunction(() => document.querySelector("#toast").textContent.includes("Aplique ou descarte"));
  assert.equal((await (await context.request.get(origin + "/api/pomodoro/state")).json()).status, "idle");
  await page.locator("#saveButton").click();
  await page.waitForFunction(() => document.querySelector("#saveState").textContent === "Configuração aplicada");
  await page.waitForFunction(() => document.querySelector("#pomodoroCountdown").textContent === "01:00");
  const deskSettings = await (await context.request.get(origin + "/api/config")).json();
  assert.deepEqual(deskSettings.clock, {timezone: "America/Boa_Vista", showSeconds: false, hour24: false});
  assert.equal(deskSettings.pages.filter(item => item.enabled).length, 7);
  // A poll started before a command must not overwrite its newer result.
  let releasePoll;
  let sawPoll;
  const pollSeen = new Promise(resolve => { sawPoll = resolve; });
  const delayedPoll = new Promise(resolve => { releasePoll = resolve; });
  const oldSnapshot = await (await context.request.get(origin + "/api/pomodoro/state")).json();
  await page.route("**/api/pomodoro/state", async route => {
    sawPoll();
    await delayedPoll;
    await route.fulfill({status: 200, contentType: "application/json", body: JSON.stringify(oldSnapshot)});
  }, {times: 1});
  await pollSeen;
  await page.locator("#pomodoroStart").click();
  await page.waitForFunction(() => document.querySelector("#pomodoroStatus").textContent === "Foco em andamento");
  const staleResponse = page.waitForResponse(response => response.url().endsWith("/api/pomodoro/state"));
  releasePoll();
  await staleResponse;
  assert.equal(await page.locator("#pomodoroStatus").innerText(), "Foco em andamento");
  await page.locator("#pomodoroPause").click();
  await page.waitForFunction(() => document.querySelector("#pomodoroStatus").textContent === "Pausado");
  const pausedCycle = await (await context.request.get(origin + "/api/pomodoro/state")).json();
  await page.reload();
  await page.locator("#app").waitFor({state: "visible"});
  await page.waitForFunction(() => document.querySelector("#pomodoroStatus").textContent === "Pausado");
  assert.deepEqual(await (await context.request.get(origin + "/api/pomodoro/state")).json(), pausedCycle);
  for (const id of ["clock", "pomodoro"]) {
    const frame = await context.request.get(origin + `/api/preview?page=${id}`);
    assert.equal(frame.status(), 200);
    assert.match(frame.headers()["content-type"], /image\/png/);
    if (output) await fs.writeFile(`${output}/${id}-preview.png`, await frame.body());
  }
  const downloadPromise = page.waitForEvent("download");
  await page.locator('a[href="/api/config/export"]').click();
  const download = await downloadPromise;
  const exported = await fs.readFile(await download.path(), "utf8");
  assert(!exported.includes(fake));
  assert(!exported.includes("2468"));
  const restored = JSON.parse(exported);
  restored.carousel.enabled = true;
  restored.pomodoro.minutes = 2;
  await page.locator("#importConfigFile").setInputFiles({name: "backup.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(restored))});
  await page.waitForFunction(() => document.querySelector("#carouselEnabled").checked);
  const publicStatus = await page.evaluate(async () => (await fetch("/api/integrations/status")).json());
  assert(publicStatus.pihole.credentialConfigured && publicStatus.homeassistant.credentialConfigured);
  assert.deepEqual(await (await context.request.get(origin + "/api/pomodoro/state")).json(), pausedCycle,
    "Import must preserve the active cycle, not restart it with the new duration");
  for (const width of [1440, 980, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow at ${width}px`);
    await page.locator('[data-configure-integration="homeassistant"]').click();
    assert(await page.locator("#integrationDialog").evaluate(element => element.scrollWidth <= element.clientWidth + 1));
    if (output) await page.screenshot({path: `${output}/control-mobile-${width}.png`});
    await page.keyboard.press("Escape");
    await page.locator("#pomodoroStart").scrollIntoViewIfNeeded();
    if (output) await page.screenshot({path: `${output}/desk-${width}.png`});
  }
  await page.locator('[data-configure-integration="pihole"]').click();
  await page.locator("#removeIntegrationCredential").click();
  await page.waitForFunction(() => document.querySelector("#integrationTestResult").textContent.includes("removida"));
  await page.locator("#cancelIntegrationDialog").click();
  const removed = await page.evaluate(async () => (await fetch("/api/integrations/status")).json());
  assert.equal(removed.pihole.credentialConfigured, false);
  assert.equal(removed.homeassistant.credentialConfigured, true);
  await page.locator("#logoutButton").click();
  await page.locator("#authScreen").waitFor({state: "visible"});
  await page.locator("#pinInput").fill("2468");
  await page.locator("#authButton").click();
  await page.locator("#app").waitFor({state: "visible"});
  await page.waitForFunction(() => document.querySelector("#pomodoroStatus").textContent === "Pausado");
  await page.locator("#pomodoroResume").click();
  await page.waitForFunction(() => document.querySelector("#pomodoroStatus").textContent === "Foco em andamento");
  assert.equal((await (await context.request.get(origin + "/api/pomodoro/state")).json()).totalSeconds, 60);
  await page.locator("#pomodoroReset").click();
  await page.waitForFunction(() => document.querySelector("#pomodoroStatus").textContent === "Pronto para focar"
    && document.querySelector("#pomodoroCountdown").textContent === "02:00");
  const calls = (await (await context.request.get(origin + "/fixture/status")).json()).calls;
  assert(calls.filter(call => call.path.startsWith("/api/states/")).every(call => call.method === "GET"));
  assert(calls.every(call => call.method === "GET" || call.path === "/api/auth"));
  assert.deepEqual(errors, []);
  console.log("PASS: connectors, clock, Pomodoro start/pause/resume/reset, stale-poll protection, reload/login persistence, backup/restore, responsive UI and preserved PIN. Fake services only.");
} catch (error) {
  if (output) {
    await fs.mkdir(output, {recursive: true});
    await page.screenshot({path: `${output}/failure.png`});
  }
  throw error;
} finally {
  await context.close();
  await browser.close();
}
