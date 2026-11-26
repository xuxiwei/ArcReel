# 补丁说明：代码审查修复（2026-11）

对应《ArcReelControl 代码审查：BUG 与逻辑错误》中的工作台条目。

## 计费

- **#1 Agent 计费**：每条用户消息送达 CLI 前预扣（余额不足直接 402，消息不会发出）；轮次结束按写入的 `api_calls` 实际费用结算，中断/失败的轮次同样按已发生费用结算。没有预扣的轮次（排队消息开启的新轮）先开 0 预扣再结算，按余额扣到为止。
- **#2 币种换算**：积分 = 成本 × `fx_<币种>_to_cny` × `cny_yuan_to_credits` × `cost_to_credits_multiplier`。CNY 不需要汇率。换算失败（缺汇率、控制面不可用且无缓存）时按预扣额收费，绝不按 1:1 少收。
- **#3 call_id**：`api_call:<id>:<started_at>`，SQLite 复用 id 后不再撞上已结算的 call_id。旧格式（`org:<org>:api_call:<id>`、`api_call:<id>`）在 settle/release 时作为回退，兼容升级前已开的预扣。
- **#4 预扣额**：按调用类型取 `SAAS_HOLD_ESTIMATE_<TYPE>`（image/video/audio/text/agent），否则 `SAAS_HOLD_ESTIMATE_CREDITS`，默认 10；视频按每 5 秒一档放大。启动收口时释放被零费用关闭的调用的预扣，并释放上个进程遗留的 Agent 预扣。

## 隔离与身份

- **#5** Agent 以当前请求的 SaaS 用户运行：用户记忆、SDK 会话存储（按用户缓存）、MCP、用量行都按用户隔离；无身份时用户记忆段关闭。
- **#7** 无身份时对象存储 key 落到 `org/_unscoped/`，不再进共享命名空间；非法 org id 直接报错，不回落全局目录。项目目录无身份时仍回落全局根（启动恢复与旧数据依赖），首次发生会记录带调用栈的告警。
- **#10** 平台 Key 优先级修正（agent > text > image > video > tts）；拉取失败且无缓存时返回 503，不再回落本地凭证表。
- **#11** SaaS 下 Agent 回调 API 的令牌改为控制面格式、带 `embedded_agent` 标记，仍受 `reject_embedded_agent` 约束。

## 登录

- **#6** 代理登录/注册时附 `X-Forwarded-For` + `X-Internal-Token`，控制面按真实客户端 IP 限流。工作台若在反向代理后，需让 uvicorn 信任代理头（`--proxy-headers --forwarded-allow-ips=<代理 IP>`）。
- **#17** 本地用户名统一小写；**WB-08** `/auth/verify` 返回登录名。

## 需要在控制面配置

- `PUT /v1/admin/config/fx_usd_to_cny`（以及实际用到的其他币种），否则美元成本按预扣额收费。

## 容量与公平（上线规模：同时在线约 100 人，16 GB / 8 核）

- Agent 会话：每用户最多 `SAAS_AGENT_SESSIONS_PER_USER`（默认 2）个，超出先淘汰该用户最旧的空闲会话；平台上限未在设置里配置时取 `SAAS_AGENT_MAX_SESSIONS`（默认 20，约 20 × 350 MB ≈ 7 GB）。
- 生成任务：认领时在跑任务少的用户优先；单用户同时在跑最多 `SAAS_TASKS_RUNNING_PER_USER`（默认 4）个。

## 金额统一人民币

- 币种缺失按 CNY；发往控制面流水的供应商成本一律换算为 CNY（`api_calls` 保留原币种用于对账）。
- 控制面只接受 CNY 充值与 CNY 成本；`/v1/me` 返回 `balance_cny` / `held_cny` / `credits_per_cny`，顶栏按人民币显示余额。
