# 上线前小修（第 1 批）

1. **后台维护覆盖组织目录**（`lib/material/maintenance.py` → `saas/isolation/maintenance_scope.py`）：
   上游只扫 `projects/`，SaaS 项目在 `projects/org/<org>/` 下，每小时的 OSS 引用重算和闲置图片缓存清理从未执行。
   现在逐个组织目录调用上游例程；过期墓碑只有在所有组织的 `deleted_projects` 里都不存在时才撤引用。
2. **有任务时不能更换或删除对象存储连接**（`server/routers/object_storage.py` → `saas/isolation/connection_guard.py`）：
   有排队或执行中的生成任务时，换桶 / Endpoint / 区域 / 类型或删除连接返回 409 `object_storage_tasks_running`
   （四种语言文案已加）；只改访问密钥不受影响。
3. **登录即下发媒体 Cookie**（`server/routers/auth.py`）：登录、注册的响应直接带 `arcreel_media`，首屏图片不会抢在第一次 API 调用之前 401。
4. **退出登录清除媒体 Cookie**：新增公开接口 `POST /api/v1/auth/logout`（204，只清 Cookie）；前端 `auth-store.logout` 顺带调用。
   `tests/integration/server/test_auth_enforcement.py` 把它列入公开接口并断言 204。

测试：`tests/unit/saas/test_step1_fixes.py`。
