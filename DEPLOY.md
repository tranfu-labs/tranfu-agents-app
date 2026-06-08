# 部署文档(傻瓜式 · 一步步照抄)

> 这份给**管理员**:把看板服务跑起来、给团队一个网址。
> 团队成员怎么接入自己的 agent → 见 `QUICKSTART.md`(5 分钟)。

你要部署的东西**只有一个常开进程**:一个小服务(`server`),它同时干两件事——
**① 接收各 agent 上报的事件;② 直接把看板网页发给浏览器**。看板是静态页,由这个服务一起提供,**不用单独部署**。数据存在本地一个 SQLite 文件里,**不依赖任何外部数据库/中间件**。512MB 内存的小机器就够。

整个部署分三步:**A. 把服务跑起来 → B. 给它一个带 HTTPS 的网址 → C. 验证 + 发给团队**。

---

## 第 0 步:先生成一个接入密钥(TF_KEY)

所有 agent 上报时要带这个密钥,**不设的话任何人都能往你的板子塞数据**。生成一串随机的:

```bash
openssl rand -hex 24
```

把输出那串(例如 `9f3c…`)记下来,后面到处用,记作 **`<TF_KEY>`**。

---

## A. 把服务跑起来

### 方式 A1 — Coolify(推荐,最省心)

根目录 `compose.yml` 面向 Coolify / Traefik:Web 服务只写 `expose: 8788`,不发布宿主机公网端口。

**1) 在 Coolify 创建 Docker Compose 应用**
- 选择仓库 `tranfu-labs/tranfu-agents-app`。
- Compose 文件使用根目录 `compose.yml`。

**2) 填环境变量**
- 设置 `TF_KEY=<TF_KEY>`。
- 如需可信归因或内容捕获,再按 D 节设置 `TF_REQUIRE_TOKEN` / `TF_READ_AUTH` / `TF_READ_KEY`。

**3) 配 Domain**
- 给 `server` service 配 Domain:`https://agents.example.com:8788`。
- 这里的 `:8788` 是容器内部端口,不是公网端口;公网仍走 HTTPS 443。

**4) 部署并确认活着**
```bash
curl https://agents.example.com/healthz      # 返回 ok 就对了
```
浏览器打开 `https://agents.example.com` 应能看到看板(还没有数据是正常的)。

- 数据存在 Docker 卷 `tf-data` 里,容器重启不丢。
- 看日志:在 Coolify 的 service logs 里看 `server`。
- 停止/重启/更新:在 Coolify 应用里操作;更新见文末"运维"。

### 方式 A2 — 不用 Docker(纯 Python)

适合直接在一台 Linux VPS 上跑。

```bash
git clone https://github.com/tranfu-labs/tranfu-agents-app.git
cd tranfu-agents-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
TF_KEY=<TF_KEY> TF_DB=/var/lib/tranfu/tf.db \
  python -m uvicorn server.app:app --host 0.0.0.0 --port 8788
```
要常驻(开机自启、崩溃重拉)就装成 systemd 服务:
```bash
sudo mkdir -p /var/lib/tranfu
sudo tee /etc/systemd/system/tranfu.service >/dev/null <<UNIT
[Unit]
Description=TRANFU//AGENTS
After=network.target
[Service]
Environment=TF_KEY=<TF_KEY>
Environment=TF_DB=/var/lib/tranfu/tf.db
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port 8788
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now tranfu
systemctl status tranfu       # 看是否 running
```

---

## B. 给它一个带 HTTPS 的网址

`localhost:8788` 只有本机能看。要让团队访问、且 agent 能 HTTPS 上报,三选一(从易到难):

### 方式 B1 — Cloudflare Tunnel(最推荐:不用开端口、不用公网 IP、自动 HTTPS)

> 前提:你有一个托管在 Cloudflare 的域名(比如 `tranfu.com`)。

```bash
# 1) 装 cloudflared
brew install cloudflared            # Mac;Linux 见 Cloudflare 文档

# 2) 登录(浏览器里选择你的域名授权)
cloudflared tunnel login

# 3) 建隧道
cloudflared tunnel create tranfu-agents-app
#    记下输出里的 Tunnel ID 和凭证文件路径(~/.cloudflared/<ID>.json)

# 4) 把一个子域名指向这条隧道
cloudflared tunnel route dns tranfu-agents-app agents.tranfu.com
```

