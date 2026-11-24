# 控制面 ↔ 工作台契约（MVP）

前缀 `/v1`。实现后以控制面 OpenAPI 为准；本文为约定草稿。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/v1/auth/register` | 开放注册；个人组织；余额 0；返回 JWT（已实现） |
| POST | `/v1/auth/login` | JWT：`user_id` + `org_id`（已实现） |
| GET | `/v1/me` | 用户、组织、余额（已实现） |
| POST | `/v1/credits/hold` | 预留；不足 402（已实现） |
| POST | `/v1/credits/settle` | 实扣 + 成本引用（已实现） |
| POST | `/v1/credits/release` | 失败/取消释放（已实现） |
| POST | `/v1/admin/credits/grant` | 人工充值（可按汇率）（已实现） |
| GET/PUT | `/v1/admin/config/*` | Key、汇率、系数（已实现） |
| GET | `/v1/admin/ledger` | 流水对账（已实现） |
| GET | `/v1/internal/platform-keys` | 工作台拉平台 Key（已实现） |
| POST | `/v1/internal/credits/hold\|settle\|release` | 工作台 Worker 扣费（已实现） |
| GET | `/v1/internal/config/{key}` | 工作台读系数等（已实现） |

控制面侧副本：`d:/work/ArcReelControl/arcreel-control-plane/docs/API_CONTRACT.md`（保持同步修改）。
