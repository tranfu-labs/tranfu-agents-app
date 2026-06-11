# ADR-0016 身份/配置按 runtime 隔离成独立文件,杜绝同机多 agent 串号

- 状态:Accepted
## 背景
同一台机器上常常跑**多个 agent**(如 Claude Code「赛博哪吒」+ Hermes「多儿」)。早期 install.sh 把身份写进**单个全局** `~/.tranfu/tf_env.sh`,hook 命令 source 它。两个 agent 各装一次时,**后装的覆盖前者的身份** → 赛博哪吒的 hook 一 `source` 就拿到多儿的 `TF_AGENT/TF_RUNTIME`,把它的全部活动**串报成多儿**,赛博哪吒的卡反而卡死。`TF_MODELS` 同病(codex 误报同机 Claude 的模型,见 ADR/PR #13)。

另一面:hook 跑在**非交互 shell**,不读 `~/.zshrc`(参见 ADR-0009 的"不靠环境变量取上下文")。所以身份必须来自 hook 能确定读到的**文件**,而非交互式 shell 的 rc 副作用——否则静默不上报。
## 决策
- install.sh 为每个 runtime 写**独立** `~/.tranfu/tf_env.<runtime>.sh`(身份 + **per-runtime** `TF_MODELS`)。
- 各 runtime 的 hook/wrapper **只 source 自己那份**(`tf_hooks` 的命令、Hermes 的 `tf-hermes-hook.sh`)。
- 共享 `tf_env.sh` 仍写,但仅供 shell rc / `tf-run`——`tf-run` 显式传 `--agent/--runtime`,只需要这里的 `server/key`,所以"最后安装者覆盖"对它无害。
## 后果
- ✅ 同机多 agent 的身份与模型**互不串**;一个 agent 的活动永远报在自己名下。
- ✅ hook 不依赖交互式 shell 是否 source 过 rc。
- 约束:**不得退回单一全局身份文件**;新增 runtime 必须有自己的 `tf_env.<runtime>.sh`;模型标签是 per-runtime 的,**不写进共享 `tf_env.sh`**。与 ADR-0015 配合:文件隔离防"写错名",服务端归一化防"写法不一致"。
