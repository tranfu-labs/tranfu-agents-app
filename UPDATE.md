# UPDATE — 把现有看板更新到最新版(给开发)

> 适用场景:`tranfu-agents-app.tranfu.com` 已经在一台服务器上跑着、并经 Cloudflare Tunnel 暴露;
> 现在要更新到最新代码(新 logo / 三视图 UI / 自动探测 shim),并修复线上当前显示的
> 「**演示数据 · 未连接服务端**」问题。
>
> 最新代码在:`https://github.com/tranfu-labs/tranfu-agents-app`(main 分支)。
> **不需要谁发文件,`git pull` 即可。** 全程大概 5 分钟。

---

## 1. 拉最新代码

进服务器上的仓库目录(就是当初部署时 clone 的那个),然后:
```bash
git pull
```
> 如果当初不是用 git clone 部署的,先 `git clone https://github.com/tranfu-labs/tranfu-agents-app.git`
> 到一个目录,后续命令在该目录里执行。

## 2. 重启服务(二选一,看当初怎么起的)

**Docker:**
```bash
docker compose up -d --build
```

**systemd(裸 Python):**
```bash
npm ci --prefix frontend
npm --prefix frontend run build
sudo systemctl restart tranfu
```

## 3. 确认后端真的通了(关键 —— 线上现在卡的就是这步)

页面显示「未连接服务端」= 浏览器没拿到后端的 `/api/state`。逐条确认:

```bash
# a) 健康检查,必须返回 ok
curl http://localhost:8788/healthz

# b) 页面接口,必须返回 JSON(包含 sessions/feed/totals 等字段)
curl http://localhost:8788/api/state | head -c 200

# c) 发一条测试事件(把 <TF_KEY> 换成线上用的那个密钥)
curl -s -XPOST http://localhost:8788/v1/events \
  -H "content-type: application/json" -H "X-TF-Key: <TF_KEY>" \
  -d '{"operator":"test","runtime":"claude-code","session_id":"smoke1","status":"running","task":"联通测试","current_step":"hello"}'
```
第三条应返回 `{"ok":true,...}`。然后刷新 `https://tranfu-agents-app.tranfu.com/`,
应能看到 **test** 这个 Pod,且页面顶部**不再显示「未连接服务端」**。

## 4. 如果刷新后仍显示「未连接服务端」

多半是 **Tunnel 只把网页代理过来了,但 `/api/*`、`/v1/*` 没走到后端**,或后端没在 `localhost:8788`。检查 Tunnel 配置 `~/.cloudflared/config.yml`,确保是**整个站点**指向后端,而不是只挂了一个静态文件:

```yaml
ingress:
  - hostname: tranfu-agents-app.tranfu.com
    service: http://localhost:8788      # 指向后端服务,不是某个静态 HTML
  - service: http_status:404
```
改完重启 Tunnel:
```bash
sudo systemctl restart cloudflared      # 或 cloudflared tunnel run <隧道名>
```
再从公网验证(在任意机器上):
```bash
curl https://tranfu-agents-app.tranfu.com/healthz          # ok
curl https://tranfu-agents-app.tranfu.com/api/state | head -c 200   # JSON
```
两条都正常,页面就会从"演示数据"切到实时数据。

## 5. 完成确认

- [ ] `curl .../healthz` 返回 ok
- [ ] `curl .../api/state` 返回 JSON
- [ ] `curl .../api/skills?days=30` 返回 JSON
- [ ] 测试事件能在看板上看到
- [ ] 页面顶部不再显示「未连接服务端」
- [ ] logo 是新的(红色图形内联)、有 Pods 看板 / Agents 列表 / SKILLS 三个标签

## 6. 本地 shim 自动更新升级注意

本版本新增 `/shims/manifest` 与 `tf_selfupdate.py`。服务端更新后,看板会显示每个 agent 上报的
shim 短版本,按三态判定:
- **current** —— 上报版本等于服务端 `/shims/manifest.version`,常态显示。
- **outdated** —— 上报了一个落后的版本,显示"旧 shim"橙色角标。
- **unknown** —— 从未上报过 `shim_version`,显示"等待客户端心跳"灰色虚线;
  常见于 2026-06 前的旧 shim(那时只在 SessionStart 通过 profile 偶尔上报),
  或是刚接入还没心跳过的新 agent。**unknown 不是"旧 shim"**——只要客户端一次心跳带上 `shim_version` 就会转 current。

现有机器还没有自更新器,需要**最后一次**通知队友重跑当前看板域名的 `install.sh`;重跑后安装器会按
manifest 全量下载并校验 shim,成功后保存 `~/.tranfu/manifest.json`,之后 Claude Code / Codex / Hermes
会在会话开始时后台自动更新 shim。新 shim 起,**每条心跳事件**都会自动顶层带上 `shim_version`
(由 `tf_report.py` 兜底注入,不再依赖 SessionStart 的 `--profile` 路径);服务端按 agent 身份
sticky 保存,后续不带这字段的心跳不会清掉它。

生效时机:
- Claude Code / Codex / Hermes:文件替换后下一次 hook 触发即生效;**当前正跑着的会话仍会显示
  unknown(进程内是旧 shim 代码)**——重启该 agent 才有新心跳带上 `shim_version`。
- OpenClaw:文件会刷新到 `~/.tranfu/openclaw/`,但需要重启 OpenClaw 才加载新版插件 JS;
  或者向 OpenClaw 进程发 `SIGUSR1` 让它热重读 `manifest.json`(只刷版本号,逻辑代码仍需重启)。

