# 实例级设置仅平台管理员可改（admin guard）

## 问题

上游是单用户：能登录的人就是实例所有者，所以对象存储、Agent 凭据、自定义供应商/端点、
系统日志、全局资产库、费用统计等路由只要求「已登录」。SaaS 下每个注册用户都是租户，
任何人都能改平台的对象存储配置、读取供应商凭据、看所有人的费用记录。

## 改法

`saas/isolation/admin_guard.py` 提供两个依赖，`server/app.py` 挂到实例级路由上：

| 守卫 | 路由 | 规则 |
| --- | --- | --- |
| `SAAS_ADMIN_ONLY` | usage、object_storage、asset_library、system、api_keys、agent_config、custom_endpoints、market_submissions、official_service、assets | 所有方法都要平台管理员 |
| `SAAS_ADMIN_WRITES` | providers、provider_models、catalog、system_config、market、custom_providers | 读开放（模型选择器等要用）；写、`/credentials` 与 `/providers/{id}/config` 读要平台管理员；`POST /system/config/recommendation-changes/acknowledge` 例外 |

- 平台管理员 = 控制面 `GET /v1/me` 的 `user.is_admin`，用调用者自己的令牌查询，缓存 60 秒（撤销管理员最多 60 秒生效）。
- 内嵌 Agent 令牌（`EMBEDDED_AGENT_SUB`）永远不是管理员。
- 控制面不可达 → 503，不会放行。
- 自托管模式全部无操作。

## 已知后续

- 费用统计（usage）尚未按用户过滤，暂时整体只给管理员；之后改成成员看自己的、管理员看全部。
- 全局资产库（assets）尚未按组织隔离，同上。
- 前端还没隐藏这些页面：成员打开会看到 403。之后在 `/auth/status` 或 `/me` 暴露 `is_admin` 并隐藏入口。

测试：`tests/unit/saas/test_admin_guard.py`。
