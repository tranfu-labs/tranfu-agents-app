# board spec delta: fix-skills-rank-layout

## MODIFIED Requirements

### Requirement: SKILLS overview main analysis layout
`/skills` 主分析区在短窗口桌面布局下 MUST 保持排行 Bar/操作员排行与每日使用趋势图左右并列，并且两张同排卡片的外框底边必须视觉对齐。

#### Scenario: 7d desktop rank and trend cards align
- **WHEN** 浏览器视口为 `1440x900`
- **AND** 用户打开 `/skills?w=7d`
- **AND** 使用排行与每日使用趋势图均已加载完成
- **THEN** `.skills-rank-panel` 与 `.skills-trend-panel` 的 `getBoundingClientRect().bottom` 差值 MUST `<= 4px`

### Requirement: SKILLS rank names are readable and resilient
`/skills` 使用排行中的长 skill 名 MUST 在常见桌面宽度默认可读，并在窄屏下不得导致根级横滚、元素重叠或摘要行破版。

#### Scenario: desktop top skill name is readable without hover
- **WHEN** 使用固定 fixture 让 `openspec-driven-development` 成为 `/api/skills?w=7d` 榜首
- **AND** 浏览器视口为 `1440x900`
- **AND** 用户打开 `/skills?w=7d`
- **THEN** 排行首行默认可见文本 MUST 完整包含 `openspec-driven-development`
- **AND** 完整可读性 MUST NOT 只依赖 `title` 或 `aria-label`

#### Scenario: narrow screen rank row does not overlap
- **WHEN** 使用同一 fixture 打开 `/skills`
- **AND** 浏览器视口为 `375x812`
- **THEN** `document.scrollingElement.scrollWidth` MUST `<= document.scrollingElement.clientWidth`
- **AND** 排行首行名称、数值、记录动作与条形轨道的 bounding boxes MUST NOT incoherently overlap
- **AND** 如果可见文本被截断，完整名称 MUST 可通过 `title`、`aria-label` 或行详情读到

#### Scenario: extreme unbroken skill name remains bounded
- **WHEN** 榜首 skill 名为 `openspec-driven-development-with-extra-long-suffix-0123456789`
- **AND** 浏览器视口为 `375x812` 或 `600px` 宽
- **THEN** 页面根 MUST NOT 横向滚动
- **AND** 排行首行关键元素 MUST NOT 重叠
- **AND** 完整名称 MUST 有可读路径

#### Scenario: breakpoint and operator regressions are guarded
- **WHEN** 用户分别在 `1081x800` 与 `1080x800` 打开 `/skills?w=7d`
- **THEN** `1081px` MUST 使用桌面短窗口左右布局且不溢出
- **AND** `1080px` MUST 降级为单列且不得保留造成空白或横滚的等高副作用
- **WHEN** 用户打开 `/skills?view=operator&w=7d`
- **THEN** 操作员排行与每日使用趋势图 MUST 正常渲染，排行行点击/键盘下钻不得被本次等高样式破坏