排查:
1. 看板卡片显示"旧 shim"(outdated)→ 先让该机器重跑新版 `install.sh`,再重启对应 agent。
   显示"等待客户端心跳"(unknown)→ 说明该 agent 从未上报过 `shim_version`,
   通常是旧 shim 还在跑、或新 agent 还没触发过一次 hook。让它做一次会话动作即可。
2. 本机要关闭自动更新 → 在 `~/.tranfu/tf_env.<runtime>.sh` 写 `export TF_AUTO_UPDATE=0`。
3. 自动更新失败不会破坏旧文件;检查是否没有写入 `~/.tranfu` 权限、或网络无法访问 `$SERVER/shims/manifest`。
4. 本地 `manifest.json` 版本一致但缺文件时,新版自更新器会自动补齐;补不齐通常是权限或下载失败。

## 7. SKILLS 统计页升级注意

本版本新增 SKILLS 顶级页与 Skill 使用统计。服务端更新后兼容旧 shim,但**只有队友重跑 install.sh 拉到新版本地 shim 后**,
Skill 调用才会开始上报 `skill` 字段,所以 SKILLS 页数据会按人逐步出现。Claude Code 走 `Skill` 工具调用;
Hermes 走 `skill_view` 工具调用;Codex 不暴露该工具调用,改由 shim 在轮次/会话结束时解析本机
rollout 文件提取(见 ADR-0016/0017)。OpenClaw 没有使用边界,新版本通过原生插件从 prompt 注入块提取
并以 `mode=equipped` 记录装备态(见 ADR-0018),不与 `used` 使用态相加;SKILLS 总览只统计 `used`,
装备态只在单个 skill 详情里展示。OpenClaw 插件在 `session_end`
只排队后台 POST,不会等待网络而阻塞 agent。这几条路都需要新版本地 shim/plugin
(`tf_rollout_scan.py` 是 Codex 采集依赖文件,`~/.tranfu/openclaw/` 是 OpenClaw 插件目录,务必确认 install.sh 已拉到)。

SKILLS 页会低频读取三个只读接口:
- `GET /api/skills?days={7|30|90}`:总览(日趋势、used-only skill 主表、used-only 操作员主表、公司库采纳漏斗),响应带服务端 UTC `today`;`days=0` 不再支持。
- `GET /api/skill/{name}`:单 skill 详情(最近 30 天 used/equipped 分列趋势、runtime/operator 分布、最近记录),响应带服务端 UTC `today`。
- `GET /api/operator/{name}`:单操作员详情(used-only 指标、按 skill 分段趋势、skill 排行、runtime 分布、最近记录),响应带服务端 UTC `today`;人维度口径是会话×skill 去重,不是实际调用次数。

前端会以服务端 `today` 为右端铺满所选 UTC 日窗口;空白天留空槽,今日柱用"进行中"样式,悬停/点击显示当天明细与合计。

公司库漏斗依赖 tranfu-skills catalog。默认地址是
`https://github.com/tranfu-labs/tranfu-skills/releases/download/catalog/index.json`;如部署环境无法访问,可在服务端设置
`TF_SKILLS_CATALOG_URL` 指向内网镜像。拉取失败时接口仍 200,使用旧缓存并在页面标记目录缓存过期;从未成功拉取时只显示漏斗不可达,其它使用统计不受影响。

升级顺序要先更新服务端并完成 `skill_uses.mode` 迁移,再让队友重跑 `install.sh` 注册 OpenClaw 插件;顺序反过来时,
旧服务端会把 OpenClaw 装备态按旧口径记成 `used`。

查不到 Skill 数据时按这个顺序排查:
1. 队友是否重跑了当前看板域名的 `install.sh`,并重启了 Claude Code / Codex / Hermes gateway / OpenClaw。
2. 本机 `~/.tranfu/` 是否有 `tf_rollout_scan.py`(Codex 采集依赖它),以及 `~/.tranfu/openclaw/`(OpenClaw 插件);
   没有=install.sh 是旧版,服务端 shims 未更新。
3. 本机是否设置了 `TF_REPORT_SKILLS=0`。
4. 是否真的**用了/装备了**某 skill:Claude Code 要触发 `Skill` 工具调用;Hermes 要触发 `skill_view(name)`;
   Codex 要真读 `.codex|.claude/skills/<名>/SKILL.md`(只在对话里提名字、不读文件不计入);
   OpenClaw 要让该 skill 进入本会话 prompt 注入块(单 skill 详情里显示 `equipped`)。
5. (Hermes)确认 `~/.hermes/config.yaml` 的 `pre_tool_call` 已指向 `~/.tranfu/tf-hermes-hook.sh`,
   且启动 Hermes 的环境能读到 `TF_SERVER/TF_KEY/TF_OPERATOR/TF_RUNTIME`。
6. (Codex)直接验解析:`python3 ~/.tranfu/tf_rollout_scan.py --session <会话id> --print`,看是否列出 skill 名。
7. (OpenClaw)看本地日志:`tail -n 50 ~/.tranfu/logs/openclaw-skill.log`,确认有 `session_end` 汇总、`skillCount`、
   `postOk/postFail`;若有 `format_drift` WARN,说明注入块格式需要重新锚定。
8. 服务端 SQLite 是否已有记录:`sqlite3 tf.db 'select session_id,skill,mode,operator,day from skill_uses limit 5;'`。
9. SKILLS 总览接口是否可读:`curl https://你的看板/api/skills?days=30 | head -c 300`。

---

完整部署/运维(备份、轮换密钥、访问控制等)见仓库 `DEPLOY.md`。
团队成员怎么接入自己的 agent 见 `QUICKSTART.md`。
