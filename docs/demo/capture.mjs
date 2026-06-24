// Records a real interaction video of the AgentDiff dashboard (dev server on the
// real sample run). Usage: node capture.mjs <scene> where scene ∈ hero|attribution|timeline|tour
// Playwright is resolved from ../../frontend/node_modules (the dashboard app).
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { createRequire } from "module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// Resolve playwright from PW_BASE (a dir or file to resolve relative to) if set,
// else expect `npm i playwright` somewhere up-tree. Capture is a dev-only tool;
// playwright is intentionally NOT a dependency of the dashboard app or CI.
const pwBase = process.env.PW_BASE || path.join(HERE, "package.json");
const require = createRequire(pwBase.endsWith(".json") ? pwBase : path.join(pwBase, "package.json"));
const { chromium } = require("playwright");

const SCENE = process.argv[2] || "tour";
const URL = process.env.URL || "http://localhost:5180/";
const OUT = path.join(HERE, "video", SCENE);
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 2,
  recordVideo: { dir: OUT, size: { width: 1280, height: 800 } },
});
const page = await ctx.newPage();
const wait = (ms) => page.waitForTimeout(ms);
const nav = (name) => page.getByRole("button", { name, exact: true }).first().click();
const scrollMain = (top) =>
  page.locator("main").evaluate((el, t) => el.scrollTo({ top: t, behavior: "smooth" }), top);
const scrollBottom = () =>
  page.locator("main").evaluate((el) => el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }));

await page.goto(URL, { waitUntil: "networkidle" });
await wait(2600); // initial load + one-time ember pulse + settle

if (SCENE === "shots") {
  // Still PNG of every dashboard window for the README gallery.
  const shotsDir = path.join(HERE, "shots");
  fs.mkdirSync(shotsDir, { recursive: true });
  const shot = async (name, navName, scrollTop = 0) => {
    if (navName) await nav(navName);
    await wait(1400);
    if (scrollTop) await page.locator("main").evaluate((el, t) => (el.scrollTop = t), scrollTop);
    await wait(700);
    await page.screenshot({ path: path.join(shotsDir, `${name}.png`) });
  };
  await shot("overview", null);
  await shot("behavioral-deltas", "Behavioral Deltas");
  await shot("attribution", "Causal Attribution");
  await shot("timeline", "Trajectory Timeline");
  await shot("run-summary", "Run Summary");
  await ctx.close();
  await browser.close();
  console.log("wrote shots", fs.readdirSync(shotsDir));
  process.exit(0);
}

if (SCENE === "hero" || SCENE === "tour") {
  await scrollMain(360);
  await wait(2200);
  await scrollBottom(); // the "output eval PASS / AgentDiff FAIL" thesis card
  await wait(3000);
  await scrollMain(0);
  await wait(1200);
}

if (SCENE === "tour") {
  await nav("Behavioral Deltas");
  await wait(2000);
  await page.getByRole("button", { name: "tallest_mountain" }).first().click().catch(() => {});
  await wait(1800);
}

if (SCENE === "attribution" || SCENE === "tour") {
  await nav("Causal Attribution");
  await wait(2200);
  await scrollMain(360); // diff hunk + Ollama explanation
  await wait(3200);
  await scrollMain(0);
  await wait(900);
}

if (SCENE === "timeline" || SCENE === "tour") {
  await nav("Trajectory Timeline");
  await wait(2200);
  await nav("candidate"); // fact_checker events disappear — the regression
  await wait(3000);
  await nav("baseline");
  await wait(1800);
}

if (SCENE === "tour") {
  await nav("Run Summary");
  await wait(1800);
  await scrollBottom();
  await wait(2000);
}

await ctx.close(); // finalizes the webm
await browser.close();
const files = fs.readdirSync(OUT).filter((f) => f.endsWith(".webm"));
console.log("wrote", OUT, files);
