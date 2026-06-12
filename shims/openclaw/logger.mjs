import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const DEFAULT_MAX_BYTES = 1024 * 1024;
const DEFAULT_KEEP_BYTES = 512 * 1024;
const REDACT_KEYS = new Set(["prompt", "systemPrompt", "input", "output", "description", "body", "content", "code"]);

function safeData(value) {
  if (Array.isArray(value)) return value.map(safeData);
  if (!value || typeof value !== "object") return value;
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    out[key] = REDACT_KEYS.has(key) ? "[redacted]" : safeData(item);
  }
  return out;
}

export function defaultLogPath() {
  return path.join(os.homedir(), ".tranfu", "logs", "openclaw-skill.log");
}

export function appendLogLine(filePath, line, options = {}) {
  const maxBytes = options.maxBytes || DEFAULT_MAX_BYTES;
  const keepBytes = options.keepBytes || DEFAULT_KEEP_BYTES;
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    if (fs.existsSync(filePath) && fs.statSync(filePath).size > maxBytes) {
      const fd = fs.openSync(filePath, "r");
      try {
        const size = fs.statSync(filePath).size;
        const start = Math.max(0, size - keepBytes);
        const buffer = Buffer.alloc(size - start);
        fs.readSync(fd, buffer, 0, buffer.length, start);
        fs.writeFileSync(filePath, buffer);
      } finally {
        fs.closeSync(fd);
      }
    }
    fs.appendFileSync(filePath, line + "\n", "utf8");
  } catch {
    // Telemetry diagnostics must never break OpenClaw.
  }
}

export function createFileLogger(options = {}) {
  const filePath = options.filePath || defaultLogPath();
  return {
    filePath,
    write(level, event, data = {}) {
      const row = {
        ts: new Date().toISOString(),
        level,
        event,
        ...safeData(data),
      };
      appendLogLine(filePath, JSON.stringify(row), options);
    },
  };
}
