# openspec — 规格与变更

- `specs/<domain>/spec.md` —— 某业务域的**当前事实规格**(必须满足的规则、场景、可验证行为)。
- `changes/<change-id>/` —— 一次需求/业务变更的工作区(proposal / design / tasks / spec delta),**先设计再实现**;
  实现并上线后,把 delta 合入对应 `specs/` 并归档该 change。

域:`ingest`(事件采集)、`board`(看板与计算)、`onboarding`(安装与接入)。
