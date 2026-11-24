# 下次从这里继续

给未来的你 / Agent：打开本文件即可续跑，不必重聊一遍。

## 1. 先读

1. [STATUS.md](STATUS.md) — 做到哪了  
2. [DECISIONS.md](DECISIONS.md) — 不要推翻已拍板项（除非用户明确改）  
3. [PLAN.md](PLAN.md) — P0 还剩什么  
4. [LAYOUT.md](LAYOUT.md) — 两个目录在哪  

## 2. 工作区路径

| 角色 | 本机路径 | 说明 |
| --- | --- | --- |
| 工作台（fork 上游） | `d:/work/ArcReelList` | 含 `saas/` 适配 + `docs/saas/` 计划 |
| 控制面（私有） | `d:/work/arcreel-control-plane` | 账号/积分/库表；已 `git init`，未绑远程 |

## 3. 环境注意

- 工作台 `origin` 当前仍可能是官方 `ArcReel/ArcReel`；SaaS 提交前应改为自己的 fork，`upstream` 指官方。  
- 控制面依赖：`uv` 在 `%USERPROFILE%\.local\bin\uv.exe`；本机曾无 **无 Docker**，Postgres 迁移未打进真实库。  
- 控制面默认库：`postgresql+asyncpg://arcreel:arcreel@127.0.0.1:5433/arcreel_control`

## 4. 建议的下一次任务（按顺序）

1. （可选）Fork + 改 remote；控制面推私有远程  
2. [x] 工作台扣费钩子 + 平台 Key 注入  
3. [x] 隔离 B + 顶栏余额  
4. [x] 联调验收 + upstream merge 演练  
5. **下一步**：工作台 fork（`origin` 切自有仓）并提交 `saas/` / 上游触点；控制面推私有远程  

对 Agent 可说：`按 docs/saas/RESUME.md 从 STATUS 下一步继续，做 fork 接线与提交。`

## 5. 不要做的事

- 不要把积分账本做进工作台 `lib/billing`（成本账保留；用户积分在控制面）  
- 不要大面积改上游核心以「塞」多租户；改动进 `saas/` + 控制面  
- 不要恢复邀请码 / 工作室 / 注册送积分（除非用户改 [DECISIONS.md](DECISIONS.md)）
