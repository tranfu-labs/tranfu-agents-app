# tranfu-agents-app 部署文档

本文按当前项目实际结构编写：服务端是 `FastAPI + uvicorn`，看板静态页是 `dashboard/index.html`，由服务端在 `/` 路由读取并返回，SQLite 数据保存在 Docker volume 中。

和参考里的纯静态站不同，本项目虽然有静态 HTML，但页面需要调用同一个服务的 `/api/state` 接口，所以不要在 Caddy 中配置 `root` / `file_server`，Caddy 只做 HTTPS 反向代理到本机 `8787` 端口。

以下示例默认：

- 域名：`tranfu-agents-app.tranfu.com`
- 服务器公网 IP：`120.77.223.183`
- 项目目录：`/var/www/tranfu/tranfu-agents-app`
- 服务端口：`127.0.0.1:8787`

本文后续命令均按 `tranfu-agents-app.tranfu.com` 编写。

---

## 0. Ubuntu 安装 Docker 和 Compose

需要安装 Docker Engine 和 Docker Compose v2 插件。Compose v2 的命令是：

```bash
docker compose version
```

注意是 `docker compose`，不是 `docker composer`。老版本 `docker-compose` 是另一个命令，不建议新部署继续使用。

先移除可能冲突的旧包：

```bash
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" 2>/dev/null || true
done
```

添加 Docker 官方 apt 仓库：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

UBUNTU_CODENAME=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
ARCH=$(dpkg --print-architecture)

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME}
Components: stable
Architectures: ${ARCH}
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update
```

安装 Docker Engine、Buildx 和 Compose 插件：

```bash
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

启动并验证：

```bash
sudo systemctl enable --now docker
sudo docker run hello-world
docker compose version
```

如果希望当前用户直接运行 `docker` 命令，不每次加 `sudo`：

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker run hello-world
```

如果不做这一步，后文所有 `docker compose ...` 命令都需要改成 `sudo docker compose ...`。

---

## 1. 准备项目目录

```bash
sudo mkdir -p /var/www/tranfu/tranfu-agents-app
sudo chown -R "$USER":"$USER" /var/www/tranfu/tranfu-agents-app
```

把当前项目代码拉取或同步到该目录：

```bash
cd /var/www/tranfu/tranfu-agents-app
```

确认关键文件存在：

```bash
ls server/app.py server/Dockerfile deploy/docker-compose.yml dashboard/index.html
```

---

## 2. 配置服务环境变量

```bash
cd /var/www/tranfu/tranfu-agents-app
cp deploy/.env.example deploy/.env
vi deploy/.env
```

配置内容：

```env
TF_KEY=改成一串随机密钥
```

如果服务器上已经有 `.env.local`，需要注意：当前 `deploy/docker-compose.yml` 只读取 `deploy/.env`：

```yaml
env_file: [ .env ]
```

所以 `.env.local` 不会自动进入容器。可以把已有配置复制过去：

```bash
cp .env.local deploy/.env
```

或者手动把 `.env.local` 里的 `TF_KEY=...` 填到 `deploy/.env`。

生成随机密钥可用：

```bash
openssl rand -hex 24
```

`TF_KEY` 是团队成员上报事件用的密钥，必须保存好。

---

## 3. 启动服务

推荐用项目自带 Docker Compose：

```bash
cd /var/www/tranfu/tranfu-agents-app
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml up -d --build
```

查看状态：

```bash
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml ps
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml logs -f --tail=100 server
```

本机验证：

```bash
curl http://127.0.0.1:8787/healthz
```

期望得到：

```text
ok
```

安全建议：如果只允许 Caddy 访问服务，把 `deploy/docker-compose.yml` 的端口绑定改成只监听本机：

```yaml
ports:
  - "127.0.0.1:8787:8787"
