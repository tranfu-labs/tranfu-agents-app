import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { appendLogLine, createFileLogger } from "../shims/openclaw/logger.mjs";
import { createOpenClawSkillReporter } from "../shims/openclaw/reporter.mjs";
import { extractSkillNames } from "../shims/openclaw/skill-extract.mjs";

test("extractSkillNames handles name attributes and dedupes", () => {
  const text = `<skills><skill name="alpha">ignore description</skill><skill name='beta'/><skill name="alpha"/></skills>`;
  assert.deepEqual(extractSkillNames(text), {
    names: ["alpha", "beta"],
    blockSeen: true,
    blockLength: text.length,
  });
});

test("extractSkillNames distinguishes no block from drift", () => {
  assert.deepEqual(extractSkillNames("plain prompt"), { names: [], blockSeen: false, blockLength: 0 });
  const drift = extractSkillNames("<skills><skill><description>Only prose here with too many words to be a name</description></skill></skills>");
  assert.equal(drift.blockSeen, true);
  assert.deepEqual(drift.names, []);
  assert.ok(drift.blockLength > 0);
});

test("reporter dedupes per session and posts equipped payloads", async () => {
  const posts = [];
  const logger = { rows: [], write(level, event, data) { this.rows.push({ level, event, data }); } };
  const reporter = createOpenClawSkillReporter({
    server: "https://tranfu.invalid/",
    key: "secret",
    operator: "alice",
    agent: "copy",
  }, {
    logger,
    env: {},
    fetch: async (url, options) => {
      posts.push({ url, payload: JSON.parse(options.body), headers: options.headers });
      return { ok: true, status: 200 };
    },
  });

  reporter.sessionStart({ sessionId: "s1" });
  reporter.llmInput({ sessionId: "s1", systemPrompt: `<skills><skill name="alpha"/><skill name="beta"/></skills>` });
  reporter.llmInput({ sessionId: "s1", systemPrompt: `<skills><skill name="alpha"/></skills>` });
  reporter.sessionEnd({ sessionId: "s1" });
  await reporter.flush();

  assert.equal(posts.length, 2);
  assert.deepEqual(posts.map((p) => p.payload.skill).sort(), ["alpha", "beta"]);
  assert.ok(posts.every((p) => p.payload.skill_mode === "equipped"));
  assert.ok(posts.every((p) => p.payload.runtime === "open-claw"));
  assert.ok(posts.every((p) => p.headers["X-TF-Key"] === "secret"));
  const summary = logger.rows.find((row) => row.event === "session_end");
  assert.equal(summary.data.skillCount, 2);
  assert.equal(reporter._stateSize(), 0);
});

test("reporter respects TF_REPORT_SKILLS=0", async () => {
  let called = false;
  const reporter = createOpenClawSkillReporter({
    server: "https://tranfu.invalid",
    operator: "alice",
  }, {
    env: { TF_REPORT_SKILLS: "0" },
    fetch: async () => {
      called = true;
      return { ok: true, status: 200 };
    },
  });
  reporter.llmInput({ sessionId: "s1", systemPrompt: `<skills><skill name="alpha"/></skills>` });
  reporter.sessionEnd({ sessionId: "s1" });
  await reporter.flush();
  assert.equal(called, false);
});

test("reporter does not block session_end on slow posts", async () => {
  let releaseFetch;
  const reporter = createOpenClawSkillReporter({
    server: "https://tranfu.invalid",
    operator: "alice",
  }, {
    env: {},
    fetch: async () => new Promise((resolve) => {
      releaseFetch = () => resolve({ ok: true, status: 200 });
    }),
  });

  reporter.llmInput({ sessionId: "s1", systemPrompt: `<skills><skill name="alpha"/></skills>` });
  reporter.sessionEnd({ sessionId: "s1" });

  assert.equal(reporter._stateSize(), 0);
  releaseFetch();
  await reporter.flush();
});

