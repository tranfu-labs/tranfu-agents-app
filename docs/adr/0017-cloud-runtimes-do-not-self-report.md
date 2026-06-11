# ADR-0017 云端 runtime 不自报;可观测性边界 = 可控的调度链路

- 状态:Accepted
## 背景
云端/托管 agent(`mulerun`/`manus`/`chatgpt`,见 `CLOUD_RUNTIMES`)是黑盒:沙箱不持久,也没有用户机器上的 shell。install.sh(写本地文件 + 装 shell hook)**根本不适配**它们。

实测:让一个云端 agent 自己跑 `curl|bash` 安装、或自己 `POST /v1/events`,等于要它向**无法验证的端点发送会话数据 + 凭证**。安全意识强的 agent 会(正确地)**拒绝**——这正是挡住"恶意版同款请求"的护栏。用话术绕过它的拒绝 = 帮人社工越过 agent 的安全判断,技术与恶意用途同形,**不做**。
## 决策
- **云端 runtime 不自报。** 上报走二选一:
  1. **平台 webhook / operator 配置的可信通道**——由用户在平台层(mulerun 后台等)把生命周期事件 POST 到 `/v1/events`,是 operator 授权的基础设施,不是 agent 在对话里临时决定。
  2. **调度端 coarse**——`tf-run --runtime <cloud> --coarse -- <触发命令>`,由用户**可信的本机**代报起止;云端 agent 保持黑盒、不碰 key、不连端点。
- install.sh / 接入引导**检测到云端 runtime 时给这套,不给 `curl|bash`**。
- 看板**只追踪"调度链路经过可控节点"的 agent**;纯网页里手点的全托管 agent,接受它**不上板**。
## 后果
- ✅ 不逼任何 agent 越过自己的安全线;接入方式经得起安全审视。
- ✅ 可观测性边界清晰、诚实:能追的追,追不到的明说,不靠伪造。
- 约束:**不得设计任何"需要说服或绕过 agent 安全判断才能上报"的路径**。云端 runtime 在看板上是 coarse 保真度(只看起止),不假装有逐步可见性。
