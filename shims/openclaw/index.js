import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { createFileLogger } from "./logger.mjs";
import { createOpenClawSkillReporter } from "./reporter.mjs";

const PLUGIN_ID = "tranfu-skill-reporter";
const logger = createFileLogger();

function registerHook(api, name, handler) {
  try {
    api.on(name, (...args) => {
      try {
        return handler(...args);
      } catch (err) {
        logger.write("WARN", "hook_error", {
          hook: name,
          error: err && err.message ? err.message : String(err),
        });
        return undefined;
      }
    });
  } catch (err) {
    logger.write("WARN", "hook_register_failed", {
      hook: name,
      error: err && err.message ? err.message : String(err),
    });
  }
}

export default definePluginEntry({
  id: PLUGIN_ID,
  name: "TRANFU Skill Reporter",
  description: "Reports OpenClaw prompt-equipped skill names to TRANFU//AGENTS.",
  register(api) {
    const reporter = createOpenClawSkillReporter(api.pluginConfig || {}, { logger });
    registerHook(api, "session_start", reporter.sessionStart);
    registerHook(api, "llm_input", reporter.llmInput);
    registerHook(api, "session_end", reporter.sessionEnd);
    // SIGUSR1 lets the self-updater nudge a long-lived OpenClaw process to
    // re-read manifest.json without restarting — JS plugin code itself still
    // needs a restart to load new logic, but the version label updates live.
    if (typeof process !== "undefined" && typeof process.on === "function") {
      try {
        process.on("SIGUSR1", () => {
          try {
            const v = reporter.reloadShimVersion();
            logger.write("INFO", "shim_version_reloaded", { shim_version: v || null });
          } catch {
            // signal handler must never throw
          }
        });
      } catch {
        // platforms without SIGUSR1 (e.g. Windows) silently skip
      }
    }
  },
});
