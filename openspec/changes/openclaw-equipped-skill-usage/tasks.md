# tasks:openclaw-equipped-skill-usage

- [ ] 0. 真机前置(实现前):在装了 OpenClaw 的机器上跑一个会触发 skill 注入的任务,抓一段 system prompt,
      确认 (1) 注入 `<skill>` 块的确切格式/标签,(2) `llm_input` 交出 system prompt 的字段/形态,
      (3) 插件能否全局 `fetch` 出站、`fs` 写日志、身份从 `api.pluginConfig` 还是环境读,(4) 插件注册进配置的落盘位置。
      有出入则相应调整 `skill-extract` 正则与插件装载。

## 语义贯通(服务端 / 协议 / 前端)—— 先于放量

- [x] 1. `server/app.py`:`skill_uses` 加 `mode TEXT NOT NULL DEFAULT 'used'`,主键扩为 `(session_id, skill, mode)`;
      既有库 `ALTER TABLE ADD COLUMN` 迁移(旧行 `used`)。ingest 读事件 `skill_mode`(白名单 `{used,equipped}`,
      非法/缺省→`used`)写入。`skill_usage()` 改 `GROUP BY skill, mode` 并返回 `mode`;**used 排行数值与现状一致**。
- [x] 2. `PROTOCOL.md`:§4 事件加可选 `skill_mode`;§5 注明 OpenClaw 下 skill 名取自注入块(只报名);§6 落库规则加 mode 维度。
      `openspec/specs/ingest/spec.md`:套用本变更 `specs/ingest/spec.md` delta。
- [x] 3. `dashboard/index.html`:排行项渲染 `equipped` 标识;同名 used/equipped 两条不合并;`node --check` 校验抽出的 `<script>`。
- [x] 4. 服务端测(`tests/test_skill_usage.py` 加用例):`equipped` 落 `mode='equipped'`;同 session 重发幂等;
      同 session 的 used+equipped 两行共存;非法/缺省 `skill_mode`→`used`;`/api/state.skills` 分条不相加;
      回归:旧客户端(不带 `skill_mode`)仍落 `used`、排行不变。

## OpenClaw 采集插件(新增 `shims/openclaw/`)

- [x] 5. `shims/openclaw/skill-extract`(纯函数):输入 system prompt 文本 → `{names, blockSeen}`;宽容解析,异常返回空 + `blockSeen=false`。
- [x] 6. `shims/openclaw/openclaw.plugin.json` + 插件入口:`register(api)` 注册 `llm_input`(解析+会话级去重)与
      `session_end`(逐个 fire-and-forget 后台 POST,带 `skill_mode=equipped`,hook 不等待网络);
      身份/server/key 取自 `api.pluginConfig`;全程 try/catch 吞异常,绝不抛进宿主。
- [x] 7. 调试日志(常开,`~/.tranfu/logs/openclaw-skill.log`):覆盖 6 个断点;漂移即时落 WARN(无原文);
      会话攒计数→`session_end` 落一行汇总;文件超阈值截断/轮转;每行不含 prompt/描述原文。
- [x] 8. 插件单测(JS):提取正/负/漂移/去重;日志 6 断点入汇总、漂移即时 WARN 且无原文、超阈值截断。

## 安装 / 文档 / 纠错

- [x] 9. `install.sh`:分发 `shims/openclaw/`,注册进 OpenClaw 配置 `plugins.entries.<id>`;依赖尽量零。
- [x] 10. `docs/adr/0018-openclaw-equipped-skill-usage.md` 成文并登记 `docs/adr/README.md`;
      `docs/architecture/module-map.md` 加 `shims/openclaw` 边界(JS 插件,只读 prompt 提取 skill 名,只出站到 collector,不依赖 Python shim)。
- [x] 11. 纠错:改正 `docs/adr/0016-*` / `shims/tf_rollout_scan.py` / `shims/tf_profile.py` 里
      「OpenClaw 跑 Codex runtime、rollout 可扫」的旧注释(保留 profile 安装态探测,那部分是对的)。

## 验证 / 部署

- [ ] 12. 端到端手验:真机 OpenClaw 跑触发 skill 注入的任务 → 远端排行出现该 skill 的 **equipped 条目**、不混进 used;
      本地日志汇总行可见 llm_input 次数/提取名/POST 结果。
- [ ] 13. 部署顺序:**先**服务端完成 `skill_uses.mode` 迁移,**后**把 `shims/openclaw/` 发布到服务端 `shims/`、队友重跑 `install.sh`
      注册插件(顺序颠倒会把装备态错记成 used)。
