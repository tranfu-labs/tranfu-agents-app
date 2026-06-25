# tasks:hermes-multi-profile-install

- [ ] 0. **真机前置(实现前必做)**:在装了 Hermes v0.17 的 ops profile 上验 4 件事:
      (1) `pre_tool_call` hook 子进程 `$HOME` 是不是 profile-scoped HOME(临时配一条 dump hook 把 env 落盘);
      (2) hook 子进程 env 里是否有 `HERMES_CONFIG_FILE` / `HERMES_HOME` / `HERMES_PROFILE`;
      (3) profile config.yaml 实际落盘位置(队友诊断说是 `<profile_root>/config.yaml`,需复核 default profile
      是 `~/.hermes/config.yaml`);
      (4) profile 子环境下 `<profile>/home/.hermes/skills`(或别处)是 skill 装载位置。
      有出入则**先改 proposal/design 再写代码**。

## 推断函数与基础抽取(为后续所有改动铺底)

- [ ] 1. 新增 `shims/_hermes_profile.py`:实现 `profile_home_from_env(home: str) -> ProfileInfo` 纯函数,
      按 design.md § 推断函数 的语义返回 6 个字段 + `is_default` + safened `profile_name`。
      `safen(name)` 把 `[^a-zA-Z0-9_-]` 替换成 `_`,保留原始名供日志。
- [ ] 2. 在 `install.sh` 用 POSIX sh 实现等价推断(`case` + `expr` / `sed`),作为 step 1 的 shell 双胞胎。
      抽到 `install.sh` 顶部作为函数 `tf_profile_home_from_env`,后续步骤复用。
- [ ] 3. 单测 `tests/test_hermes_profile.py`:
      正例 default(`/home/u` → `is_default=true`、`profile_name=default`);
      正例 profile(`/home/u/.hermes/profiles/ops/home` → `is_default=false`、`profile_name=ops`、
      `config_path=/home/u/.hermes/profiles/ops/config.yaml`);
      边界(profile 名含 `/` 与中文 → safened,但原始名留在 `.profile_name_raw`);
      回归(空字符串、根 `/`、`~` 字面值 → 走 default 分支不抛错)。

## install.sh:profile 检测 + marker block + 归档

- [ ] 4. `install.sh` 加 `--hermes-config <path>` 显式参数与 `$HERMES_CONFIG_FILE` env 兜底,
      最终 `CONFIG_PATH` 取值优先级:`--hermes-config` > `$HERMES_CONFIG_FILE` > 推断函数 `config_path`。
- [ ] 5. `install.sh` 写 shell rc 时,**`TF_AGENT` 默认按推断结果**:`is_default=true` → `hermes`;
      否则 `hermes-<safened_profile_name>`。用户 `--agent A` 显式覆盖仍最优先(沿用现有约定)。
- [ ] 6. `install.sh` 实现 marker block 读写(POSIX awk):
      `# >>> tranfu-hermes-hook >>>` ... `# <<< tranfu-hermes-hook <<<`,定位旧 block 整段提取,
      重写时整段替换;不存在则追加到 `$CONFIG_PATH` 末尾(保留尾部空行)。
      block 内容写绝对路径 hook,加审计注释行(写入时间 + shim 版本)。
- [ ] 7. `install.sh` marker 外旧字面行归档:`grep` 找 `command:.*tf-hermes-hook.sh`(marker 范围外)→
      整行加前缀 `# [archived by tranfu install <UTC ts>] `,写回原位(`sed -i` 等价,Mac/Linux 兼容写法)。
- [ ] 8. `install.sh` 旧 wrapper 孤儿归档:对比 `~/.tranfu/manifest.json`(上一次安装的 namespace 内文件)
      与新 manifest,差集 `mv` 到 `$HOME/.tranfu/.archive/<UTC ts>/<原相对路径>`;
      只有实际有 mv 时才创建 `<UTC ts>/` 目录(无新东西 → 不产生空目录,保幂等)。
- [ ] 9. `install.sh` 主 HOME 错位检测:`$HOME != /home/$(whoami)` 时,检查 `/home/$(whoami)/.tranfu/tf-hermes-hook.sh`,
      存在则输出 WARN 列出该路径与建议处理方式,**不动它**。
- [ ] 10. `install.sh` 幂等保护:重跑无新变化时 → stdout "no changes",config.yaml 内容字节级相同,
       `.archive/` 不创建新目录。
- [ ] 11. `install.sh` 失败显式:归档 mv 失败、config.yaml 写权限不足等 install 期错误 → **非静默**,
       输出错误并退出 != 0(与 shim 静默约束不同,install 期错误必须告诉用户)。
- [ ] 12. `shims/manifest` 扩 `namespace` 字段:tranfu 拥有的文件名集合(用于步骤 8 识别孤儿)。
       服务端 `/shims/manifest` 同步,旧客户端读不到时按当前文件名硬编码列表回退(不归档孤儿,行为不变)。

## shim 探测与 doctor 改造(共用推断)

