# 部署委托 · PR #7

> 一句话：把 PR #7 合并并更新线上 server，让「hook 上报修复 / skill 画像修复 / 看板清理端点」三项生效，然后清掉接入调试时灌进看板的测试事件。

| 项 | 内容 |
|---|---|
| 委托人 | NEZHA（调度员） |
| 受托人 | __待填（管理员 / 运维 / 受托 agent）__ |
| 委托日期 | 2026-06-03 |
| 关联 PR | https://github.com/tranfu-labs/tranfu-agents-app/pull/7 |
| 分支 | `claude/suspicious-varahamihira-6f301b` → `main` |
| 预计耗时 | 10–15 分钟 |
| 风险级别 | 中（含一次性破坏性删除操作，见 §4） |

---

## 0. 待确认（开工前先回答，否则别动手）

这两条我（赛博哪吒）不掌握，**不能替你假设**：

- [ ] **生产用哪种部署形态？** Docker Compose / systemd（纯 Python）/ 其他。→ 决定 §2 用哪套命令。
- [ ] **server 跑在哪台机器、怎么登上去？** 域名 `tranfu-agents-app.tranfu.com` 背后的主机。
- [ ] **`TF_KEY` 从哪取？** 不要写进任何文件/聊天。用机器上 `.env` 或 systemd Environment 里现有的那串；下文一律用占位 `<TF_KEY>`。

> 服务端地址（下文 `$SERVER`）：`https://tranfu-agents-app.tranfu.com`

---

## 1. 背景：为什么这次部署是必要的

接入 Claude Code 时实测发现接入「装好就坏」，PR #7 修了三个真问题，但**全部需要更新线上 server 才生效**：

1. **hook 静默不上报** — 配置写进 `~/.zshrc`，但 hook 由非交互 shell 执行读不到；`install.sh` 与 shim 已改为写 `~/.tranfu/tf_env.sh` 并由 hook 显式 source。线上 server 同时**对外分发 `install.sh` 和 `shims/*`**，所以必须更新，团队后续新装才拿到修复版。
2. **skill 画像串号** — `detect_skills` 改为按 runtime 扫对应目录 + 跳过软链。
3. **看板无法清理脏数据** — 新增 `DELETE /v1/events`（admin），这正是 §4 清理测试垃圾要用的端点，**部署后才存在**。

---

## 2. 部署动作（按 §0 的形态二选一；命令出自 `DEPLOY.md` E 节）

### 前置：合并 PR #7
- 在 GitHub 上 review 并 merge PR #7 到 `main`（CI 应已绿：契约测试 17/17）。

### 形态 A — Docker Compose
```bash
cd tranfu-agents-app && git pull
docker compose up -d --build
docker compose logs -f server      # 看启动无报错
```

### 形态 B — systemd（纯 Python）
```bash
cd tranfu-agents-app && git pull
source .venv/bin/activate && pip install -r server/requirements.txt
sudo systemctl restart tranfu
systemctl status tranfu            # running
```

---

## 3. 验证全链路（每条都要过）

```bash
SERVER=https://tranfu-agents-app.tranfu.com

# 3.1 活着
curl -s $SERVER/healthz                      # 期望: ok

# 3.2 【关键】确认新代码已生效：DELETE 端点存在
#     新代码空体删除返回 400（缺目标）；旧代码会返回 405（方法不允许）
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE $SERVER/v1/events \
  -H "X-TF-Key: <TF_KEY>" -H 'content-type: application/json' -d '{}'
#     期望: 400  ；若 405 → 还是旧代码，部署没生效，回 §2 排查

# 3.3 分发的 install.sh 已是修复版（应能搜到 tf_env.sh）
curl -s $SERVER/install.sh | grep -c 'tf_env.sh'   # 期望: ≥1

# 3.4 写入链路通（发一条测试事件，随后在 3.5 一起删掉）
curl -s -XPOST $SERVER/v1/events \
  -H "content-type: application/json" -H "X-TF-Key: <TF_KEY>" \
  -d '{"operator":"deploy-check","runtime":"claude-code","session_id":"pr7-smoke","status":"running","task":"PR7部署验证","current_step":"ok"}'
#     期望: {"ok":true,...}
```

---

## 4. 部署后清理：删掉接入调试灌进看板的测试事件 ⚠️

> 这是**破坏性**操作，用 admin 端点 `DELETE /v1/events`（`X-TF-Key` 守门）。
> 只删下列**确定的测试 session**，不要按身份删（会误伤赛博哪吒真卡片）。

```bash
SERVER=https://tranfu-agents-app.tranfu.com
curl -s -X DELETE $SERVER/v1/events \
  -H "X-TF-Key: <TF_KEY>" -H 'content-type: application/json' \
  -d '{"session_ids":[
        "clean-zsh-1","clean-sh-sourced-1","diag-zshenv-1",
        "final-sh","final-zsh","final-bash","pr7-smoke"
      ]}'
#     返回 {"ok":true,"deleted":N,...}
```

说明：
- `pr7-smoke` 是 §3.4 自己发的验证事件，一并清掉。
- `操作 deploy-check` 的 smoke 卡片（§3.4）也可顺手删：`-d '{"operator":"deploy-check"}'`。
- `接入验证` / `修正skill画像` 用的是 `cli-<pid>` 自动 session，归并在赛博哪吒真卡片下、会被下次真实会话顶掉，**不必单独删**（按身份删会误伤）。

---

## 5. 回滚

- **server 代码**：`git revert` PR #7 的 merge commit（或 checkout 上一个 tag），重跑 §2 更新命令。SQLite 数据不受影响。
- **已删除的事件**：`DELETE` 不可逆。若误删，只能等其重新上报或从 §6 的 `tf.db` 备份恢复。**执行 §4 前先备份**（见下）。

```bash
# Docker
docker compose cp server:/data/tf.db ./tf-backup-$(date +%F).db
# systemd
sudo cp /var/lib/tranfu/tf.db /var/lib/tranfu/tf-backup-$(date +%F).db
```

---

## 6. 验收标准（DoD）

- [ ] PR #7 已 merge 到 `main`，CI 绿。
- [ ] §3.1 `/healthz` 返回 ok。
- [ ] §3.2 DELETE 空体返回 **400**（证明新代码生效）。
- [ ] §3.3 `install.sh` 含 `tf_env.sh`。
- [ ] §4 测试垃圾已清，看板上赛博哪吒卡片只剩真实记录、skill 列表为自有技能（无 `lark-*`）。
- [ ] §5 备份已生成。

---

## 7. 给受托人的提醒

- `<TF_KEY>` 全程不要落盘到聊天/工单/这份文件，用机器上现成的环境变量。
- 若线上开了 Cloudflare Access / Caddy 读侧鉴权，确认 `/v1/events` 在放行名单里（见 `DEPLOY.md` D 节），否则 §3/§4 的请求会被边缘挡住返回 HTML 而非 JSON。
- 接入这台机器的人（NEZHA）还需**重启本地 Claude Code**，hook 才会以修复后的方式上报——这一步在成员机器上做，不在 server 上。
