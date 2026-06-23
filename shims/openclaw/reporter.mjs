import { extractSkillNames } from "./skill-extract.mjs";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";

const DEFAULT_RUNTIME = "open-claw";
const DEFAULT_TRANFU_HOME = join(homedir(), ".tranfu");
const DEFAULT_MANIFEST_PATH = join(DEFAULT_TRANFU_HOME, "manifest.json");
const DEFAULT_SELFUPDATE_PATH = join(DEFAULT_TRANFU_HOME, "tf_selfupdate.py");

function readShimVersion(path) {
  try {
    const raw = readFileSync(path, "utf8");
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.version === "string" && parsed.version.trim()) {
      return parsed.version.trim();
    }
  } catch {
    // manifest absent or unreadable -> caller will omit shim_version (server
    // keeps the sticky value, frontend renders 'unknown' if never set).
  }
  return "";
}

function atPath(obj, path) {
  let cur = obj;
  for (const part of path.split(".")) {
    if (!cur || typeof cur !== "object") return "";
    cur = cur[part];
  }
  return typeof cur === "string" && cur.trim() ? cur.trim() : "";
}

export function sessionIdFrom(...values) {
  const paths = [
    "session_id", "sessionId", "session.id", "session.sessionId",
    "context.sessionId", "run.sessionId", "runId", "conversationId", "threadId", "id",
  ];
  for (const value of values) {
    if (!value || typeof value !== "object") continue;
    for (const path of paths) {
      const sid = atPath(value, path);
      if (sid) return sid;
    }
  }
  return "";
}

function contentToString(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object") return part.text || part.content || "";
      return "";
    }).join("\n");
  }
  return "";
}

export function findSystemPrompt(value, depth = 0) {
  if (typeof value === "string") return depth === 0 ? value : "";
  if (!value || typeof value !== "object" || depth > 5) return "";

  for (const key of ["systemPrompt", "system_prompt", "system", "prompt"]) {
    const found = contentToString(value[key]);
    if (found) return found;
  }
  for (const key of ["messages", "history", "conversation"]) {
    if (!Array.isArray(value[key])) continue;
    for (const msg of value[key]) {
      if (!msg || typeof msg !== "object") continue;
      if (String(msg.role || msg.type || "").toLowerCase() === "system") {
        const found = contentToString(msg.content || msg.text || msg.message);
        if (found) return found;
      }
    }
  }
  for (const nested of Object.values(value)) {
    const found = findSystemPrompt(nested, depth + 1);
    if (found) return found;
  }
  return "";
}

function normalizeConfig(config = {}, env = {}) {
  const server = String(config.server || env.TF_SERVER || "").replace(/\/+$/, "");
  const key = String(config.key || env.TF_KEY || "");
  const token = String(config.token || env.TF_TOKEN || "");
  const operator = String(config.operator || env.TF_OPERATOR || env.USER || "").trim();
  const agent = String(config.agent || env.TF_AGENT || "").trim();
  const runtime = String(config.runtime || env.TF_RUNTIME || DEFAULT_RUNTIME).trim() || DEFAULT_RUNTIME;
  const reportSkills = config.reportSkills !== false && env.TF_REPORT_SKILLS !== "0";
  return { server, key, token, operator, agent, runtime, reportSkills };
}

function newStats(sessionId) {
  return {
    sessionId,
    llmInputs: 0,
    promptMissing: 0,
    blockSeen: false,
    driftWarnings: 0,
    names: new Set(),
    postOk: 0,
    postFail: 0,
  };
}