test("reporter summary exposes the six silent failure checkpoints", async () => {
  const rows = [];
  const logger = { write(level, event, data) { rows.push({ level, event, data }); } };
  const reporter = createOpenClawSkillReporter({
    server: "https://tranfu.invalid",
    operator: "alice",
  }, {
    logger,
    env: {},
    fetch: async (_url, options) => {
      const payload = JSON.parse(options.body);
      return { ok: payload.skill === "ok-skill", status: payload.skill === "ok-skill" ? 200 : 500 };
    },
  });

  reporter.sessionEnd({ sessionId: "no-input" });
  await reporter.flush();
  reporter.llmInput({ sessionId: "missing-prompt", tool: "x" });
  reporter.sessionEnd({ sessionId: "missing-prompt" });
  await reporter.flush();
  reporter.llmInput({ sessionId: "no-block", systemPrompt: "plain system prompt" });
  reporter.sessionEnd({ sessionId: "no-block" });
  await reporter.flush();
  reporter.llmInput({ sessionId: "drift", systemPrompt: "<skills><skill><description>Only prose with no name field and too many words here</description></skill></skills>" });
  reporter.sessionEnd({ sessionId: "drift" });
  await reporter.flush();
  reporter.llmInput({ sessionId: "posts", systemPrompt: '<skills><skill name="ok-skill"/><skill name="bad-skill"/></skills>' });
  reporter.sessionEnd({ sessionId: "posts" });
  await reporter.flush();

  const bySession = Object.fromEntries(rows
    .filter((row) => row.event === "session_end")
    .map((row) => [row.data.session_id, row.data]));
  assert.equal(bySession["no-input"].llmInputs, 0);
  assert.equal(bySession["missing-prompt"].promptMissing, 1);
  assert.equal(bySession["no-block"].blockSeen, false);
  assert.equal(rows.some((row) => row.event === "format_drift" && row.level === "WARN"), true);
  assert.equal(bySession.drift.driftWarnings, 1);
  assert.equal(bySession.posts.postOk, 1);
  assert.equal(bySession.posts.postFail, 1);

  const missingRows = [];
  const missing = createOpenClawSkillReporter({}, { logger: { write(level, event, data) { missingRows.push({ level, event, data }); } }, env: {} });
  missing.sessionStart({ sessionId: "missing-config" });
  missing.sessionEnd({ sessionId: "missing-config" });
  await missing.flush();
  const missingSummary = missingRows.find((row) => row.event === "session_end");
  assert.equal(missingRows.find((row) => row.event === "session_start").data.missingConfig, true);
  assert.equal(missingSummary.data.missingConfig, true);
});

test("reporter attaches shim_version on every equipped post", async () => {
  const posts = [];
  const reporter = createOpenClawSkillReporter({
    server: "https://tranfu.invalid/",
    key: "secret",
    operator: "alice",
    agent: "copy",
  }, {
    env: {},
    fetch: async (_url, options) => {
      posts.push(JSON.parse(options.body));
      return { ok: true, status: 200 };
    },
    manifestPath: "/does/not/matter",
    readShimVersion: () => "fixed-shim-1234",
  });

  reporter.llmInput({ sessionId: "s1", systemPrompt: `<skills><skill name="alpha"/></skills>` });
  reporter.sessionEnd({ sessionId: "s1" });
  await reporter.flush();

  assert.equal(posts.length, 1);
  assert.equal(posts[0].shim_version, "fixed-shim-1234");
});

test("reporter omits shim_version when manifest is unreadable", async () => {
  const posts = [];
  const reporter = createOpenClawSkillReporter({
    server: "https://tranfu.invalid/",
    key: "secret",
    operator: "alice",
    agent: "copy",
  }, {
    env: {},
    fetch: async (_url, options) => {
      posts.push(JSON.parse(options.body));
      return { ok: true, status: 200 };
    },
    readShimVersion: () => "",
  });

  reporter.llmInput({ sessionId: "s1", systemPrompt: `<skills><skill name="alpha"/></skills>` });
  reporter.sessionEnd({ sessionId: "s1" });
  await reporter.flush();

  assert.equal(posts.length, 1);
  assert.equal("shim_version" in posts[0], false);
});

test("reloadShimVersion picks up a refreshed manifest", () => {
  let current = "v1";
  const reporter = createOpenClawSkillReporter({
    server: "https://tranfu.invalid/",
    key: "secret",
    operator: "alice",
  }, {
    env: {},
    fetch: async () => ({ ok: true, status: 200 }),
    readShimVersion: () => current,
  });
  assert.equal(reporter._shimVersion(), "v1");
  current = "v2";
  assert.equal(reporter.reloadShimVersion(), "v2");
  assert.equal(reporter._shimVersion(), "v2");
});

test("logger redacts prompt-like fields and truncates oversized files", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "tranfu-openclaw-"));
  const filePath = path.join(dir, "openclaw-skill.log");
  appendLogLine(filePath, "x".repeat(100), { maxBytes: 10, keepBytes: 5 });
  appendLogLine(filePath, "tail", { maxBytes: 10, keepBytes: 5 });
  assert.ok(fs.readFileSync(filePath, "utf8").includes("tail"));

  const logger = createFileLogger({ filePath, maxBytes: 1024, keepBytes: 512 });
  logger.write("WARN", "format_drift", { session_id: "s1", prompt: "secret prompt", blockLength: 42 });
  const last = fs.readFileSync(filePath, "utf8").trim().split("\n").pop();
  assert.ok(!last.includes("secret prompt"));
  assert.ok(last.includes("[redacted]"));
});
