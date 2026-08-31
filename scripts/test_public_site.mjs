import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { createServer, request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve, sep } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const siteRoot = resolve(projectRoot, "site");
const publicBase = "/personalization-control-plane/";
const screenshotDir = process.env.PCP_PUBLIC_E2E_SCREENSHOT_DIR;

if (typeof WebSocket !== "function") {
  throw new Error("The public-site browser test requires Node.js 22 or newer.");
}
if (!existsSync(join(siteRoot, "index.html"))) {
  throw new Error(`Static site not found at ${siteRoot}.`);
}
if (screenshotDir) {
  await mkdir(screenshotDir, { recursive: true });
}

async function collectTextFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectTextFiles(path));
    } else if ([".css", ".html", ".js", ".json", ".svg"].includes(extname(entry.name))) {
      files.push(path);
    }
  }
  return files;
}

for (const file of await collectTextFiles(siteRoot)) {
  const contents = await readFile(file, "utf8");
  assert.doesNotMatch(
    contents,
    /execute-api|wss:\/\/|amazonaws\.com/i,
    `Public artifact contains a private cloud endpoint marker: ${file}`,
  );
}

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".drawio": "application/xml; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }

  for (const command of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
    const found = spawnSync("which", [command], { encoding: "utf8" });
    if (found.status === 0 && found.stdout.trim()) return found.stdout.trim();
  }

  throw new Error("Chrome or Chromium is required for the public-site browser test.");
}

async function startStaticServer() {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || "/", "http://127.0.0.1");
      let pathname = decodeURIComponent(url.pathname);
      if (pathname === publicBase.slice(0, -1) || pathname === publicBase) {
        pathname = `${publicBase}index.html`;
      }
      if (!pathname.startsWith(publicBase)) {
        response.writeHead(404).end("Not found");
        return;
      }

      const relativePath = pathname.slice(publicBase.length);
      const filePath = resolve(siteRoot, relativePath);
      if (filePath !== siteRoot && !filePath.startsWith(`${siteRoot}${sep}`)) {
        response.writeHead(403).end("Forbidden");
        return;
      }

      const body = await readFile(filePath);
      response.writeHead(200, {
        "cache-control": "no-store",
        "content-type": contentTypes[extname(filePath)] || "application/octet-stream",
      });
      if (request.method === "HEAD") response.end();
      else response.end(body);
    } catch {
      response.writeHead(404).end("Not found");
    }
  });

  await new Promise((resolveListen, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  return { server, origin: `http://127.0.0.1:${port}` };
}

function requestJson(url, method = "GET") {
  return new Promise((resolveRequest, reject) => {
    const request = httpRequest(url, { method }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        body += chunk;
      });
      response.on("end", () => {
        if (!response.statusCode || response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(`HTTP ${response.statusCode || "unknown"}: ${body}`));
          return;
        }
        try {
          resolveRequest(JSON.parse(body));
        } catch (error) {
          reject(new Error(`Invalid JSON from ${url}: ${error}`));
        }
      });
    });
    request.setTimeout(2_000, () => {
      request.destroy(new Error(`Timed out requesting ${url}`));
    });
    request.once("error", reject);
    request.end();
  });
}

async function pollJson(url, chrome) {
  let lastError;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (chrome.exitCode !== null) {
      throw new Error(`Chrome exited before DevTools became available (code ${chrome.exitCode}).`);
    }
    try {
      return await requestJson(url);
    } catch (error) {
      lastError = error;
    }
    await delay(100);
  }
  throw new Error(`Timed out waiting for Chrome DevTools: ${lastError}`);
}

async function waitForDevToolsUrl(chrome, getOutput) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (chrome.exitCode !== null) {
      throw new Error(`Chrome exited before DevTools became available (code ${chrome.exitCode}).`);
    }
    const match = getOutput().match(/DevTools listening on (ws:\/\/\S+)/);
    if (match) return match[1];
    await delay(100);
  }
  throw new Error("Timed out waiting for Chrome to announce its DevTools endpoint.");
}

class CdpSession {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result || {});
        return;
      }
      const listeners = this.listeners.get(message.method);
      if (!listeners) return;
      for (const listener of [...listeners]) listener(message.params || {});
    });
  }

  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((resolveOpen, reject) => {
      socket.addEventListener("open", resolveOpen, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });
    return new CdpSession(socket);
  }

  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolveResult, reject) => {
      this.pending.set(id, { resolve: resolveResult, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || new Set();
    listeners.add(listener);
    this.listeners.set(method, listeners);
    return () => listeners.delete(listener);
  }

  once(method, timeoutMs = 10_000) {
    return new Promise((resolveEvent, reject) => {
      const timer = setTimeout(() => {
        unsubscribe();
        reject(new Error(`Timed out waiting for Chrome event ${method}`));
      }, timeoutMs);
      const unsubscribe = this.on(method, (params) => {
        clearTimeout(timer);
        unsubscribe();
        resolveEvent(params);
      });
    });
  }

  close() {
    this.socket.close();
  }
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    const description = (
      result.exceptionDetails.exception?.description
      || result.exceptionDetails.text
      || "Browser evaluation failed"
    );
    throw new Error(description);
  }
  return result.result?.value;
}

