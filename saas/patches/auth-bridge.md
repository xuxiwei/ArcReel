# 补丁说明：鉴权桥

## 改动文件

- `server/auth.py` — SaaS 分支校验控制面 JWT；`CurrentUserInfo` 增加 `org_id`
- `server/routers/auth.py` — SaaS 代理 login/register；status 返回 `deployment_mode`
- `frontend/.../LoginPage.tsx` + i18n — SaaS 时展示注册入口
- `.env.example` / `deploy/.env.example` — 文档化桥接变量

## 原因

工作台前端仍只打同源 `/api/v1/auth/*`；SaaS 模式下由服务端转发控制面并验其 JWT，避免大面积改前端传输层。
