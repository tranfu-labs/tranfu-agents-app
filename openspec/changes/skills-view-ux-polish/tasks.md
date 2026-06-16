# 任务:skills-view-ux-polish

- [x] 1. `frontend/` 操作员详情 ⑨ 区左右对调 + skill 排行(问题 1+3)。
      `OperatorDetail.tsx`:`.dist` → 新 `.dist-mirror`(左 RUNTIME 窄 / 右 skill 排行宽);
      右栏标题改「使用 Skill 排行」(新 i18n key);渲染前按 `sessions_7d desc`(平手累计、名称)重排 `data.skills`。
      `styles.css`:`.dist-mirror{grid-template-columns:360px minmax(0,1fr)}`,≤1080px 单列。
- [x] 2. `frontend/` 视角切换独立卡片(问题 2)。
      `Skills.tsx`:`ViewSwitch` 移出统计卡,独立标准 `frame` 置顶,标题栏 `cnt` 放随视角说明文案(新 i18n key),
      内容行放 32px 高品牌色分段按钮;切视角逻辑/时间窗不重置不变。`styles.css`:`.viewcard` + `.viewbody .seg`。
- [x] 3. `frontend/` 最近记录显示到秒(问题 4)。
      `utils.ts` 新增 `fmtTs(iso)`;`OperatorDetail.tsx` / `SkillDetail.tsx` 最近记录首列改
      `fmtTs(record.first_seen) || record.day`。
- [x] 4. `frontend/` 表格整行可点 + 局部优先(问题 5)。
      `Skills.tsx`(SkillsTable / OperatorTable)、`OperatorDetail.tsx`(skill 排行表):`useNavigate` + `<tr onClick>`
      跳转(透传 `location.search`),内层 `<Link>` 降级为 `<b>`,`role="link"`/`tabIndex`/Enter·Space 键盘可达;
      表头排序 `stopPropagation`。`styles.css`:修正 `.skills-wrap tbody tr` 指针态、"最近记录"表设 `cursor:default`。
- [x] 5. 端到端手验:本地起服务造多 operator + 跨 runtime + OpenClaw equipped 数据。
      ⑨ 区左 runtime 右 skill 排行、默认 7 天降序;视角卡片标准标题栏 + 32px 分段按钮整页换主语 + 说明随视角变;
      两详情页最近记录到秒、缺 first_seen 回退到日期;四张下钻表整行可点(含键盘)、表头排序不误跳、
      双向下钻闭环仍在;"最近记录"表不可点(指针 default)。暗/亮主题 + ≤600px 走查;
      `npm --prefix frontend run build` 通过。
- [x] 6. 文档:spec delta 合入 `openspec/specs/board/spec.md`;归档本 change 留待上线后执行。
