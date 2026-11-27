# 前端对普通成员隐藏管理员页面

后端已对实例级路由加了平台管理员守卫（`admin-guard.md`），成员打开这些页面只会看到 403。

- `server/routers/auth.py` `GET /me/wallet`：多返回 `is_admin`（控制面 `users.is_admin`；内嵌 Agent 恒为 false）。
- `frontend/src/stores/saas-role-store.ts`（新）：`useIsRestrictedMember()`，SaaS 且非管理员时为真；自托管或拿不到部署模式时不隐藏任何东西；
  SaaS 下拿不到身份时按成员处理。换账号登录会重新读取。
- `SystemConfigPage.tsx`：成员只看到 Agent 记忆、通用、提示词模版、关于；地址里指定了其他分区时落到「通用」。
- `GlobalHeader.tsx` / `LobbyHeader.tsx`：成员不显示全局资产库、外部 Agent、项目费用入口，也不显示“配置不完整”红点（平台配置由管理员负责）。
- `AssetLibraryPage.tsx`：成员直接打开时跳回项目列表。

已知：新手引导里指向“供应商”设置的步骤对成员没有目标元素；成员一般不需要这一步。
