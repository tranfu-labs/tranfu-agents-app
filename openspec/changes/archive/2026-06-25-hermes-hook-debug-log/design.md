# 设计:hermes-hook-debug-log

## 信源声明

本设计的事实基础:

- 本仓库代码现状 [shims/tf_hook.py](../../../shims/tf_hook.py)、[shims/tf_report.py](../../../shims/tf_report.py)、[shims/wrapper/tf-hermes-hook.sh](../../../shims/wrapper/tf-hermes-hook.sh)、[install.sh](../../../install.sh)。
- [PROTOCOL.md](../../../PROTOCOL.md) §5 隐私边界:只报名、不报内容(本变更把这条边界向本地一档同样收紧)。
- POSIX `write(2)`: `O_APPEND` 模式下 < `PIPE_BUF`(4096B 保底)的 append 是原子的。本变更每条日志硬控在 < 200B,远低于此阈。
- `os.rename(src, dst)` 在 POSIX 同文件系统下是原子操作。

## 已确认的决策

1. **目标**:Hermes 钩子链路加常态可观察日志,事后可查全链路状态。范围仅 Hermes。
2. **触发模式**:**默认开**。逃逸口 `TF_HOOK_DEBUG=0` 关闭。理由:用户原话「加一个 hermes 的 log」诉求是常态可观察,按需开的方案(harden-codex 的 `TF_DEBUG_HOOK=1`)解决不了"下次又漏诊断时没开 → 抓瞎"的根本问题。
3. **轮转**:**双文件 rotate**,每份 5MB,总上限 10MB。理由:磁盘占用上限明确(2×阈值),实现 ~10 行(`os.rename` + 文件大小检查),无外部依赖。优于"单文件自截"(中间段会丢)和"按日期保留 N 天"(要扫目录清旧文件,复杂度多一档)。
4. **写哪些事件**:**全量 Hermes 事件**(`HERMES_EVENTS`),不仅是 `pre_tool_call`。理由:未来其他诊断(如 session 始末漏匹配)也能从这份日志反推。
5. **字段**:8 个固定字段(见下),禁写 raw stdin、tool_input 完整体、shell 命令文本。隐私边界与 PROTOCOL.md §5 一致。
6. **接入点**:`_run_report()` 一处。`_spawn_selfupdate()` **不接入**——detached 长进程,抓 rc 会卡热路径。
7. **不互锁**:POSIX `O_APPEND` 对 <PIPE_BUF 的 append 已原子,`os.rename` 也是原子。不引入 fcntl.flock。
8. **写失败静默**:磁盘满 / 父目录只读 → `try/except` 包住,不影响 `tf_report.py` 的调用与上报。

## 数据流

```
Hermes pre_tool_call → tf-hermes-hook.sh → tf_hook.py.main()
  → resolve(d) → argv
  → _run_report(argv):
      proc = subprocess.run([..., tf_report.py, *argv],
                            timeout=8,
                            stdout=DEVNULL,
                            stderr=PIPE)
  → _hook_log(ev, tool, sid, skill, argv, rc=proc.returncode, err=proc.stderr[:80]):
      ev ∉ HERMES_EVENTS  → return  (Claude/Codex 不落)
      TF_HOOK_DEBUG == "0" → return  (逃逸口)
      _ensure_log_dir()         (os.makedirs(..., exist_ok=True))
      _rotate_if_needed()        (os.stat(LOG_PATH).st_size >= LOG_MAX → os.rename(LOG_PATH, LOG_PATH + ".1"))
      open(LOG_PATH, "a", encoding="utf-8").write(json.dumps(record) + "\n")
      所有上面这些都包 try/except Exception: pass
```

`_run_report()` 的 `subprocess.run` 参数从原 `stdout=DEVNULL, stderr=DEVNULL` 改为 `stdout=DEVNULL, stderr=subprocess.PIPE`。`timeout=8` 不变;`subprocess.TimeoutExpired` 已被原代码的 `except Exception: pass` 兜住,补一条:超时分支 rc 记为 `-1`、err 记 `"timeout"`、仍写一行日志。

