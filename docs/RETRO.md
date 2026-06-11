# RETRO — TRANFU//AGENTS 接入与上报的踩坑复盘

一次从「装好就坏」一路查到根的复盘。结论先行:最值钱的三条教训——
1. **遥测失败必须可观测**,不能静默冒充成功([ADR-0018](adr/0018-telemetry-failure-must-be-observable.md))。
2. **身份模型**(按 agent/runtime 隔离 + 服务端归一化)是一次性门,得早定([ADR-0015](adr/0015-server-side-identity-normalization.md)、[ADR-0016](adr/0016-per-runtime-identity-files.md))。
3. **可观测性的边界 = 你能控制的调度链路**;越界就只能靠伪造或越权,两者都不做([ADR-0017](adr/0017-cloud-runtimes-do-not-self-report.md))。

下面逐条:**问题/经验 → 调整建议**。

## 一、接入与上报机制
1. **`curl | bash` 是接入的第一个雷。** 安全意识强的 agent 会(正确地)抵触。→ 第一方工具也提供"可审查再执行"的路径;云端 runtime 干脆不给 curl|bash(见 [ADR-0017](adr/0017-cloud-runtimes-do-not-self-report.md))。
2. **hook 写进 `.zshrc` 失效。** hook 跑非交互 shell、不读 rc → 静默不报。→ 身份配置放 hook 能确定读到的 per-runtime 文件并显式 `source`(见 [ADR-0016](adr/0016-per-runtime-identity-files.md))。
3. **静默失败伪装成功(最坑)。** `TF_SERVER` 为空时只打印、exit 0、无 spool,看着"成功"实则一条没发,据此误判多轮。→ 失败必须可观测(见 [ADR-0018](adr/0018-telemetry-failure-must-be-observable.md))。

## 二、身份模型(最贵的一次性门)
4. **skill 画像按机器、不按 agent。** 扫全机 `~/.claude/skills`,所有 agent 报相同列表 + 混入软链借来的别家技能。→ 身份相关探测按 runtime 隔离目录。
5. **聪明的启发式不通用——"跳过软链"误伤多儿。** 为让 Claude 不显示借来的 lark,把 Hermes 自己的 lark 软链也砍了。→ 启发式按场景分流(Claude 借来的跳、Hermes 自己的留)+ 永远留显式覆盖(`TF_SKILLS`)。
6. **operator/runtime 大小写裂成多个 Pod。** → 服务端归一化(见 [ADR-0015](adr/0015-server-side-identity-normalization.md))。
7. **同机多 agent 共用单文件 → 串号(最隐蔽)。** "单一真源 `tf_env.sh`"被后装 agent 覆盖,活动报成别人。→ 按 runtime 一份身份文件(见 [ADR-0016](adr/0016-per-runtime-identity-files.md));`TF_MODELS` 同病同治。

## 三、诊断与"在线"的真假
8. **别凭假设下结论,要活体探针。** 两次说"重启就好"都错,真因是身份串号。→ 定位用真实探针(发一条、看 session_id 落到哪个 agent),而非"应该是 X"。
9. **看板上的"在线"可能是 stale 或伪造。** 多儿的卡来自旧事件 + 手动 push,gateway 根本没接 tranfu。→ 区分"卡上有数据"和"有活的上报机制";验收追到机制。
10. **cron 心跳是反模式(诚实红线)。** 每 5 分钟谎报 `running`、把空闲算成活跃工时,且 5min > 3min 阈值仍闪 idle。→ 事件驱动只在干活时亮;真要"待命在线"就加诚实的 `standby` 状态(渲染在线但不计工时),绝不用 running 冒充。多儿最终改为 Hermes 原生事件 hook(`config.yaml hooks:` + `tf-hermes-hook.sh`)。

## 四、运维与交付
11. **测试数据会污染真看板,且删不掉(90 天保留)。** → 加 admin 删除端点(已做 `DELETE /v1/events`);测试用独立 operator/session 前缀。
12. **部署 ≠ 合并(反复踩)。** 提 PR、合 main 都不等于线上生效;部署是手动单独一步。→ 当两件事对待 + 部署后跑版本探针(见 [ADR-0018](adr/0018-telemetry-failure-must-be-observable.md))。
13. **幂等性。** install 重复运行往 rc 无限追加、重装不升级旧 hook 命令。→ rc 用 marker 守护;重装自动升级旧命令(见 ADR-0010)。
14. **密钥四处明文 + 落进云端聊天。** `TF_KEY` 散在 `.zshrc/.zshenv/tf_env/备份`,还被贴进云端对话。→ 收敛到单文件 600;引导用 `<TF_KEY>` 占位、私下发;外泄了就轮换。

## 五、可观测性的边界(最该写进 ADR 的认知)
15. **云端黑盒 agent 自报遥测 = 逼它越安全线。** mulerun 的 agent 正确拒绝了 curl|bash 和 API beacon。→ 云端走 webhook/operator 配置/调度端 coarse,永不靠"说服 agent"(见 [ADR-0017](adr/0017-cloud-runtimes-do-not-self-report.md))。
16. **看板只能诚实追踪"调度链路经过可控节点"的 agent。** 纯网页托管 agent 没有干净的追踪路径。→ 当产品边界写进文档,别硬接;接受"有些 agent 不上板"比伪造数据健康。

## 过程层面做对的事(值得保持)
- **先看清再动手**:开局没盲跑 install.sh,先审仓库,救了命。
- **薄切片 + 活体探针**定位真因,比凭推理快也准。
- **每个修复独立 PR + 契约测试**(#7–#11),保证回归不破。
- **守住诚实红线**:不伪造在线、不帮绕过 agent 的安全拒绝。
