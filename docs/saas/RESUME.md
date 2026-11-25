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
| 工作台（fork） | `d:/work/ArcReelControl/ArcReelList` | `origin` → `xuxiwei/ArcReel`；`upstream` → 官方 |
| 控制面（私有） | `d:/work/ArcReelControl/arcreel-control-plane` | 随根仓 `xuxiwei/ArcReelControl` 推送 |

## 3. 环境注意

- 工作台：`origin=https://github.com/xuxiwei/ArcReel.git`，`upstream=https://github.com/ArcReel/ArcReel.git`  
- 控制面随 monorepo：`https://github.com/xuxiwei/ArcReelControl.git`（私有）  
- 拉上游：`git fetch upstream && git merge upstream/main`（当前 SaaS 分支 `saas/control-plane-p0`）  
- JWT 已绑 `aud=arcreel-control-plane` / `iss=arcreel-auth` / `typ=access`；工作台 `auth_bridge` 同步校验  
- 明文平台 Key 迁移：临时 `MIGRATION_ALLOW_PLAINTEXT=1`，后台重新保存后关闭  

## 4. 建议的下一次任务（按顺序）

1. [x] 工作台 fork + 推送 `saas/`；控制面私有远程  
2. [x] 上游 merge + JWT/限流/密钥 P0 安全项  
3. **下一步**：审计 P1（NEW-02 金额上界、CP-15 grant 权限、WB-04 HTTPS、GD-03 子仓 CI）  
4. （可选）内测前再跑 `tools/saas_e2e_acceptance.py`  

对 Agent 可说：`按 docs/saas/RESUME.md 修审计 P1`。

## 5. 不要做的事

- 不要把积分账本做进工作台 `lib/billing`（成本账保留；用户积分在控制面）  
- 不要大面积改上游核心以「塞」多租户；改动进 `saas/` + 控制面  
- 不要恢复邀请码 / 工作室 / 注册送积分（除非用户改 [DECISIONS.md](DECISIONS.md)）  
- 不要 `git push upstream`  
