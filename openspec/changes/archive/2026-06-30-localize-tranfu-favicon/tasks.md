# 任务:localize-tranfu-favicon

- [x] 1. 新增 `tranfu.com` 同款版本化 favicon / apple-touch / android icon 文件到 `frontend/public/`。
- [x] 2. 更新 `frontend/index.html`:使用本地根绝对路径的版本化 favicon 链路,移除 SVG favicon 声明。
- [x] 3. 更新 `frontend/public/manifest.json`:icons 改为版本化本地路径,保留 TRANFU//AGENTS 自己的文案和 theme。
- [x] 4. 更新 `server/routes/onboarding.py`:版本化根静态文件支持 GET/HEAD。
- [x] 5. 更新 `tests/test_onboarding.py`:覆盖版本化根静态资源 MIME 与 HEAD 行为。
- [x] 6. 同步 `AGENTS.md` 与 spec-delta 中网站 head/根静态资源约定(归档时再合并 specs 事实源)。
- [x] 7. 验证:`python -m py_compile server/*.py server/routes/*.py`。
- [x] 8. 验证:`python -m pytest tests/test_onboarding.py`。
- [x] 9. 验证:`npm --prefix frontend run build`。
