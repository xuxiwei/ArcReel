# 注册邀请码（控制面注册方式）

控制面新增注册方式 `open / invite / closed`（`app_config.registration_mode`，后台“注册与邀请码”页设置）。

工作台改动：

- `server/routers/auth.py`：`RegisterRequest` 加可选 `invite_code`，原样转发控制面 `/v1/auth/register`。
- `saas/adapter/control_plane_client.py`：`control_plane_register(..., invite_code=)`。
- `frontend/src/components/pages/LoginPage.tsx`：注册模式下多一个“邀请码”输入框（可留空）；控制面返回 403 显示“暂未开放注册”，返回含 `invite code` 的 400 显示“邀请码缺失、无效、已用完或已过期”。
- `frontend/src/i18n/{zh,en,ru,vi}/auth.ts`：四个新文案键。

自托管模式不受影响：注册接口本来就只在 SaaS 模式开放。
