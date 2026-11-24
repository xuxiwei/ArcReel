# 目录结构（方便管理）

## 推荐总览

```text
d:/work/
├── ArcReelList/                          # 工作台工作区（目标：自有 fork）
│   ├── docs/saas/                        # ★ 计划与进度（本目录）— 管理入口
│   ├── saas/                             # ★ 运行时薄适配代码（少改上游）
│   │   ├── adapter/                      # mode / auth / credits / keys 客户端
│   │   ├── isolation/                    # 路径与 OSS 前缀
│   │   ├── patches/                      # 上游补丁说明（尽量空）
│   │   └── PATCH_BUDGET.md               # 允许改的上游白名单
│   ├── frontend/ server/ lib/ ...        # 上游树，尽量原样跟
│   └── SAAS.md                           # 根入口跳转到 docs/saas
│
└── arcreel-control-plane/                # 控制面私有仓
    ├── control_plane/db/                 # ORM
    ├── alembic/                          # 迁移
    ├── api/                              # 路由占位 → 实现时放包内或此处
    ├── web/                              # 管理后台
    ├── deploy/                           # Compose + .env.example
    └── docs/                             # SCHEMA / 契约；与 docs/saas 互链
```

## 职责划分

| 放哪里 | 放什么 |
| --- | --- |
| `docs/saas/` | 计划、决策、进度、续跑说明（给人 / Agent 读） |
| `saas/` | 将来真正 import 的适配代码 |
| `arcreel-control-plane/` | 账号、积分、Key、管理、库 |
| 上游核心 `lib/` `server/` | 只做白名单内「一行挂钩」，细节进 `saas/` |

## 你可自行调整的部分

若要改目录名或合并仓，先改本文件与 [RESUME.md](RESUME.md) 中的路径表，再改代码引用。常见可选调整：

1. 把 `ArcReelList` 重命名/克隆为 `arcreel-workbench`（与文档一致）  
2. 控制面 `api/` 占位与 `control_plane/` 包合并为单一 Python 包（实现 API 时再收）  
3. 把 `docs/saas` 软链到控制面 `docs/workbench-plan`（可选，非必须）  

## 已从 `saas/docs/` 迁出

原 `saas/docs/LAYOUT.md`、`UPSTREAM_SYNC.md` 以本目录与 [UPSTREAM.md](UPSTREAM.md) 为准；`saas/docs/` 仅保留跳转，避免两处维护。