## 日志记录字段表(NDJSON 一行一条)

| 字段 | 类型 | 内容 | 上限 |
|---|---|---|---|
| `ts` | string | UTC ISO8601 秒精度,如 `"2026-06-25T10:23:11Z"` | 固定 20 字符 |
| `ev` | string | `hook_event_name` 原样,如 `"pre_tool_call"` | 实际最长 16 字符 |
| `tool` | string | `tool_name` 字符串(空则空) | 截前 32 字符 |
| `sid` | string | `_session_id()` 返回值的**前 8 字符**(脱敏) | 8 字符 |
| `skill` | string | `_skill_name()` 返回值(空 = 未识别) | 截前 64 字符 |
| `argv_tail` | string | `tf_report.py` argv 拼成 string 后**取末 80 字符** | 80 字符 |
| `rc` | int | `subprocess.returncode`;超时 = -1 | — |
| `err` | string | rc==0 时为 `""`;否则 `stderr.decode(errors="replace")[:80]` | 80 字符 |

每行长度上界 ≈ 20+16+32+8+64+80+8+80 + JSON 框架 ≈ 380B(留余量)。实际平均 ~150B。**禁写**:`tool_input` 任何非 `name` 字段、stdin 全文、PII。

## 路径与常量

```
LOG_DIR  = ~/.tranfu/logs                  (与 openclaw-skill.log 同目录,便于诊断时一并打包)
LOG_PATH = LOG_DIR / hermes-hook.ndjson    (当前)
LOG_BAK  = LOG_DIR / hermes-hook.ndjson.1  (上一份,rotate 时覆盖)
LOG_MAX  = 5 * 1024 * 1024 = 5MB           (硬编码,本变更不暴露环境变量)
LOG_KEEP = 1                               (备份份数;若未来要 N 份再改;只保留一份足够定位最近问题)
HERMES_EVENTS = {
    "on_session_start", "pre_llm_call", "pre_tool_call",
    "post_tool_call",   "post_llm_call", "on_session_end",
}
```

`HERMES_EVENTS` 与 [shims/tf_hook.py](../../../shims/tf_hook.py) `MAP` 里 snake_case 那批(行 41-47)严格对齐。Claude/Codex 用 CamelCase 事件名(`SessionStart` 等),自动不命中。

## 并发与原子性

Hermes 一次工具调用前后可能连发两条 hook(`pre_tool_call` + `post_tool_call`),也可能跨工具调用快速堆叠。两个 hook = 两个 python 进程同时写同一份日志。

- `open(LOG_PATH, "a")` 在 POSIX 上设 `O_APPEND` 标志。kernel 对 < PIPE_BUF 的 write 保证原子追加。本变更每行 < 400B,远低于 4096B 阈,**两进程的行不会交错**。
- `os.rename(LOG_PATH, LOG_BAK)` 在 POSIX 同 fs 下原子。**理论竞态**:进程 A 刚拿到 `os.stat().st_size >= LOG_MAX`、还没 rename,进程 B 同时检查也判 size 超阈、也 rename。结果:A 把 `LOG_PATH` 移到 `LOG_BAK`,B 检查时 `LOG_PATH` 已不存在(`FileNotFoundError`),被 try/except 兜住、跳过 rotate;接下来 A 和 B 都 append 到新建的 `LOG_PATH`,正确无丢失。**最坏情况**:B 在 A rename 后 / A 新建 current 前 append → append 自动创建新 current 文件(`"a"` 模式语义),依然正确。
- `os.makedirs(..., exist_ok=True)` 并发安全。
- 全段总开销 ≤ 1ms,不显著拖慢 hook 热路径。

## 守门与逃逸口

```python
def _hook_log(ev, tool, sid, skill, argv, rc, err):
    if ev not in HERMES_EVENTS:
        return                                    # Claude/Codex 不落
    if os.environ.get("TF_HOOK_DEBUG") == "0":
        return                                    # 用户显式关闭
    try:
        _ensure_log_dir()
        _rotate_if_needed()
        record = {
            "ts": _utcnow_iso(),
            "ev": ev,
            "tool": (str(tool) if tool else "")[:32],
            "sid": (str(sid) if sid else "")[:8],
            "skill": (str(skill) if skill else "")[:64],
            "argv_tail": (" ".join(map(str, argv)))[-80:],
            "rc": int(rc) if rc is not None else -1,
            "err": (err or "")[:80],
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 诊断日志 must never break the hook
```

