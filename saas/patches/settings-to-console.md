# 平台设置搬到控制面管理后台（第一批）

SaaS 下，下面这些只给平台管理员用的设置分区从工作台“设置”里隐藏，改在控制面管理后台（`arcreel-control-plane/web`）维护：

| 工作台分区 | 后台页面 | 后台调用的工作台接口 |
| --- | --- | --- |
| 素材库与存储 · 对象存储 | 系统 → 对象存储 | `/api/v1/object-storage/*` |
| 素材库与存储 · 素材库账号 / 推理凭证绑定 | 系统 → 供应商素材库 | `/api/v1/asset-library/*` |
| 外部 Agent、访问令牌 | 系统 → 外部 Agent 与令牌 | `/api/v1/api-keys` |
| 每日对账 | 财务 → 每日对账 | 直接调控制面 |
| （新增）费用统计（全部用户） | 财务 → 费用统计 | `/api/v1/usage/*` |
| （新增）跨组织资产库 | 内容 → 资产库 | `/api/v1/saas/admin/assets` |
| （新增）用户在工作台的项目与调用 | 用户详情 | `/api/v1/saas/admin/users/{id}/activity` |

后台用同一个登录令牌直接调工作台接口，配置只有一份。

工作台改动：

- `frontend/src/components/pages/SystemConfigPage.tsx`：SaaS 下隐藏 `MOVED_TO_CONSOLE` 里的分区；管理员看到一条提示，设了 `VITE_ADMIN_CONSOLE_URL` 时附“打开管理后台”链接。
- `frontend/src/stores/saas-role-store.ts`：新增 `useIsSaas()`。
- `frontend/src/i18n/*/dashboard.ts`：`settings_moved_to_console`、`settings_open_console`。
- `saas/adapter/routes_admin_workbench.py` + `server/app.py` 挂载：跨组织资产列表与删除（删除按资产所属组织走原删除流程）、用户活动汇总；`SAAS_ADMIN_ONLY`。

还留在工作台、后续再搬：供应商、默认模型、调用端点、ArcReel Agent、市场。成员的个人设置（Agent 记忆、自己的费用、通用、提示词模板、关于）和成员用的资产库页面不变。自托管模式不受影响。