async function waitFor(cdp, expression, description, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await evaluate(cdp, expression);
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await delay(50);
  }
  throw new Error(`Timed out waiting for ${description}${lastError ? `: ${lastError}` : ""}`);
}

async function click(cdp, selector) {
  const serialized = JSON.stringify(selector);
  const clicked = await evaluate(cdp, `(() => {
    const element = document.querySelector(${serialized});
    if (!element || element.disabled) return false;
    element.scrollIntoView({ block: "center", inline: "center" });
    element.click();
    return true;
  })()`);
  assert.equal(clicked, true, `Missing or disabled clickable element ${selector}`);
  await delay(60);
}

async function navigate(cdp, url) {
  const loaded = cdp.once("Page.loadEventFired");
  await cdp.send("Page.navigate", { url });
  await loaded;
}

async function captureScreenshot(cdp, name) {
  if (!screenshotDir) return;
  const result = await cdp.send("Page.captureScreenshot", {
    captureBeyondViewport: false,
    format: "png",
    fromSurface: true,
  });
  await writeFile(join(screenshotDir, name), Buffer.from(result.data, "base64"));
}

function waitForProcessExit(process, timeoutMs) {
  if (process.exitCode !== null || process.signalCode !== null) {
    return Promise.resolve(true);
  }
  return new Promise((resolveExit) => {
    const onExit = () => {
      clearTimeout(timer);
      resolveExit(true);
    };
    const timer = setTimeout(() => {
      process.off("exit", onExit);
      resolveExit(false);
    }, timeoutMs);
    process.once("exit", onExit);
  });
}

const { server, origin } = await startStaticServer();
const profileDir = await mkdtemp(join(tmpdir(), "pcp-pages-chrome-"));
const chromePath = findChrome();
let chromeOutput = "";
const chromeArgs = [
  "--headless",
  "--disable-background-networking",
  "--disable-component-update",
  "--disable-default-apps",
  "--disable-dev-shm-usage",
  "--disable-extensions",
  "--disable-gpu",
  "--disable-sync",
  "--metrics-recording-only",
  "--mute-audio",
  "--no-default-browser-check",
  "--no-first-run",
  "--remote-debugging-address=127.0.0.1",
  "--remote-debugging-port=0",
  `--user-data-dir=${profileDir}`,
  "--window-size=1440,1000",
  "about:blank",
];
if (process.platform === "linux") chromeArgs.unshift("--no-sandbox");

const chrome = spawn(chromePath, chromeArgs, {
  stdio: ["ignore", "pipe", "pipe"],
});
for (const stream of [chrome.stdout, chrome.stderr]) {
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    chromeOutput = `${chromeOutput}${chunk}`.slice(-12_000);
  });
}

let cdp;
const browserExceptions = [];
const consoleErrors = [];
const requestedUrls = [];
const webSocketUrls = [];
const networkFailures = [];
const badResponses = [];

