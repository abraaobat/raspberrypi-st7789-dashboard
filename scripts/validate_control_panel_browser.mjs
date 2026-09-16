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
  assert.equal(await page.locator(".page-row").count(), 7);
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
  const downloadPromise = page.waitForEvent("download");
  await page.locator('a[href="/api/config/export"]').click();
  const download = await downloadPromise;
  const exported = await fs.readFile(await download.path(), "utf8");
  assert(!exported.includes(fake));
  assert(!exported.includes("2468"));
  const restored = JSON.parse(exported);
  restored.carousel.enabled = true;
  await page.locator("#importConfigFile").setInputFiles({name: "backup.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(restored))});
  await page.waitForFunction(() => document.querySelector("#carouselEnabled").checked);
  const publicStatus = await page.evaluate(async () => (await fetch("/api/integrations/status")).json());
  assert(publicStatus.pihole.credentialConfigured && publicStatus.homeassistant.credentialConfigured);
  for (const width of [1440, 980, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow at ${width}px`);
    await page.locator('[data-configure-integration="homeassistant"]').click();
    assert(await page.locator("#integrationDialog").evaluate(element => element.scrollWidth <= element.clientWidth + 1));
    if (output) await page.screenshot({path: `${output}/control-mobile-${width}.png`});
    await page.keyboard.press("Escape");
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
  const calls = (await (await context.request.get(origin + "/fixture/status")).json()).calls;
  assert(calls.filter(call => call.path.startsWith("/api/states/")).every(call => call.method === "GET"));
  assert(calls.every(call => call.method === "GET" || call.path === "/api/auth"));
  assert.deepEqual(errors, []);
  console.log("PASS: guided connectors, HTTP consent, private credentials, binding, previews, backup/restore, responsive UI and preserved PIN. Fake services only.");
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
