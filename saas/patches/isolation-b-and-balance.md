# 补丁说明：隔离 B + 顶栏余额

## 上游触点

- `lib/project/project_manager.py` — `get_project_manager()` 委托 `saas.isolation`
- `lib/infra/data_root_layout.py` — `for_project_dir` 兼容 `projects/org/<org>/…`
- `lib/material/formal_objects.py` / `lib/object_storage/relay.py` — 对象 key 加 org/user 前缀
- `server/routers/auth.py` — `GET /me/wallet` 代理控制面 `/v1/me`
- `frontend/.../GlobalHeader.tsx` / `LobbyHeader.tsx` — 顶栏积分徽章

## `saas/isolation/`

- `paths.py` — `TenantDataRootLayout`
- `project_scope.py` — 按 org 缓存 ProjectManager
- `object_keys.py` — OSS 前缀

## 原因

不同账号共享同一工作台进程时，项目目录与对象 key 必须按组织切开；余额展示走控制面真相源，不写进工作台账本。