async function postJson(fetchImpl, cfg, payload) {
  if (typeof fetchImpl !== "function") return { ok: false, status: "missing-fetch" };
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timeout = controller ? setTimeout(() => controller.abort(), 4000) : null;
  try {
    const headers = { "content-type": "application/json", "X-TF-Key": cfg.key };
    if (cfg.token) headers["X-TF-Token"] = cfg.token;
    const res = await fetchImpl(`${cfg.server}/v1/events`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller ? controller.signal : undefined,
    });
    return { ok: Boolean(res && res.ok), status: res ? res.status : "no-response" };
  } catch (err) {
    return { ok: false, status: err && err.name === "AbortError" ? "timeout" : "error" };
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

export function createOpenClawSkillReporter(config = {}, deps = {}) {
  const env = deps.env || (typeof process !== "undefined" ? process.env : {});
  const cfg = normalizeConfig(config, env);
  const logger = deps.logger || { write() {} };
  const fetchImpl = deps.fetch || globalThis.fetch;
  const manifestPath = deps.manifestPath || DEFAULT_MANIFEST_PATH;
  const selfupdatePath = deps.selfupdatePath || DEFAULT_SELFUPDATE_PATH;
  const spawnImpl = deps.spawn || spawn;
  const readShim = deps.readShimVersion || readShimVersion;
  let shimVersion = readShim(manifestPath);
  const state = new Map();
  const pending = new Set();

  function reloadShimVersion() {
    shimVersion = readShim(manifestPath);
    return shimVersion;
  }

  function spawnSelfUpdate() {
    // OpenClaw is long-lived, so SessionStart is the natural trigger. The
    // Python self-updater handles throttling (~/.tranfu/.selfupdate.json) and
    // is fully best-effort; we fire-and-forget and never let it impact the
    // host process. shim_version itself only reflects the new bundle on the
    // *next* OpenClaw startup, which matches the Python shim's behavior.
    if (env.TF_AUTO_UPDATE === "0") return;
    try {
      const child = spawnImpl("python3", [selfupdatePath], {
        detached: true,
        stdio: "ignore",
        env,
      });
      if (child && typeof child.unref === "function") child.unref();
      if (child && typeof child.on === "function") {
        child.on("error", () => {
          // python3 missing or selfupdate script absent — silent, by design.
        });
      }
    } catch {
      // spawn itself threw (e.g. no python3 in PATH) — telemetry must never
      // break the host agent.
    }
  }

  function track(task) {
    const tracked = Promise.resolve(task)
      .catch((err) => {
        try {
          logger.write("WARN", "background_error", {
            error: err && err.message ? err.message : String(err),
          });
        } catch {
          // OpenClaw hooks must never fail because reporting failed.
        }
      })
      .finally(() => pending.delete(tracked));
    pending.add(tracked);
  }

  async function flush() {
    await Promise.allSettled(Array.from(pending));
  }

  function getStats(sessionId) {
    const sid = sessionId || "unknown";
    if (!state.has(sid)) state.set(sid, newStats(sid));
    return state.get(sid);
  }

  function sessionStart(event = {}, context = {}) {
    const sessionId = sessionIdFrom(event, context);
    const stats = getStats(sessionId);
    spawnSelfUpdate();
    logger.write("INFO", "session_start", {
      session_id: stats.sessionId,
      reportSkills: cfg.reportSkills,
      missingConfig: !(cfg.server && cfg.operator),
    });
  }

  function llmInput(event = {}, context = {}) {
    if (!cfg.reportSkills) return;
    const sessionId = sessionIdFrom(event, context);
    const stats = getStats(sessionId);
    stats.llmInputs += 1;
    const prompt = findSystemPrompt(event) || findSystemPrompt(context);
    if (!prompt) {
      stats.promptMissing += 1;
      return;
    }
    const result = extractSkillNames(prompt);
    stats.blockSeen = stats.blockSeen || result.blockSeen;
    if (result.blockSeen && result.names.length === 0) {
      stats.driftWarnings += 1;
      logger.write("WARN", "format_drift", {
        session_id: stats.sessionId,
        blockSeen: true,
        blockLength: result.blockLength,
        extracted: 0,
      });
      return;
    }
    for (const name of result.names) stats.names.add(name);
  }

  async function postAndLog(summary) {
    if (summary.reportSkills && !summary.missingConfig && summary.session_id !== "unknown") {
      await Promise.all(summary.skills.map(async (name) => {
        const payload = {
          v: "0.1",
          operator: cfg.operator,
          runtime: cfg.runtime,
          session_id: summary.session_id,
          status: "done",
          current_step: `skill(equipped): ${name}`,
          skill: name,
          skill_mode: "equipped",
        };
        if (cfg.agent) payload.agent = cfg.agent;
        if (shimVersion) payload.shim_version = shimVersion;
        const res = await postJson(fetchImpl, cfg, payload);
        if (res.ok) summary.postOk += 1;
        else summary.postFail += 1;
      }));
    }
    logger.write("INFO", "session_end", {
      session_id: summary.session_id,
      llmInputs: summary.llmInputs,
      promptMissing: summary.promptMissing,
      blockSeen: summary.blockSeen,
      driftWarnings: summary.driftWarnings,
      skillCount: summary.skills.length,
      skills: summary.skills,
      postOk: summary.postOk,
      postFail: summary.postFail,
      missingConfig: summary.missingConfig,
      reportSkills: summary.reportSkills,
    });
  }

  function sessionEnd(event = {}, context = {}) {
    const sessionId = sessionIdFrom(event, context);
    const stats = getStats(sessionId);
    const summary = {
      session_id: stats.sessionId,
      llmInputs: stats.llmInputs,
      promptMissing: stats.promptMissing,
      blockSeen: stats.blockSeen,
      driftWarnings: stats.driftWarnings,
      skills: Array.from(stats.names).sort(),
      postOk: 0,
      postFail: 0,
      missingConfig: !(cfg.server && cfg.operator),
      reportSkills: cfg.reportSkills,
    };
    track(postAndLog(summary));
    state.delete(stats.sessionId);
  }

  return {
    sessionStart, llmInput, sessionEnd, flush,
    reloadShimVersion,
    _stateSize: () => state.size,
    _shimVersion: () => shimVersion,
  };
}
