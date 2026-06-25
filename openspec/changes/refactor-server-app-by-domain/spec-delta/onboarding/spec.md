# Delta:onboarding(安装与接入域)— refactor-server-app-by-domain

## 修改:事实来源

### 原(spec.md 第 3 行)
```
事实来源:`install.sh`、`server/app.py`(`/install.sh`、`/shims/{path}`、`/shims/manifest`)、`shims/*`、`QUICKSTART.md`/`USAGE.md`。
```

### 改为
```
事实来源:`install.sh`、`server/routes/onboarding.py`(`/install.sh` / `/shims/{path}` / `/shims/manifest` /
        `/llms.txt` / `/robots.txt` / `/healthz` / SPA 路由)、`server/shim.py`(`_build_shim_manifest` /
        `_SHIM_MANIFEST` — 内容版本与文件清单)、`shims/*`、`QUICKSTART.md` / `USAGE.md`。
```

## 理由
`server/app.py` 已按 spec 域拆分(本变更)。事实来源指向新的物理位置。

行为零变更:看板域名安装、`install.sh` 全量下载 + sha256 校验、装完即注册、目录穿越拒绝、
manifest 内容版本、hooks 安装幂等可回退、`tf_selfupdate.py` 触发点与安全边界、
OpenClaw 装备态生效路径 等所有 MUST 规则与原 spec 完全一致,只是实现位置从单文件搬到了对应模块。
