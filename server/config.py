"""配置与不可变常量。
对应 openspec/specs/ 各域共享的口径/上限/枚举(由 refactor-server-app-by-domain 引入)。

注意:可变开关(DB_PATH/INGEST_KEY/ADMIN_KEY/各 RATE_*/TRASH_DAYS/STATE_TTL_SECONDS/
REQUIRE_TOKEN/READ_AUTH_OK/TRUST_PROXY/HSTS_FORCE)与路径常量(REPO_ROOT/FRONTEND_*/SHIMS_DIR/
INSTALL_PATH/LLMS_PATH/ROBOTS_PATH)留在 server/app.py — 测试通过 monkeypatch 改它们,
搬到这里会让 patch 失效。
"""
import os


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except Exception:  # pragma: no cover  — env 解析异常兜底
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:  # pragma: no cover
        return float(default)


# 静态文件 MIME(/shims 直出)。
_MEDIA = {".sh": "text/x-shellscript", ".py": "text/x-python",
          ".js": "text/javascript", ".mjs": "text/javascript",
          ".json": "application/json", ".md": "text/markdown"}

# 须以可执行位写出的 shim 文件清单(install.sh / 自更新会读)。
_EXECUTABLE_SHIMS = {
    "tf_client.sh", "tf_hooks.py", "tf_claude_hooks.py",
    "wrapper/tf-run", "wrapper/tf-hermes-hook.sh", "wrapper/tf-doctor",
}

# 启动期弱钥告警的样本集。
_WEAK_ADMIN_KEYS = {"devadmin", "admin", "password", "changeme", "test", "secret"}

# profile keys the shim MAY include on an event (all optional, opt-in)。
# NOTE: `shim_version` 不在此处 — 它走独立 sticky 表,见 agent_shim_versions。
PROFILE_KEYS = ("models", "config", "mcp", "skills", "integrations",
                "about", "tips", "cf", "instructions", "memory")

# 读侧鉴权未开时必须丢弃的敏感字段。
SENSITIVE_KEYS = ("input", "output", "instructions", "memory")

# §8 size limits。
MAX_BODY = 256 * 1024          # 拒绝整 POST > 该值 -> 413
MAX_CONTENT = 16 * 1024        # 持久化的 input/output,各
MAX_META = 4 * 1024            # 持久化的 meta json
MAX_SKILL_NAME = 160           # skill usage 元数据上限

# 保留与读窗口。
WINDOW_DAYS = 90

# skill mode 枚举(used / equipped)。
SKILL_MODES = {"used", "equipped"}

# 限流器来源条目硬上限,防海量来源撑爆内存。
_RATE_MAX_ENTRIES = 10000

# Skills catalog 同步。
CATALOG_URL = os.environ.get(
    "TF_SKILLS_CATALOG_URL",
    "https://github.com/tranfu-labs/tranfu-skills/releases/download/catalog/index.json",
)
CATALOG_TTL_SECONDS = _env_int("TF_SKILLS_CATALOG_TTL", 3600)
CATALOG_FETCH_TIMEOUT = _env_int("TF_SKILLS_CATALOG_TIMEOUT", 6)
CATALOG_COMPANY_TYPES = {"own", "meta"}
CATALOG_SOURCE_UNKNOWN = "非公司库"
