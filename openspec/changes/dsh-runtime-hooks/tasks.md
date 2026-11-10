# tasks:dsh-runtime-hooks

- [ ] 0. 真机核对(在运行的 DSH 会话里用 `cordis_inspect_query` 的 `Event` / `Tool`):
      确认 `session/created`、`session/disposed`、`session/event`(`turn/start`/`turn/end`)、`tools/pre-execute`、
      `tools/result`、`agent/error`、`agent/turn-stopping` 的实际名称、分发模式与 payload 字段;
      确认 skill 调用对应的 tool 名;确认新装 bundle 是否 HMR 生效。有出入则调整 design §2 与映射表。
- [ ] 1. `shims/dsh/` 薄壳 bundle:`package.json`(`dsh.bundle.patch`、exports `./locale/*.json`/`./icon`、`files`)、
      `cordis.patch.yml`、`index.js`(`apply(ctx)`;waterfall 监听先 `next()`;detached spawn,unref,吞异常)、
      `locale/en.json` + `locale/zh.json`(meta.title/description)、`icon.svg`(原创)。壳内常量 `PROTOCOL = 1`。
- [ ] 2. `shims/tf_dsh_event.py`:读 stdin 壳 JSON → 事件映射 → 复用 `tf_hook.py` 分发(`resolve`/`SKILL_TOOLS`);
      解析 `tf_env.dsh.sh` 注入环境;未知 protocol/事件静默;`SELFUPDATE_EVENTS` 上 detached 拉起 `tf_selfupdate.py`;
      绝不抛错、始终 `exit 0`。
- [ ] 3. `shims/tf_dsh_plugin.py`:`install` / `ensure` 子命令;DSH 检测、`dsh` 定位、profile 枚举、
      幂等 `plugin add link:`、壳版本比对、`TF_DSH_PLUGIN=0` 开关、全程静默。
- [ ] 4. `shims/tf_selfupdate.py`:新增 `_ensure_dsh_plugin()`,`main()` 中节流前调用,沿用现有守护函数的 try/except 风格。
- [ ] 5. `install.sh`:`--runtime dsh` 生成 `tf_env.dsh.sh`;检测到 DSH 家目录默认安装;`shims/dsh/` 经 manifest 全量拉取
      (确认 `_EXECUTABLE_SHIMS`、`name.startswith` 过滤不误伤 `dsh/` 目录与 `tf_env*` 规则)。
- [ ] 6. `shims/tf_profile.py` / `tf_hooks.py` / 前端 runtime 展示:认识 `dsh`(先 grep 白名单与枚举再改)。
- [ ] 7. 测试(`tests/`):
      - `tf_dsh_event`:各事件映射、session id 提取、Skill 正/负例、`TF_REPORT_SKILLS=0`、未知 protocol 静默;
      - `tf_dsh_plugin`:无 `.dsh` 不动作、有 profile 才调 CLI(monkeypatch subprocess)、已装跳过、失败静默、`TF_DSH_PLUGIN=0`;
      - manifest:新增 `dsh/*` 进清单、目标路径不越界;
      - selfupdate:`_ensure_dsh_plugin` 不受节流限制、异常不外抛。
- [ ] 8. 文档:`PROTOCOL.md`(runtime 枚举 + DSH 说明)、`QUICKSTART.md`、`USAGE.md`、`UPDATE.md`、`SKILL.md`、
      `docs/architecture/module-map.md`、`AGENTS.md` shims 清单、新增 `docs/adr/00NN-dsh-plugin-shell.md` 并登记 README;
      并入 `openspec/specs/onboarding/spec.md`。
- [ ] 9. 校验:`python -m py_compile server/*.py server/routes/*.py shims/*.py`、`bash -n install.sh`、
      `node --check shims/dsh/index.js`、`python -m pytest -q`、覆盖率 ≥ 95%、`wc -l server/app.py` ≤ 220。
- [ ] 10. 端到端手验:真机 DSH 跑一轮会话 → 看板出现 `runtime=dsh` 卡片、活跃时长递增、Skill 使用入榜;
       改一处 `tf_dsh_event.py` 发布到服务端 → 本机自动更新后行为变化,无需重启 DSH。
- [ ] 11. 部署与归档:发布新 shims 到服务端;确认老客户端自更新可拉到 `dsh/*`;归档本变更。