**5) 写配置** `~/.cloudflared/config.yml`:
```yaml
tunnel: tranfu-agents-app
credentials-file: /Users/你的用户名/.cloudflared/<Tunnel-ID>.json
ingress:
  - hostname: agents.tranfu.com
    service: http://localhost:8788
  - service: http_status:404
```

**6) 跑起来(并装成常驻服务)**
```bash
cloudflared tunnel run tranfu-agents-app        # 前台测试,Ctrl-C 退出
# 确认没问题后装成开机自启:
sudo cloudflared service install
```

现在看板在 **https://agents.tranfu.com**,你的服务端地址(发给团队的 `--server`)就是它。

### 方式 B2 — Caddy 反向代理(有公网 VPS + 域名,要自动 HTTPS)

把域名 A 记录指到这台 VPS 的公网 IP,然后:
```bash
# 安装 caddy 后,一条命令即可(自动申请并续期 HTTPS 证书)
caddy reverse-proxy --from agents.tranfu.com --to localhost:8788
```
(要常驻就写 Caddyfile + `systemctl enable --now caddy`。)

### 方式 B3 — 只在内网/LAN 用(最简单,临时)

同一局域网的人直接访问 `http://<这台机器的内网IP>:8788` 即可,无需 HTTPS。
仅适合内网试用;给 agent 上报也用这个地址。

---

## C. 验证全链路 + 发给团队

**1) 服务在不在:**
```bash
curl https://agents.tranfu.com/healthz       # ok
```

**2) 发一条测试事件,看板能不能收到:**
```bash
curl -s -XPOST https://agents.tranfu.com/v1/events \
  -H "content-type: application/json" -H "X-TF-Key: <TF_KEY>" \
  -d '{"operator":"test","runtime":"claude-code","session_id":"smoke1","status":"running","task":"联通测试","current_step":"hello board"}'
```
返回 `{"ok":true,...}`,然后刷新看板,应看到 `test` 这个 Pod 在"运行中"。

**3) 把接入方式发给团队**(每人按自己情况改 `--operator/--runtime`):
```bash
curl -fsSL https://raw.githubusercontent.com/tranfu-labs/tranfu-agents-app/main/install.sh | bash -s -- \
  --server https://agents.tranfu.com --key <TF_KEY> --operator 名字 --runtime claude-code
```
更详细的成员接入(三条路径 + 自动探测 + `TF_ROLE`)在 `QUICKSTART.md`。

---

## D. 加访问控制(开放给全员前,务必做)

看板默认**谁有网址谁就能看**。在让它对外、尤其在打开敏感上报(`TF_CAPTURE_CONTENT` / `TF_REPORT_MEMORY`)之前,给"读"加一道门。

### D1. 读侧鉴权(给"看板"加门)
- **Cloudflare Access(配 B1 用,最省事)**:Cloudflare Zero Trust → Access → 给 `agents.tranfu.com` 建一条策略,限定公司邮箱/Google 登录。**注意只保护网页路径,放行 `/v1/events`、`/install.sh`、`/shims/*`、`/healthz`**(否则 agent 上报/安装会被挡):给这些路径单独配 Bypass,或让 agent 走另一个不加 Access 的子域名。
- **Caddy Basic Auth(配 B2 用)**:在 Caddyfile 里对 `/` 与 `/api/*` 加 `basicauth`,对 `/v1/events`、`/install.sh`、`/shims/*`、`/healthz` 放行。
- **VPN/内网**:整台机器只在 VPN 内可达,最省事但成员需连 VPN。

> 写入侧已有 `TF_KEY` 保护;这一步是给**读取(看板)**加保护。

### D2. 内容捕获是硬约束(服务端会强制执行)
一旦打开 `input`/`output`/`instructions`/`memory` 上报,等于把 prompt、代码、系统提示挂到看板。服务端因此**强制要求先声明读侧已受保护**,否则**直接丢弃这些敏感字段不予存储**(状态类字段照常)。配好 D1 后,在服务端环境里二选一声明:

```bash
# 走了边缘鉴权(Cloudflare Access / Caddy)→ 声明已就位:
TF_READ_AUTH=1
# 或:用应用内只读令牌(非空即视为读侧受保护;真正的读侧中间件强制为后续工作):
TF_READ_KEY=<另一串随机密钥>
```

> 这是 ADR-0012 的硬约束:**没配读侧鉴权就拿不到敏感内容**,无侥幸空间。

