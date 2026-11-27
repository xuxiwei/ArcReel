# Agent Bash 沙箱多租户加固（2026-11）

## 背景

上游的 Agent 访问策略按「一台机器一个可信用户」设计：内置 Read/Write 由 hook 严格围栏，
但 Bash 只靠内核沙箱的 denyRead 黑名单（工作台 `.env`、数据根系统条目），且上游明确
不限制 Bash 在 `projects/` 内跨项目读取。SaaS 下任何注册用户都能驱动 Agent 执行 Bash
（包括通过剧本、素材里的提示注入），黑名单之外的整台主机都可读。

## 改动

逻辑集中在 `saas/isolation/agent_sandbox.py`，上游文件只加 `is_saas()` 分支调用：

| 位置 | 作用 |
| --- | --- |
| `AgentAccessPolicy._collect_env_keys_to_scrub` | Bash 命令 `env -u` 剥离清单加入 `SECRET`/`PASSWORD`/`DATABASE_URL`/`_DSN`/`CONTROL_PLANE_` 等名字；保留 `ARCREEL_API_TOKEN`（技能脚本回调工作台用，短期且只属于本会话用户） |
| `AgentAccessPolicy.build_sandbox_settings` | `denyRead` 追加：从 `projects/` 到本项目路径上每一层的全部兄弟条目（其他组织、本组织其他项目、旧平铺项目）；SDK 会话目录里其他会话的记录与 `history.jsonl`；`ARCREEL_AGENT_DENY_READ` 列出的主机路径 |
| `OptionsAssembler` 组装 `options.env` | 上述密钥在 CLI 子进程 env 里置空，`/proc/<cli>/environ` 与所有 Bash 子进程都拿不到 |

自托管模式行为不变。

## 已知边界

- 沙箱在会话启动时编译一次：会话期间新建的目录（新租户的第一个项目）要到下个会话才进 denyRead。
- 主进程（uvicorn）环境变量仍含密钥；若沙箱未隔离 PID 命名空间，同一系统用户可读 `/proc/<pid>/environ`。部署上线前需实测（见 `deploy/README.md`「Agent 隔离自检」）。
- 根本措施在部署层：控制面以独立系统用户运行、备份仅 root 可读、PostgreSQL 本机连接要求密码。
