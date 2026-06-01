# DEV-SETUP — 从 zip 到线上(给开发,一步步走通)

> 目标:基于交付的 `tranfu-agents-app.zip` **重新建库 + 部署**,让
> `https://tranfu-agents-app.tranfu.com/` 跑最新版,并修复当前的「未连接服务端」。
> 全程约 15 分钟。更深入的部署/运维见 `DEPLOY.md`;更新现有部署见 `UPDATE.md`。

整体五步:**解压 → 建库 → 起服务 → 暴露(Tunnel)→ 连通验证**。

---

## 0. 准备

- 一台 24h 常开的机器(就是现在跑 tunnel 的那台即可),装好 `git`、`docker`、`cloudflared`。
- 一个接入密钥 `TF_KEY`:**沿用现在线上用的那个**;若要新建:`openssl rand -hex 24`。

---

## 1. 解压代码

```bash
unzip tranfu-agents-app.zip
cd tranfu-agents-app
ls    # 应看到 server/ dashboard/ shims/ deploy/ 及若干 .md
```

## 2. 建 GitHub 库并推上去

用 GitHub CLI 最快(先 `gh auth login` 登录一次):
```bash
git init
git add -A
git commit -m "TRANFU//AGENTS — latest (logo + 三视图 + 自动探测 shim)"
git branch -M main
gh repo create <org或你>/tranfu-agents-app --private --source=. --remote=origin --push
```
> 库名/可见性按你们规范定。要继续用现有的 `tranfu-labs/tranfu-agents-app`,
> 就把上面 `gh repo create` 换成给现有库加 remote 再推:
> ```bash
> git remote add origin https://github.com/tranfu-labs/tranfu-agents-app.git
> git push -u origin main      # 若历史冲突且确认以这套为准,可加 --force(慎用)
> ```

## 3. 起服务(Docker,推荐)

```bash
cd deploy
cp .env.example .env
# 编辑 .env,把 TF_KEY= 改成线上现用的密钥
docker compose up -d --build
```
本机自检:
```bash
curl http://localhost:8788/healthz            # 返回 ok
curl http://localhost:8788/api/state | head   # 返回 JSON
```
> 不想用 Docker 就走 systemd,见 `DEPLOY.md` 的 A2 段。

## 4. 用 Cloudflare Tunnel 暴露(子域名照旧)

子域名 `tranfu-agents-app.tranfu.com` 已存在,只要确保隧道把**整站**指向后端
(而不是只挂一个静态 HTML)。检查 `~/.cloudflared/config.yml`:
```yaml
ingress:
  - hostname: tranfu-agents-app.tranfu.com
    service: http://localhost:8788      # 关键:指向后端服务(含页面+API),不是静态文件
  - service: http_status:404
```
改完重启隧道:
```bash
sudo systemctl restart cloudflared      # 或 cloudflared tunnel run <隧道名>
```
> 全新建隧道见 `DEPLOY.md` 的 B1 段(create / route dns / config.yml / service install)。

## 5. 连通验证(关键 —— 线上现在卡的就是这步)

从公网验证(任意机器):
```bash
curl https://tranfu-agents-app.tranfu.com/healthz            # ok
curl https://tranfu-agents-app.tranfu.com/api/state | head   # JSON

# 发一条测试事件(X-TF-Key 用线上 TF_KEY)
curl -s -XPOST https://tranfu-agents-app.tranfu.com/v1/events \
  -H "content-type: application/json" -H "X-TF-Key: <TF_KEY>" \
  -d '{"operator":"test","runtime":"claude-code","session_id":"smoke1","status":"running","task":"联通测试","current_step":"hello"}'
```
最后一条返回 `{"ok":true,...}`,刷新页面应看到 **test** 这个 Pod,
且**不再显示「未连接服务端」**。

若仍显示「未连接服务端」:基本就是第 4 步的 Tunnel 没把 `/api/*`、`/v1/*` 代理到后端
(只挂了静态页)。回到第 4 步,确认 `service: http://localhost:8788`。

---

## 6. 把部署服务器指向新库(以后好更新)

如果这台部署机当初是从旧库 clone 的,改成跟踪新库,以后 `git pull` 才对:
```bash
git remote set-url origin <新库地址>
git pull
```

## 7. 发给团队(可选)

接入命令(每人改 `--operator/--runtime`):
```bash
curl -fsSL https://raw.githubusercontent.com/<新库owner>/<库名>/main/install.sh | bash -s -- \
  --server https://tranfu-agents-app.tranfu.com --key <TF_KEY> --operator 名字 --runtime claude-code
```
> 一键安装要 raw 可读 → 库需公开,或在私有库下改用其它分发方式。成员细节见 `QUICKSTART.md`。

---

## 完成确认

- [ ] 公网 `…/healthz` 返回 ok、`…/api/state` 返回 JSON
- [ ] 测试事件能在看板上看到
- [ ] 页面不再显示「未连接服务端」
- [ ] logo 是新的(红色图形内联),有 Pods 看板 / Agents 列表 两个标签
- [ ] 部署机 remote 已指向新库
