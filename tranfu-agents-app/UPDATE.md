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
cd deploy
docker compose up -d --build
```

**systemd(裸 Python):**
```bash
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
- [ ] 测试事件能在看板上看到
- [ ] 页面顶部不再显示「未连接服务端」
- [ ] logo 是新的(红色图形内联)、有 Pods 看板 / Agents 列表 两个标签

---

完整部署/运维(备份、轮换密钥、访问控制等)见仓库 `DEPLOY.md`。
团队成员怎么接入自己的 agent 见 `QUICKSTART.md`。
