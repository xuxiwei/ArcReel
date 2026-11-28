# 补丁预算（相对 upstream）

目标：相对 `upstream/main`，**非 `saas/` 路径**的长期改动控制在很少文件（理想个位数）。

## 允许触点白名单（将来挂钩时用）

| 上游区域 | 允许改法 | 状态 |
| --- | --- | --- |
| `server/auth.py` | 一处分支调用 `saas.adapter` 鉴权；`CurrentUserInfo.org_id` | 已改 |
| `server/routers/auth.py` | SaaS 登录/注册转发或代理；`/auth/status` 暴露 `deployment_mode` | 已改 |
| `frontend/src/components/pages/LoginPage.tsx` | SaaS 注册入口薄封装 | 已改 |
| `frontend/src/i18n/*/auth.ts` | 注册文案 | 已改 |
| `.env.example` / `deploy/.env.example` | `DEPLOYMENT_MODE`、控制面 URL/密钥 | 已改 |
| `lib/generation/generation_queue.py` | 入队戳记 `_saas.org_id` | 已改 |
| `lib/generation/generation_worker.py` | 执行时恢复 billing context | 已改 |
| `lib/billing/ledger.py` | 计费括号旁路 hold/settle/release | 已改 |
| `lib/config/resolver.py` | SaaS 叠加平台 Key | 已改 |
| `server/routers/providers.py` | SaaS 禁止 BYOK；平台 Key 配好的供应商显示为就绪 | 已改 |
| `lib/config/service.py` | SaaS：平台 Key 配好的供应商算作 ready（可选模型、默认模型才看得到） | 已改 |
| `server/agent_runtime/options_assembler.py` | Agent 平台 Key | 已改 |
| `frontend/.../CredentialList.tsx` | SaaS 隐藏添加密钥 | 已改 |
| `lib/project/project_manager.py` | SaaS 委托 org 隔离 ProjectManager | 已改 |
| `lib/infra/data_root_layout.py` | `for_project_dir` 兼容 org 嵌套 | 已改 |
| `lib/material/formal_objects.py` | OSS formal key 加 org/user 前缀 | 已改 |
| `lib/object_storage/relay.py` | OSS relay key 加 org/user 前缀 | 已改 |
| `server/routers/auth.py` | `GET /me/wallet` | 已改 |
| `frontend/.../GlobalHeader.tsx` / `LobbyHeader.tsx` | 顶栏余额 | 已改 |
| `server/routers/projects.py` | 列表过滤（改由路径隔离覆盖） | 无需改 |
| `server/agent_runtime/session_manager.py` | SaaS：组织隔离 cwd（WB-09）；每条消息送达前预扣、轮次结束按实际费用结算；按会话用户而非默认用户运行；单用户会话上限 + 平台默认上限 20 | 已改 |
| `server/agent_runtime/arcreel_mcp.py` | SaaS：MCP 走组织 ProjectManager，无身份拒绝（WB-10） | 已改 |
| `server/auth.py` | SaaS：识别 `embedded_agent` 令牌映射为 `EMBEDDED_AGENT_SUB` | 已改 |
| `lib/db/repositories/task_repo.py` | SaaS：`claim_next` 按用户公平调度 + 单用户在跑上限（`SAAS_TASKS_RUNNING_PER_USER`） | 已改 |
| `server/agent_runtime/agent_access_policy.py` | SaaS：Bash 密钥剥离扩展到控制面/数据库密钥；`denyRead` 追加他人项目、其他会话 SDK 记录与 `ARCREEL_AGENT_DENY_READ`（逻辑在 `saas/isolation/agent_sandbox.py`） | 已改 |
| `server/agent_runtime/options_assembler.py` | SaaS：CLI 子进程 env 置空多租户密钥 | 已改 |
| `lib/db/engine.py` | SaaS：`get_database_url` 在 `DATABASE_URL` 被移出进程环境后从 `saas.adapter.secret_env` 取 | 已改 |
| `server/app.py` | SaaS：启动完成后 `seal_secret_env()`，此后子进程不再继承密钥 | 已改 |
| `server/app.py` | SaaS：实例级路由挂 `SAAS_ADMIN_ONLY` / `SAAS_ADMIN_WRITES`（平台管理员 = 控制面 `users.is_admin`；逻辑在 `saas/isolation/admin_guard.py`，自托管无操作） | 已改 |
| `lib/object_storage/client.py` | SaaS：`kind` 支持 `oss`，`create_sdk_client` 转到 `saas/storage/aliyun_oss.py` | 已改 |
| `server/routers/object_storage.py` | SaaS：`kind` 为 `tos`/`oss`，未传时按 Endpoint 推断（`*.aliyuncs.com` → oss） | 已改 |
| `pyproject.toml` | SaaS：依赖 `oss2` | 已改 |
| `lib/material/formal_objects.py` | SaaS：`stores_remotely` 含视频/音频；`store` 对视频/音频流式摘要与上传（逻辑在 `saas/storage/media_offload.py`） | 已改 |
| `lib/object_storage/client.py` | SaaS：`put_file_sync` 流式上传 | 已改 |
| `server/services/tasks/generation_tasks.py` | SaaS：视频/参考视频/TTS/试听任务包 `formal_commit` | 已改 |
| `lib/material/work_files.py` | SaaS：闲置清理保留视频/音频本地工作文件 | 已改 |
| `lib/project/project_manager.py` | SaaS：新建 / 生成项目名时跨组织唯一（`saas/isolation/project_names.py`） | 已改 |
| `lib/project/deleted_projects.py` | SaaS：恢复已删除项目时避开他组织同名 | 已改 |
| `server/services/project/project_archive.py` | SaaS：导入与他组织同名时改名 | 已改 |
| `server/app.py` | SaaS：启动 / 停止项目文件镜像（`saas/storage/project_mirror.py`） | 已改 |
| `lib/object_storage/client.py` | SaaS：`delete_sync` | 已改 |
| `server/auth.py` | SaaS：`get_current_user` 刷新媒体 Cookie（`saas/isolation/media_access.py`） | 已改 |
| `server/routers/files.py` | SaaS：媒体按 Cookie 所属组织读取；已在 OSS 的媒体 302 到签名地址（`saas/storage/media_redirect.py`） | 已改 |
| `server/auth.py` | SaaS：`create_download_token` 带签发者组织（`saas/isolation/download_identity.py`） | 已改 |
| `server/app.py` | SaaS：导出 / 剪映下载路由挂 `bind_download_identity` | 已改 |
| `lib/material/maintenance.py` | SaaS：每小时维护按组织目录执行（`saas/isolation/maintenance_scope.py`） | 已改 |
| `server/routers/object_storage.py` | SaaS：有任务排队/执行时禁止换桶或删除连接（`saas/isolation/connection_guard.py`） | 已改 |
| `lib/i18n/*/errors.py` | SaaS：`object_storage_tasks_running` 文案 | 已改 |
| `server/routers/auth.py` | SaaS：登录/注册下发媒体 Cookie；`POST /auth/logout` 清除 | 已改 |
| `frontend/src/stores/auth-store.ts` | SaaS：退出登录时调用 `/auth/logout` | 已改 |
| `server/routers/auth.py` | SaaS：`/me/wallet` 返回 `is_admin` | 已改 |
| `frontend/src/components/pages/SystemConfigPage.tsx` | SaaS：成员只显示个人设置分区（`stores/saas-role-store.ts`） | 已改 |
| `frontend/src/components/layout/GlobalHeader.tsx` / `pages/lobby/LobbyHeader.tsx` | SaaS：成员隐藏资产库、外部 Agent、费用入口与配置红点 | 已改 |
| `frontend/src/components/pages/AssetLibraryPage.tsx` | SaaS：成员跳回项目列表 | 已改 |
| `frontend/src/api.ts` | `getMeWallet` 类型加 `is_admin` | 已改 |
| `lib/db/repositories/usage_repo.py` | SaaS：`_scope_query` 让成员只读自己的调用记录（`saas/isolation/usage_scope.py`） | 已改 |
| `lib/db/models/asset.py` + `alembic/versions/5a1e0c7d9b42_*` | SaaS：`assets.org_id`，名称组织内唯一 | 已改 |
| `lib/db/repositories/asset_repo.py` | SaaS：资产库按组织读写（`saas/isolation/asset_scope.py`） | 已改 |
| `server/routers/files.py` | SaaS：全局资产文件只给本组织 | 已改 |
| `server/app.py` | SaaS：费用统计改用 `SAAS_USAGE_SCOPE`；资产库对成员开放；挂对账代理路由 | 已改 |
| `frontend/src/components/pages/settings/ReconciliationSection.tsx` 等 | SaaS：管理员对账页面；对象存储文案支持阿里云 OSS | 已改 |
| `server/routers/auth.py` + `frontend/src/components/pages/LoginPage.tsx` + `frontend/src/i18n/*/auth.ts` | SaaS：注册表单加邀请码并转发控制面；注册关闭/邀请码无效的中文提示 | 已改 |
| `frontend/src/components/pages/SystemConfigPage.tsx` + `stores/saas-role-store.ts` + `i18n/*/dashboard.ts` | SaaS：已搬到控制面后台的设置分区在工作台隐藏（`patches/settings-to-console.md`） | 已改 |
| `server/app.py` | SaaS：挂 `saas/adapter/routes_admin_workbench.py`（跨组织资产、用户活动） | 已改 |
| `frontend/src/onboarding/OnboardingTour.tsx` | SaaS：成员的新手引导跳过供应商、ArcReel Agent 两步（`patches/legacy-assets-and-onboarding.md`） | 已改 |

## 禁止

- 在 `lib/billing` 内实现用户积分账本（积分真相在控制面）
- 大面积改写 Agent / 供应商核心以「塞进」多租户
- 无说明的上游文件修改

每新增一处上游 diff，在本表追加一行并在 `patches/` 写原因。
