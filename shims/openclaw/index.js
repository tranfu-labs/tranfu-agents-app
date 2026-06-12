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
  },
});