```

然后重启：

```bash
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml up -d
```

---

## 4. 配置 Caddy

当前项目由 Docker 服务提供 HTTP。`dashboard/index.html` 会由 FastAPI 在 `/` 返回，并继续请求 `/api/state`，所以 Caddy 配置使用 `reverse_proxy`，不要用 `root` / `file_server` 单独托管静态文件。

编辑：

```bash
sudo vi /etc/caddy/Caddyfile
```

新增配置：

```caddyfile
tranfu-agents-app.tranfu.com {
    reverse_proxy 127.0.0.1:8787

    tls {
        dns alidns {
            access_key_id {env.ALICLOUD_ACCESS_KEY}
            access_key_secret {env.ALICLOUD_SECRET_KEY}
        }
    }
}
```

默认不要配置 Caddy `basic_auth`。当前项目通过 `TF_KEY` 保护事件上报接口；Caddy 只负责域名、HTTPS 和反向代理。

如果 Caddy 还没有配置阿里云 DNS 插件环境变量，添加 systemd override：

```bash
sudo systemctl edit caddy
```

填入：

```ini
[Service]
Environment=ALICLOUD_ACCESS_KEY=你的Ali_Key
Environment=ALICLOUD_SECRET_KEY=你的Ali_Secret
```

验证配置文件是否正确：

```bash
caddy validate --config /etc/caddy/Caddyfile
```

让配置生效：

```bash
sudo systemctl reload caddy
```

如果刚才新增或修改了 systemd 环境变量，需要重启 Caddy 进程：

```bash
sudo systemctl daemon-reload
sudo systemctl restart caddy
```

如果 reload 失败，查看日志：

```bash
journalctl -u caddy -n 100 --no-pager
```

如果 `caddy validate` 报：

```text
base64-decoding password: illegal base64 data at input byte 0
```

说明 Caddyfile 里还残留了错误的 `basic_auth` 配置。当前部署不需要它，删掉整段 `basic_auth { ... }` 和相关 `handle` 分支，只保留上面的 `reverse_proxy 127.0.0.1:8787` 配置。

---

## 5. 配置域名

添加 `tranfu-agents-app.tranfu.com` 的 A 记录：

```bash
ALIBABA_CLOUD_ACCESS_KEY_ID="$Ali_Key" \
ALIBABA_CLOUD_ACCESS_KEY_SECRET="$Ali_Secret" \
aliyun alidns AddDomainRecord \
  --region cn-hangzhou \
  --DomainName tranfu.com \
  --RR tranfu-agents-app \
  --Type A \
  --Value 120.77.223.183 \
  --TTL 600
