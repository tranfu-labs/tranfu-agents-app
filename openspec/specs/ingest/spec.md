# 规格:ingest(事件采集域)

事实来源:`server/app.py` 的 `POST /v1/events` 与 `PROTOCOL.md`(TATP v0.1)。

## 身份与字段
- 身份 = `operator` + (`agent` 若有,否则 `runtime`)。
- 必填:`operator`、`runtime`、`session_id`、`status`。
- 可选:`agent`(用途标签)、`task`、`current_step`、`ts`、`model`、`input`/`output`(opt-in)、`meta`。
- `status` 枚举:`started / running / waiting / blocked / done / error / idle`。
- 可选 profile 字段(任意子集):`models, config, mcp, skills, integrations, about, tips, cf, instructions, memory`。

## 规则(MUST)
1. 写入须带请求头 `X-TF-Key`,且等于服务端 `TF_KEY`(`TF_KEY` 为空时仅限本地开发)。
2. **去重**:仅当 `status` 或 `current_step` 相对该身份的上一行发生变化时才落新行;
   否则视为心跳,仅更新 `last_seen`,响应 `{"heartbeat": true}`,且不进活动流。
3. 收到含 profile 字段的事件时,按身份**更新该身份最新 profile**(`profiles` 表);技能名首次出现记入 `skills_seen.first_day`。
4. 时间一律按 UTC;`day` 取 UTC 日期。
5. 云端运行时 `{manus, mulerun, chatgpt}` 标记 `fidelity = coarse`,其余 `full`。
6. `input`/`output`(内容)与 `instructions`/`memory`(敏感)默认不应被上报,仅在使用者显式开启时携带。

## 不变量
- 不存在任何 token / 成本字段(见 ADR-0002)。
- 上报失败不得影响使用者 agent(客户端侧静默,见 ADR-0005)。

## 可验证行为(示例)
- 连发两条相同 `status+current_step` → 第二条返回 `heartbeat:true`,活动流不增。
- 带 `skills` 的事件后,`/api/state` 该身份 session 含 `skills`,且 leverage 资产数随之增加。
