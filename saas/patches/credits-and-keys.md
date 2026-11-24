# 补丁说明：扣费钩子 + 平台 Key 注入

## 改动文件（上游触点）

- `lib/billing/ledger.py` — `record` / resume / agent turn 旁路 hold·settle·release
- `lib/config/resolver.py` — 解析供应商配置后叠加平台 Key
- `lib/generation/generation_queue.py` — 入队时把 `org_id` 戳进 payload
- `lib/generation/generation_worker.py` — 执行任务时恢复 billing context
- `server/auth.py` — 鉴权成功后写入 billing ContextVar
- `server/routers/providers.py` — SaaS 禁止 BYOK 增删改/激活
- `server/agent_runtime/options_assembler.py` — Agent ANTHROPIC_* 走平台 Key
- `frontend/.../CredentialList.tsx` — SaaS 隐藏「添加密钥」

## `saas/adapter/` 新增

- `billing_context.py` / `credits_hook.py` / `platform_keys.py`
- `control_plane_client.py` 扩展 internal credits / keys / config

## 控制面

- `POST /v1/internal/credits/{hold,settle,release}`（`X-Internal-Token`）
- `GET /v1/internal/config/{key}`

## 原因

生成在 Worker 异步执行，无法依赖请求态用户 JWT；用内部令牌 + 入队时戳记的 `org_id` 完成 hold/settle。平台 Key 与积分真相都在控制面，工作台只做薄挂钩。