- [ ] 13. `shims/tf_profile.py:185` skill 探测:`HOME / ".hermes" / "skills"` → `ProfileInfo.skills_dir`。
- [ ] 14. `shims/tf_profile.py:238` IM 检测:`HOME / ".hermes" / "secrets.env"` → `ProfileInfo.im_secrets_path`。
- [ ] 15. `shims/tf_profile.py:284` memory:`HOME / ".hermes" / "memory.md"` → `ProfileInfo.memory_path`。
- [ ] 16. `shims/wrapper/tf-doctor:156` hook 检查:用 `profile_home_from_env($HOME)` 推 `config_path`,
       只报当前 profile 的 marker block 是否存在(不跨 profile 扫描)。
- [ ] 17. `shims/wrapper/tf-hermes-hook.sh:7-12` 注释里 yaml 示例改为绝对路径范例,加一句"由 `install.sh` 在
       写入时展开,请勿手工 copy"。
- [ ] 18. `shims/tf_hooks.py:26` 注释更新:profile 子环境下 `$HOME` 已隔离,`tf_env.hermes.sh` 自然每 profile
       一份;前提是用户按"切到 profile 子环境再装"操作(文档侧明确)。

## 文档 / ADR / spec delta

- [ ] 19. 新增 `docs/adr/0022-hermes-multi-profile-agent-identity.md`(Accepted 等本 change 落地后改):
       决策 = default `hermes` / profile `hermes-<name>` / 用户 `--agent` 优先;关联 ADR-0006、ADR-0017。
       登记 `docs/adr/README.md`。
- [ ] 20. `QUICKSTART.md` / `USAGE.md` / `SKILL.md` 加 "Hermes profile 子环境安装" 小节:
       **先切到目标 profile 子环境**(`hermes --profile ops` 等示例)再跑 `install.sh`;支持 `--hermes-config`
       与 `--agent` 覆盖。
- [ ] 21. `UPDATE.md` 加 "升级旧 Hermes 装机" 小节:
       说明会做的 3 件事(注释旧字面行 / 归档孤儿 / 主 HOME WARN)、`.archive/` 位置、如何找回。
- [ ] 22. `docs/architecture/module-map.md` 加 `shims/_hermes_profile.py` 边界(纯函数,无副作用,
       `install.sh` / `tf_profile.py` / `tf-doctor` 共用)。
- [ ] 23. `openspec/specs/onboarding/spec.md`:套用本变更 `specs/onboarding/spec.md` delta
       (multi-profile 安装规则与可验证行为)。

## 单测

- [ ] 24. `tests/test_hermes_profile.py`(对应 step 3,已列出来,再次确认覆盖)。
- [ ] 25. `tests/test_install_marker.py`:把一段示例 config.yaml 喂给 `install.sh` 等价函数(若 install.sh
       本身难单测,抽 awk 段成独立脚本):
       (a) 无 marker / 无旧字面行 → 追加新 block,config.yaml 末尾干净;
       (b) 有 marker(旧 block)→ 整段替换,顺序与缩进保留;
       (c) marker 外有旧字面行 → 整行加注释前缀,不影响其它行;
       (d) 重跑(无变化)→ diff 为空。
- [ ] 26. `tests/test_install_archive.py`:孤儿识别 + mv 幂等:
       (a) 给定旧 `~/.tranfu/<file>` 在旧 namespace 内、不在新 manifest → `mv` 到 `.archive/<ts>/`;
       (b) 同一文件第二次跑 → 已不在 `~/.tranfu/`,不再 mv,不产生新 archive 目录;
       (c) 不在 namespace 的私有文件 → 永远不动。
- [ ] 27. 服务端 `/shims/manifest` 加 `namespace` 后,旧客户端读 manifest 仍能成功(向后兼容契约测试,
       追加到 `tests/test_app.py` 或就近现有 manifest 测试)。

## 验证 / 部署

- [ ] 28. 真机:ops profile 首装(切到子环境 → 跑 install.sh → skill_view → 远端排行 + 卡片
       `agent=hermes-ops`)。
- [ ] 29. 真机:default profile 首装(主 HOME → install.sh → skill_view → 远端排行 + 卡片 `agent=hermes`,
       与升级前数值/卡片身份逐字节一致)。
- [ ] 30. 真机:同机双 profile(default + ops 各装一次,各 skill_view 一次 → `/api/state` 两张独立卡)。
- [ ] 31. 真机:升级路径(已装旧版机器跑新 install.sh → marker block 出现 / 旧字面行被注释 / 旧孤儿在 archive)。
- [ ] 32. 真机:幂等(连跑两次 install.sh → 第二次 "no changes"、config.yaml diff 空、archive 无新建)。
- [ ] 33. 部署顺序:**先**服务端 `/shims/manifest` 加 `namespace`、新 install.sh 推到 `/install.sh`,
       **后**通知队友重跑 `install.sh`(顺序反了会出现"新 install.sh 找不到 namespace 字段 → 按硬编码回退" 的过渡期,
       行为正确但不归档孤儿,可接受)。
