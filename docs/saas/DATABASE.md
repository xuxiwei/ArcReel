# 控制面数据库

实现仓：`d:/work/arcreel-control-plane`  
详细 ER：该仓 [`docs/SCHEMA.md`](file:///d:/work/arcreel-control-plane/docs/SCHEMA.md)（若 IDE 打不开，直接打开该路径）。

## 表

| 表 | 用途 |
| --- | --- |
| `users` | 开放注册账号 |
| `organizations` | 个人组织 |
| `memberships` | 用户↔组织（MVP 仅 owner） |
| `wallets` | balance / held |
| `credit_holds` | 按 call 预留（进行中 `call_id` 部分唯一） |
| `credit_ledger` | 积分流水 + 对账字段 |
| `platform_credentials` | 平台 Key |
| `app_config` | 汇率与系数 |

## 种子

- `cny_yuan_to_credits` = `10` → 10 元 = 100 积分  
- `cost_to_credits_multiplier` = `1.0`  

## 起库（开发期推荐直接跑 SQL）

建表脚本（含中文注释 + 种子）：控制面仓 `arcreel-control-plane/db/schema.sql`

```powershell
cd d:\work\ArcReelControl\arcreel-control-plane
$env:PGHOST = "你的主机"
$env:PGPORT = "5432"
$env:PGUSER = "你的用户"
$env:PGDATABASE = "arcreel_control"
$env:PGPASSWORD = "从密钥管理读取"
psql -f db\schema.sql
```

可选本机 Compose + Alembic：

```powershell
cd d:\work\ArcReelControl\arcreel-control-plane
docker compose -f deploy/docker-compose.yml up -d postgres
# uv 若未在 PATH：%USERPROFILE%\.local\bin\uv.exe
uv sync
# DATABASE_URL 用环境变量配置，见 deploy/.env.example
uv run alembic upgrade head
```

默认本机 Compose 端口见 `deploy/docker-compose.yml`（映射 `5433`）。

## 代码位置

- ORM：`control_plane/db/models/`  
- 迁移：`alembic/versions/20260323_0001_initial_schema.py`  
