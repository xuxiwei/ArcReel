# 登录令牌改公私钥 + 主进程密钥封存（2026-11）

## 为什么

原来控制面和工作台共用一个 HS256 密钥：工作台（跑着 Agent，攻击面最大）一旦被拿下，
就能给任何用户、包括平台管理员签发令牌。另外工作台启动时把 `.env` 载入进程环境，
之后启动的每个子进程（ffmpeg、Agent CLI、技能脚本）都会继承控制面令牌、数据库密码等，
同一系统用户可读 `/proc/<pid>/environ`。

## 改动

| 位置 | 内容 |
| --- | --- |
| 控制面 `security/jwt.py`、`settings.py` | 配置 `JWT_PRIVATE_KEY_PATH` 时用 Ed25519（EdDSA）签发与校验；否则沿用 HS256。只接受当前模式的算法 |
| `saas/adapter/auth_bridge.py` | 配置 `CONTROL_PLANE_JWT_PUBLIC_KEY_PATH` 时只用公钥验签（拒绝 HS256）；拒绝带 `embedded_agent` 的控制面令牌 |
| 同上 | Agent 回调令牌改由工作台自己签发：由工作台令牌密钥派生的独立 HMAC 键、独立 issuer/audience，控制面验不了也不接受 |
| `saas/adapter/secret_env.py` + `server/app.py` | 启动完成后把密钥类变量从 `os.environ` 移入进程内存；SaaS 代码经 `secret_env.get` 读取 |
| `lib/db/engine.py` | `get_database_url` 在环境里没有 `DATABASE_URL` 时回退到封存值 |

## 部署

`arcreelctl.sh gen-jwt-keys` 生成密钥对；控制面 `.env` 设 `JWT_PRIVATE_KEY_PATH`，工作台 `.env` 设
`CONTROL_PLANE_JWT_PUBLIC_KEY_PATH` 并删除 `CONTROL_PLANE_JWT_SECRET`。切换后旧令牌失效，用户重新登录。

## 已知边界

- 私钥文件目前对运行用户 `arcreel` 可读（两个服务同一用户）。要让工作台进程本身也读不到私钥，
  需把控制面改为独立系统用户（`deploy` 待办）。Agent 的 Bash 已通过 `ARCREEL_AGENT_DENY_READ` 禁读 `/etc/arcreel`。
- 封存只针对启动之后：启动阶段（迁移等）启动的子进程仍会继承完整环境。
