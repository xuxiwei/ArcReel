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
| `server/routers/providers.py` | SaaS 禁止 BYOK | 已改 |
| `server/agent_runtime/options_assembler.py` | Agent 平台 Key | 已改 |
| `frontend/.../CredentialList.tsx` | SaaS 隐藏添加密钥 | 已改 |
| `lib/project/project_manager.py` | SaaS 委托 org 隔离 ProjectManager | 已改 |
| `lib/infra/data_root_layout.py` | `for_project_dir` 兼容 org 嵌套 | 已改 |
| `lib/material/formal_objects.py` | OSS formal key 加 org/user 前缀 | 已改 |
| `lib/object_storage/relay.py` | OSS relay key 加 org/user 前缀 | 已改 |
| `server/routers/auth.py` | `GET /me/wallet` | 已改 |
| `frontend/.../GlobalHeader.tsx` / `LobbyHeader.tsx` | 顶栏余额 | 已改 |
| `server/routers/projects.py` | 列表过滤（改由路径隔离覆盖） | 无需改 |

## 禁止

- 在 `lib/billing` 内实现用户积分账本（积分真相在控制面）
- 大面积改写 Agent / 供应商核心以「塞进」多租户
- 无说明的上游文件修改

每新增一处上游 diff，在本表追加一行并在 `patches/` 写原因。