## 与 harden-codex-skill-hook-payload 的代码共存

[harden-codex-skill-hook-payload](../harden-codex-skill-hook-payload/proposal.md) 实施后,`tf_hook.py.main()` 会在 stdin 解析后立即写 `~/.tranfu/logs/hook-payload.jsonl`(仅当 `TF_DEBUG_HOOK=1`)。本变更的 `_hook_log()` 在 `_run_report()` 内部、resolve 之后调用——**两个写入点完全独立**:

- 调用顺序:`main` → `_hook_log_payload_dump`(他) → `resolve` → `_run_report` → `_hook_log`(我们) → return。
- 写入文件:`hook-payload.jsonl`(他,raw dump) vs `hermes-hook.ndjson`(我们,结构化摘要)。
- 守门条件:`TF_DEBUG_HOOK=1`(他) vs `ev ∈ HERMES_EVENTS and TF_HOOK_DEBUG != "0"`(我们)。
- 故障域:他失败不影响我们,我们失败不影响他;都失败也不影响 `tf_report.py` 的调用。

谁先归档:把 ingest 域 / onboarding 域分别拿到的诊断条款落到 `openspec/specs/`,后者按 openspec/changes/AGENTS.md 的合并约定接住基线。

## 已知边界(默认决策,可推翻)

- **日志只写 Hermes 事件**——Claude/Codex 漏采时本地仍无结构化痕迹。如果未来 Claude/Codex 也要,扩 `_hook_log()` 守门集合即可,**不需要本变更预留**。
- **`sid` 只取前 8 字符**——若两个 Hermes session 巧合前 8 字符相同,日志层无法区分。极小概率,接受;真要分,加 ADR 改字段长度即可。
- **`err` 只截 80 字符**——长 stderr(如 python traceback)会被截。`tf_report.py` 现状 stderr 通常很短(只在网络异常输出一行)。够用。
- **`TF_HOOK_DEBUG=0` 才关**——默认开,等于一旦装机就开始写。可接受:Hermes 一天事件数百条 × 150B ≈ 几十 KB,远低于 5MB rotate 阈;用户也可设 `TF_HOOK_DEBUG=0` 关闭。
- **路径硬编码 `~/.tranfu/logs/hermes-hook.ndjson`**——不暴露 `TF_HOOK_LOG_PATH` 之类的环境变量。理由:路径稳定才好排查;真要变,改 `LOG_PATH` 常量比加环境变量更明确。
- **不主动清理 `.1` 文件**——卸载时由 `install.sh --uninstall`(如有)统一清。`.1` 保留有助于复盘上一周期的事件。
- **`subprocess.run(stderr=PIPE)` 改动的副作用**——`tf_report.py` 现状 stderr 几乎不输出;就算输出,会被 hook 进程吸进内存(单次 ≤ 几 KB),不会回流到 Hermes。无副作用。

## 验证计划(实现后据此填结果)

1. **单元**:见 tasks.md 第 2 步的 8 类测试用例。
2. **解析手验**:构造每类 Hermes payload 喂 `tf_hook.py` stdin,断言 `~/.tranfu/logs/hermes-hook.ndjson` 出对应行。
3. **轮转手验**:`dd if=/dev/zero of=~/.tranfu/logs/hermes-hook.ndjson bs=1M count=6` → 下一次 hook 触发 → 断言出现 `.ndjson.1` 且 current 文件大小 < 5MB。
4. **端到端手验**:真机 Hermes 触发 skill_view → 本地 ndjson 出对应行(含 `skill`)→ 远端 `tf.db.skill_uses` 出对应行 → 形成端到端诊断闭环。
5. **回归**:Claude/Codex 既有用例(`Skill` 工具、`scan_codex_skills`)不破。