### D3. 身份归因(可选:让数据可信地对应到真人)
默认只有团队密钥 `TF_KEY` 时,`operator` 是**自证**的——任何拿到密钥的人都能冒名上报,看板标"未验证"。要让归因可信,开启 per-operator 令牌(ADR-0011):

```bash
# 1) 服务端开启强制归因:
TF_REQUIRE_TOKEN=1        # 加进 .env 或 systemd Environment,重启服务

# 2) 用团队密钥为每个成员签发一次性令牌(明文仅返回一次,服务端只存 sha256):
curl -s -XPOST https://agents.tranfu.com/v1/enroll \
  -H "content-type: application/json" -H "X-TF-Key: <TF_KEY>" \
  -d '{"operator":"alice"}'
#   → {"operator":"alice","token":"ttk_...","note":"保存到 TF_TOKEN，仅此一次可见"}

# 3) 把 token 发给该成员,存进其环境变量 TF_TOKEN(shim 上报时自动带 X-TF-Token)。
```

开启后:令牌与 `operator` 不一致 → 403;一致 → 看板标 `verified`。不开则向后兼容(仍允许自证)。

---

## E. 日常运维

**看日志**
```bash
docker compose logs -f server          # Docker
journalctl -u tranfu -f                # systemd
```

**更新到最新版**
```bash
# Coolify:重新部署应用
# systemd:重装依赖后 sudo systemctl restart tranfu
```

**备份数据(SQLite)**
```bash
# Docker:把库文件拷出来
docker compose cp server:/data/tf.db ./tf-backup-$(date +%F).db
# systemd:直接拷 /var/lib/tranfu/tf.db
```
定期(如每天)拷一份到别处即可;恢复就是把文件放回原位重启。

**轮换密钥**:改 Coolify 环境变量或 `.env` 里的 `TF_KEY` → 重新部署,并通知团队用新 key 重新 `install.sh`(旧 key 立即失效)。

---

## F. 出问题先查这几条

| 现象 | 多半原因 / 怎么办 |
|---|---|
| `curl /healthz` 不通 | 服务没起来。看 `docker compose logs` / `systemctl status tranfu`。 |
| 看板打开是空的 | 正常——还没人上报。先用 C-2 的测试事件验证。 |
| 测试事件返回 401 | `X-TF-Key` 和服务端 `TF_KEY` 不一致。 |
| 测试事件返回 403 | 开了 `TF_REQUIRE_TOKEN`,但没带 `X-TF-Token` 或令牌与 `operator` 不匹配(见 D3,重新 enroll)。 |
| 测试事件返回 413 | 请求体超过 256 KiB 上限(见 PROTOCOL §8),减小 `input`/`output`/`task`。 |
| 看板没有 prompt/代码内容 | 没声明读侧鉴权,敏感字段被服务端丢弃(见 D2),配 `TF_READ_AUTH=1` 或 `TF_READ_KEY`。 |
| 成员上报没反应 | 成员的 `TF_SERVER` 写错、或没带对 key;让其 `echo $TF_SERVER $TF_KEY` 核对;新装后要新开终端。 |
| 卡片变灰/不动 | 超过 3 分钟没心跳判为掉线,重新跑任务即可。 |
| 上报被 Access 挡住 | `/v1/events` 没放行,见 D 节。 |
| 容器重启数据没了 | 没挂卷。用根目录 `compose.yml`(已挂 `tf-data`),别手动 `docker run` 不挂卷。 |

---

## G. 安全清单(过一遍)

- [ ] `TF_KEY` 已设成随机串,没用示例值。
- [ ] 看板走 HTTPS(B1/B2),不是裸 `http` 暴露公网。
- [ ] 对外前给"读"加了门(D1),`/v1/events`、`/install.sh`、`/shims/*`、`/healthz` 已放行。
- [ ] 打开 `TF_CAPTURE_CONTENT` 或 `TF_REPORT_MEMORY` 之前,确认看板在 VPN/SSO 之后,并已设
      `TF_READ_AUTH=1` 或 `TF_READ_KEY`(D2)——否则服务端会**丢弃**敏感字段。
      这两个会把 **prompt/代码/系统指令/记忆** 上报并展示,默认都是关的。
- [ ] (可选)需要可信归因时开 `TF_REQUIRE_TOKEN` 并给成员 enroll 令牌(D3)。
- [ ] 定期备份 `tf.db`。

> 活跃时长按 **UTC 日/周** 统计,跨天会话按当天边界自动拆分(后续可加 `TF_TZ` 改时区)。