```

执行结果示例：

```json
{
  "RecordId": "xxxxxxxxxxxxxxxx",
  "RequestId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

检查是否成功：

```bash
ALIBABA_CLOUD_ACCESS_KEY_ID="$Ali_Key" \
ALIBABA_CLOUD_ACCESS_KEY_SECRET="$Ali_Secret" \
aliyun alidns DescribeDomainRecords \
  --region cn-hangzhou \
  --DomainName tranfu.com \
  --RRKeyWord tranfu-agents-app \
  --TypeKeyWord A
```

期望记录里包含：

```json
{
  "RR": "tranfu-agents-app",
  "Type": "A",
  "Value": "120.77.223.183",
  "Status": "ENABLE"
}
```

如果记录已存在，不要重复添加，使用已有 `RecordId` 更新：

```bash
ALIBABA_CLOUD_ACCESS_KEY_ID="$Ali_Key" \
ALIBABA_CLOUD_ACCESS_KEY_SECRET="$Ali_Secret" \
aliyun alidns UpdateDomainRecord \
  --region cn-hangzhou \
  --RecordId "$RecordId" \
  --RR tranfu-agents-app \
  --Type A \
  --Value 120.77.223.183 \
  --TTL 600
```

---

## 6. 公网验证

检查 DNS：

```bash
dig +short tranfu-agents-app.tranfu.com
```

期望得到：

```text
120.77.223.183
```

检查 HTTPS 和服务健康：

```bash
curl -I https://tranfu-agents-app.tranfu.com/
curl https://tranfu-agents-app.tranfu.com/healthz
```

`/healthz` 期望得到：

```text
ok
```

发送一条测试事件：

```bash
cd /var/www/tranfu/tranfu-agents-app
TF_KEY="$(grep '^TF_KEY=' deploy/.env | cut -d= -f2-)"

curl -sS -X POST https://tranfu-agents-app.tranfu.com/v1/events \
  -H "Content-Type: application/json" \
  -H "X-TF-Key: $TF_KEY" \
  -d '{
    "operator": "deploy",
    "runtime": "curl",
    "session_id": "deploy-test-001",
    "status": "running",
    "task": "部署验证",
    "current_step": "hello board"
  }'
```

期望得到：

```json
{"ok":true}
```

浏览器打开：

```text
https://tranfu-agents-app.tranfu.com
```

看板上应能看到 `deploy` 的测试卡片。

---

## 7. 团队成员接入

管理员给团队成员两项信息：

- 接入地址：`https://tranfu-agents-app.tranfu.com`
- 接入密钥：`deploy/.env` 里的 `TF_KEY`

手动安装示例：

```bash
curl -fsSL https://raw.githubusercontent.com/tranfu-labs/tranfu-skills/main/tranfu-agent-telemetry/install.sh \
  | bash -s -- --server https://tranfu-agents-app.tranfu.com --key "$TF_KEY" --operator bob --runtime codex
```

更多说明见项目内 `USAGE.md`。

---

## 8. 更新发布

```bash
cd /var/www/tranfu/tranfu-agents-app

# 拉取或同步最新代码后
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml up -d --build
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml logs -f --tail=100 server
```

再次验证：

```bash
curl https://tranfu-agents-app.tranfu.com/healthz
```

---

## 9. 数据与备份

SQLite 数据库路径在容器内是：

```text
/data/tf.db
```

Docker Compose 会把它保存到 volume：

```text
tranfu-agents-app_tf-data
```

备份：

```bash
docker run --rm \
  -v tranfu-agents-app_tf-data:/data \
  -v "$PWD":/backup \
  alpine \
  sh -c 'cp /data/tf.db /backup/tf.db.$(date +%Y%m%d%H%M%S).bak'
```

---

## 10. 常用排查

### Docker Hub 拉镜像超时

如果构建卡在：

```text
load metadata for docker.io/library/python:3.12-slim
dial tcp ... i/o timeout
```

这是 Docker daemon / BuildKit 在拉基础镜像时访问 Docker Hub 超时。可以用代理，但不要只在命令前加：

```bash
HTTPS_PROXY=http://127.0.0.1:3128 HTTP_PROXY=http://127.0.0.1:3128 docker compose ...
```

这种写法不一定会影响 Docker daemon 拉镜像。更稳的做法是给 Docker 服务配置代理。

这个代理配置主要影响 Docker daemon 自己的外网请求，例如拉取基础镜像、查询镜像元数据、推送镜像等；不会自动让已经运行的业务容器流量都走代理，也不会改变 Caddy 访问 `127.0.0.1:8787` 的方式。需要注意的是，执行 `sudo systemctl restart docker` 应用配置时，运行中的容器可能会有短暂中断。

如果代理就在服务器本机，并且监听 `127.0.0.1:3128`：

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d

sudo tee /etc/systemd/system/docker.service.d/proxy.conf >/dev/null <<'EOF'
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:3128"
Environment="HTTPS_PROXY=http://127.0.0.1:3128"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
EOF

sudo systemctl daemon-reload
sudo systemctl restart docker
systemctl show --property=Environment docker
```

先单独验证基础镜像能否拉取：

```bash
docker pull python:3.12-slim
```

成功后再重新部署：

```bash
cd /var/www/tranfu/tranfu-agents-app
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml up -d --build
```

注意：如果代理在你自己的电脑上，不在服务器上，那么服务器里的 `127.0.0.1:3128` 指的是服务器自己，不是你的电脑。此时需要在服务器上启动代理，或用 SSH 反向隧道把本地代理映射到服务器。

查看容器：

```bash
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml ps
```

查看服务日志：

```bash
docker compose -p tranfu-agents-app -f deploy/docker-compose.yml logs --tail=200 server
```

查看 Caddy 日志：

```bash
journalctl -u caddy -n 200 --no-pager
```

检查端口：

```bash
ss -lntp | grep 8787
```

如果事件上报返回 `401`，检查客户端使用的 `X-TF-Key` 是否等于服务器 `deploy/.env` 中的 `TF_KEY`。

如果网页能打开但看板没数据，先用第 6 步的 `curl -X POST /v1/events` 发送测试事件。
