# ADR-0015 身份归一化在服务端:operator 大小写无关、runtime 小写

- 状态:Accepted
## 背景
同一个人/agent 因 `operator` 大小写或空格不一致(`NEZHA` vs `nezha`)、`runtime` 大小写不一致(`Hermes` vs `hermes`)被当成不同实体,在看板上裂成多张卡(参见 ADR-0006 的合并键)。客户端写法**无法保证一致**:一台机器上有多份配置(shell rc、`secrets.env`、`tf_env.sh`)、多个 runtime、多次安装,任意一处大小写不同就裂。
## 决策
归一化放**服务端**,作为唯一权威:
- `POST /v1/events` 与 `POST /v1/enroll` 都经 `canon_operator()`:operator 按 `casefold()+trim()` 归一,映射到**首次出现的展示 casing**(`identities` 表)。
- `runtime` 写入时 `lower()+trim()`(受控词表;展示侧由 `RT_LABEL` 还原 `hermes`→`Hermes`)。
- 所有分组/去重/画像键、令牌归因都用归一化后的值。
- `init_db` 内置**幂等迁移**:把历史 `events`/`profiles` 的 operator/runtime 归一化,`profiles` 按 `(operator,ak,runtime)` 去重保留最新——部署即自动合并现存重复卡。
## 后果
- ✅ 同一人/agent 永远一张卡,无论客户端怎么写大小写/空格。
- ✅ 跨大小写令牌仍验证(enroll 同样归一化,绑定的是规范名)。
- 约束:**客户端不得假设大小写敏感**;归一化的权威在服务端。展示 casing = 首见值,要改某身份的展示写法,改 `identities` 表的 `display`,不要靠客户端"统一大小写"。