try {
  const browserWebSocketUrl = await waitForDevToolsUrl(chrome, () => chromeOutput);
  const devToolsOrigin = `http://${new URL(browserWebSocketUrl).host}`;
  await pollJson(`${devToolsOrigin}/json/version`, chrome);
  const target = await requestJson(
    `${devToolsOrigin}/json/new?${encodeURIComponent("about:blank")}`,
    "PUT",
  );
  cdp = await CdpSession.connect(target.webSocketDebuggerUrl);

  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Network.enable");
  cdp.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
    browserExceptions.push(
      exceptionDetails?.exception?.description || exceptionDetails?.text || "Unknown exception",
    );
  });
  cdp.on("Runtime.consoleAPICalled", ({ type, args }) => {
    if (type !== "error") return;
    consoleErrors.push(args.map((arg) => arg.value || arg.description || "").join(" "));
  });
  cdp.on("Network.requestWillBeSent", ({ request }) => {
    if (request?.url) requestedUrls.push(request.url);
  });
  cdp.on("Network.webSocketCreated", ({ url }) => {
    if (url) webSocketUrls.push(url);
  });
  cdp.on("Network.loadingFailed", ({ errorText, type, blockedReason }) => {
    networkFailures.push({ errorText, type, blockedReason });
  });
  cdp.on("Network.responseReceived", ({ response }) => {
    if (response?.status >= 400) {
      badResponses.push({ status: response.status, url: response.url });
    }
  });

  await navigate(cdp, `${origin}${publicBase}?public-site=true`);
  await waitFor(
    cdp,
    `document.documentElement.dataset.publicSite === "true"
      && document.querySelector("h1")?.innerText.includes("Optimize recommendations")`,
    "the canonical landing page",
  );
  const landing = await evaluate(cdp, `(() => ({
    copy: document.body.innerText,
    status: document.querySelector("#service-status")?.innerText,
    dashboardHref: document.querySelector('a[href="./dashboard.html"]')?.href,
    architectureHref: document.querySelector('a[href="./architecture.html"]')?.href,
    apiHref: document.querySelector("[data-local-api-link]")?.href,
  }))()`);
  assert.match(landing.copy, /Fictional seeded data/);
  assert.equal(landing.status, "published synthetic preview");
  assert.equal(landing.dashboardHref, `${origin}${publicBase}dashboard.html`);
  assert.equal(landing.architectureHref, `${origin}${publicBase}architecture.html`);
  assert.equal(
    landing.apiHref,
    "https://github.com/hk-775/personalization-control-plane/blob/main/docs/API.md",
  );
  await captureScreenshot(cdp, "personalization-control-plane-landing.png");

  await navigate(cdp, `${origin}${publicBase}architecture.html?public-site=true`);
  await waitFor(
    cdp,
    `document.documentElement.dataset.publicSite === "true"
      && Boolean(document.querySelector("#architecture-canvas"))
      && [...document.querySelectorAll(".architecture-figure img")]
        .every((image) => image.complete && image.naturalWidth > 0)`,
    "the architecture explorer and rendered diagrams",
  );
  const initialProgress = await evaluate(cdp, `document.querySelector("#flow-progress").innerText`);
  assert.match(initialProgress, /^STEP 01 \/ 06$/);
  await click(cdp, '[data-flow="breach"]');
  await waitFor(
    cdp,
    `document.querySelector('[data-flow="breach"]').classList.contains("is-active")
      && document.querySelectorAll(".arch-node.is-danger").length >= 2
      && document.querySelector("#arch-packet").style.left !== ""`,
    "the guardrail-breach architecture animation",
  );
  await click(cdp, "#flow-toggle");
  await waitFor(
    cdp,
    `document.querySelector("#flow-toggle").innerText === "Resume animation"`,
    "the paused architecture animation",
  );
  const pausedProgress = await evaluate(cdp, `document.querySelector("#flow-progress").innerText`);
  await delay(2_600);
  assert.equal(
    await evaluate(cdp, `document.querySelector("#flow-progress").innerText`),
    pausedProgress,
  );
  await click(cdp, "#flow-toggle");
  await waitFor(
    cdp,
    `document.querySelector("#flow-toggle").innerText === "Pause animation"`,
    "the resumed architecture animation",
  );
  await captureScreenshot(cdp, "personalization-control-plane-architecture.png");

  await navigate(cdp, `${origin}${publicBase}dashboard.html?public-site=true`);
  await waitFor(
    cdp,
    `document.documentElement.dataset.publicSite === "true"
      && document.querySelector("#health-chip")?.innerText === "published preview · read only"
      && document.querySelectorAll("#overview-metrics .metric-card").length === 4`,
    "the synthetic operator dashboard",
  );
  const dashboardBoundary = await evaluate(cdp, `(() => ({
    killDisabled: document.querySelector("#kill-switch-button").disabled,
    resetDisabled: document.querySelector("#reset-button").disabled,
    experiments: document.querySelectorAll("#overview-experiments tr").length,
    apiRequests: performance.getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((url) => url.includes("/api/")),
  }))()`);
  assert.equal(dashboardBoundary.killDisabled, true);
  assert.equal(dashboardBoundary.resetDisabled, true);
  assert.ok(dashboardBoundary.experiments >= 4);
  assert.deepEqual(dashboardBoundary.apiRequests, []);

  const dashboardViews = [
    ["experiments", "#experiments-table tr"],
    ["policies", "#policies-grid .policy-card"],
    ["cohorts", "#cohorts-table tr"],
    ["metrics", "#metrics-table tr"],
    ["guardrails", "#guardrail-evidence .activity-row"],
    ["approvals", "#audit-table tr"],
    ["demo", "#scenario-list .scenario-button"],
  ];
  for (const [view, contentSelector] of dashboardViews) {
    await click(cdp, `[data-view="${view}"]`);
    await waitFor(
      cdp,
      `document.querySelector('[data-view-panel="${view}"]').classList.contains("is-active")
        && document.querySelectorAll(${JSON.stringify(contentSelector)}).length > 0`,
      `the ${view} dashboard view`,
    );
  }

  const scenarios = [
    ["transparent-ranking", "Transparent deterministic ranking"],
    ["privacy-floor", "Minimum cohort privacy floor"],
    ["approval-gate", "Human approval for risky launches"],
    ["guardrail-rollback", "Automatic guardrail rollback"],
    ["kill-switch", "Global safe fallback"],
  ];
  for (const [scenario, title] of scenarios) {
    await click(cdp, `[data-scenario="${scenario}"]`);
    await waitFor(
      cdp,
      `document.querySelector(".demo-result h3")?.innerText === ${JSON.stringify(title)}
        && document.querySelector(".demo-result .state")?.innerText === "static walkthrough"`,
      title,
    );
  }
  await captureScreenshot(cdp, "personalization-control-plane-dashboard.png");

  await cdp.send("Emulation.setDeviceMetricsOverride", {
    deviceScaleFactor: 1,
    height: 844,
    mobile: true,
    screenHeight: 844,
    screenWidth: 390,
    width: 390,
  });
  await navigate(cdp, `${origin}${publicBase}?public-site=true`);
  await waitFor(
    cdp,
    `document.querySelector("h1")?.innerText.includes("Optimize recommendations")`,
    "the mobile landing page",
  );
  await click(cdp, ".nav-toggle");
  const mobile = await evaluate(cdp, `(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    navOpen: document.querySelector(".nav-links").classList.contains("is-open"),
  }))()`);
  assert.ok(mobile.scrollWidth <= mobile.innerWidth + 1, `Mobile overflow: ${JSON.stringify(mobile)}`);
  assert.equal(mobile.navOpen, true);
  await captureScreenshot(cdp, "personalization-control-plane-mobile.png");

  const httpRequests = requestedUrls.filter(
    (url) => url.startsWith("http://") || url.startsWith("https://"),
  );
  const unexpectedRequests = httpRequests.filter((url) => {
    const parsed = new URL(url);
    return parsed.origin !== origin
      || !parsed.pathname.startsWith(publicBase)
      || parsed.pathname.includes("/api/");
  });
  assert.deepEqual(
    unexpectedRequests,
    [],
    `Unexpected public-site requests: ${unexpectedRequests.join(", ")}`,
  );
  assert.deepEqual(webSocketUrls, [], `Unexpected WebSocket connections: ${webSocketUrls.join(", ")}`);
  assert.deepEqual(browserExceptions, [], `Browser exceptions: ${browserExceptions.join("\n")}`);
  assert.deepEqual(consoleErrors, [], `Browser console errors: ${consoleErrors.join("\n")}`);
  assert.deepEqual(badResponses, [], `HTTP error responses: ${JSON.stringify(badResponses)}`);
  assert.deepEqual(
    networkFailures.filter(({ errorText }) => errorText !== "net::ERR_ABORTED"),
    [],
    `Network failures: ${JSON.stringify(networkFailures)}`,
  );
  assert.ok(
    requestedUrls.some((url) => url.endsWith(`${publicBase}assets/static-data.js`)),
    "The synthetic dashboard data was not loaded from the Pages base path.",
  );
  assert.ok(
    requestedUrls.some((url) => url.endsWith(`${publicBase}assets/system-architecture.png`)),
    "The current architecture image was not loaded from the Pages base path.",
  );

  console.log(
    "public site e2e OK: landing, architecture diagrams and animation, "
      + "all dashboard views, 5 synthetic scenarios, mobile layout, and no API/WebSocket traffic",
  );
} catch (error) {
  if (cdp) {
    try {
      console.error(
        "Page state:",
        JSON.stringify(
          await evaluate(cdp, `(() => ({
            href: location.href,
            title: document.title,
            text: document.body?.innerText?.slice(0, 4000) || "",
          }))()`),
          null,
          2,
        ),
      );
    } catch (diagnosticError) {
      console.error("Unable to capture page state:", diagnosticError);
    }
  }
  console.error("Browser exceptions:", JSON.stringify(browserExceptions, null, 2));
  console.error("Requested URLs:", JSON.stringify(requestedUrls, null, 2));
  console.error("Network failures:", JSON.stringify(networkFailures, null, 2));
  if (chromeOutput) {
    console.error("Chrome output (tail):\n", chromeOutput);
  }
  throw error;
} finally {
  cdp?.close();
  if (chrome.exitCode === null && chrome.signalCode === null) {
    chrome.kill("SIGTERM");
  }
  if (!await waitForProcessExit(chrome, 3_000)) {
    chrome.kill("SIGKILL");
    await waitForProcessExit(chrome, 3_000);
  }
  server.close();
  await rm(profileDir, {
    recursive: true,
    force: true,
    maxRetries: 10,
    retryDelay: 100,
  });
}
