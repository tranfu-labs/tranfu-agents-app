# 设计:fix-shim-version-reporting

## 方案

三层都修(用户敲定的 C 方案)。

### 客户端

- `shims/tf_profile.py`
  - 新增 `quick_shim_version()`:进程内缓存读 `~/.tranfu/manifest.json` 顶层 `version`,返回 None 当文件缺失。
    `detect_shim_version()` 改为复用 `quick_shim_version()`,行为不变。
- `shims/tf_report.py`
  - `argparse` 新增 `--shim-version`(为外部调用者保留);
  - **自动兜底**:每次构造 payload 时,若顶层无 `shim_version` 且没传 `--profile`,
    主动调用 `tf_profile.quick_shim_version()` 取一次塞进顶层;
  - 这一步把"每个事件都带 shim_version"的能力下沉到上报器,`tf_hook.py` 不必感知。
- `shims/tf_hook.py`
  - **不需要改**:所有 hook 事件都通过 `tf_report.py` 上报,自动获得 shim_version 注入。
  - 现有 `SessionStart` 的 `--profile` 路径保留,因为它还要刷 cf/mcp/skills/integrations 等其它字段。
- `shims/openclaw/reporter.mjs`
  - 启动时同步读一次 `~/.tranfu/manifest.json`,缓存 `shimVersion`(失败 → 仍上报但不带该字段);
  - 监听 `SIGUSR1` 重读 manifest(对应自更新器替换文件后再次发版的场景,无需重启 OpenClaw 也能拿到新版);
  - 每次 `postJson()` 把 `shimVersion` 注入 payload 顶层。

### 服务端

- `server/app.py` 表结构
  - 新增独立小表 `agent_shim_versions(operator TEXT, ak TEXT, runtime TEXT, shim_version TEXT, updated TEXT, PRIMARY KEY(operator,ak,runtime))`,
    与 `profiles` 同身份维度但职责单一。
  - 这是"agent 粒度独立 sticky 列"的物理实现 —— 不混进现有 `profiles.json`,避免与 profile 全量替换语义冲突。
- 事件入库
  - `/v1/events` 处理路径中,若 `e` 顶层带 `shim_version` 非空 → `UPSERT agent_shim_versions`(`ON CONFLICT DO UPDATE SET shim_version=excluded.shim_version, updated=excluded.updated`)。
  - 不带 → 不动该表(自然 sticky)。
- profile 拆字段
  - `PROFILE_KEYS` 移除 `shim_version`,profile 全量替换不再触碰它。
- `/api/state` 聚合
  - 读 `agent_shim_versions` 全表为 `shim_map[(operator,ak,runtime)] = shim_version`,
    在 `card(r)` 里:`d["shim_version"] = shim_map.get(key)`(可能为 None)。
- 兼容旧客户端
  - 旧客户端依旧只在 SessionStart 时通过 profile 上 `shim_version` —— 加 hook:
    若 payload 没有顶层 `shim_version` 但 profile 里有,启动时**兜底**写入 `agent_shim_versions`。
    这样旧 shim 客户端注册时仍能让看板拿到一次值,前端显示"已知 / 已记录",不至于全部变灰。

### 前端

- `frontend/src/lib/utils.ts`
  - 新增 `shimState(agent, latest): 'current' | 'outdated' | 'unknown'`;
    保留 `isOldShim` 为兼容包装(`shimState() === 'outdated'`),后续可清理。
- `frontend/src/components/Common.tsx` / `frontend/src/views/AgentDetail.tsx`
  - 卡片 / 详情按三态切 className(`current` 默认 / `old` 橙 / `unknown` 灰)与文案。
- `frontend/src/lib/i18n.ts`
  - 加 `shimUnknown: '等待客户端心跳' / 'awaiting client'`。
- `frontend/src/lib/demo.ts`
  - 加一个 `shim_version: undefined` 的演示 agent,允许在 demo 模式看到三态。

## 权衡

- **拆独立小表 vs 给 profiles 加列**:选独立小表。
  - 独立小表:职责单一,SQL 简单,profile 全量替换语义不被污染,回滚干净(DROP TABLE)。
  - 给 profiles 加列:看起来更紧凑,但要在 INSERT OR REPLACE 上加"保留旧 shim_version"特例,复杂、易错。
- **每次心跳都带 vs 只在心跳节流后带**:选每次都带。
  - 进程内缓存后读一次 manifest.json 成本 ~微秒级,远小于 hook 调用一次 python 解释器的成本。
  - 简化协议:不需要"频率"语义。
- **顶层字段 vs 嵌套字段**:选顶层。
  - 顶层字段进表更直接;profile 字段会跟 profile 全量替换语义混淆。
- **OpenClaw 缓存 + SIGUSR1 vs 每次 POST 重读**:选缓存 + SIGUSR1。
  - OpenClaw 常驻进程,频繁 fs.readFile 多余;重启 OpenClaw 才加载新版插件本来就是约定。
  - SIGUSR1 留个轻量重读后门(自更新器可在替换文件后发信号,但不强求)。
- **shimState 不写单测**:已说明项目无前端测试基础设施;函数 3 行纯函数,走 demo.ts 三态视觉验证 + AI 验证流程。
- **不动旧 SessionStart 路径**:`MAP` 表仍保留 `attach_profile=True`,因为 profile 还有 cf/mcp/skills 等字段也得在 SessionStart 刷;只是 `shim_version` 不再依赖它。

## 风险

- **部署顺序敏感**:服务端必须先升(读 `agent_shim_versions` 时表才存在)。客户端先升、服务端没升 → 服务端会忽略顶层 `shim_version`,但 profile 路径仍生效,行为不变。tasks.md 显式标注顺序。
- **OpenClaw SIGUSR1 不可用平台(Windows)**:`process.on('SIGUSR1', ...)` 在 Windows 上 no-op;不影响其他平台,且非必需路径,可接受。
- **agent_shim_versions 表持续增长**:理论上每个 `(operator,ak,runtime)` 一行,与 `profiles` 同级别,
  规模不会失控。`admin-data-cleanup` 的现有清理路径需要顺手把该表一并清(写进 tasks)。
- **回滚**:三层独立;若服务端回滚 → 客户端继续多带 `shim_version` 顶层字段会被忽略,不影响事件入库;
  前端回滚 → 三态退回二态,但服务端 sticky 保留,看板字段仍正确。
