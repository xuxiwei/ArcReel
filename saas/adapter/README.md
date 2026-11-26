# `adapter/`

模式开关与控制面客户端。上游只做白名单内薄挂钩，细节放这里。

| 模块 | 作用 |
| --- | --- |
| `mode.py` | `DEPLOYMENT_MODE`（默认 `self_hosted`） |
| `auth_bridge.py` | 校验控制面 JWT（`user_id` + `org_id`） |
| `local_user.py` | 把控制面 `user_id` 幂等写入本地 `users`（满足 batches/tasks FK） |
| `control_plane_client.py` | 登录 / 注册 / me / internal credits / keys |
| `billing_context.py` | 请求与 Worker 的 `org_id` ContextVar |
| `credits_hook.py` | hold / settle / release + 成本→积分 |
| `platform_keys.py` | 拉取并缓存平台供应商密钥 |

环境变量（SaaS）：

- `DEPLOYMENT_MODE=saas`
- `CONTROL_PLANE_URL` — 例 `http://127.0.0.1:8100`
- `CONTROL_PLANE_JWT_SECRET` — 与控制面 `JWT_SIGNING_SECRET` 相同
- `CONTROL_PLANE_INTERNAL_TOKEN`（或 `CONTROL_PLANE_ADMIN_TOKEN`）— 调 internal API
- 可选：`SAAS_HOLD_ESTIMATE_CREDITS`、`SAAS_COST_TO_CREDITS_MULTIPLIER`
