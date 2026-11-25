# 进度状态

最后更新：2026-11-25（工程收口：fork 改名、JWT 同步推送、文档）

## 已完成

- [x] 产品决策定稿（控制面分仓、开放注册、个人组织、平台代付积分、隔离 B、可对账）  
- [x] 双仓目录骨架（工作台 `saas/` + 控制面在 `ArcReelControl/arcreel-control-plane`）  
- [x] 日更 / 补丁预算文档  
- [x] 控制面 ORM + Alembic 初始迁移 + Compose 占位  
- [x] 模型导入冒烟测试通过  
- [x] 计划全文写入 `docs/saas/`（本目录）  
- [x] 控制面：开放注册 / 登录 / 个人组织 / JWT + `GET /v1/me`  
- [x] 控制面：credits + admin + internal platform-keys  
- [x] 工作台：扣费钩子 hold/settle/release + 平台 Key 注入 + 隐藏 BYOK  
- [x] 工作台：隔离 B（`projects/org/<org_id>/…` + OSS org/user 前缀）  
- [x] 前端：顶栏积分余额（`GET /me/wallet` → 控制面 `/v1/me`）  
- [x] 管理后台 Vue（用户名密码 + is_admin）  
- [x] 审计 P0：密钥加密、计费 fail-closed、限流、CORS、AgentLint；NEW-05/06、CP-02  
- [x] 工作台 fork：`origin=xuxiwei/ArcReel`，`upstream` 官方；分支 `saas/control-plane-p0`  
- [x] 控制面随 `xuxiwei/ArcReelControl` 私有仓已推送  

## 进行中 / 阻塞

- [x] 外置库：应用角色 DML 授权 + `alembic stamp head`  
- [x] 工作台 `.env` 已配控制面 token  
- [x] upstream merge 已做过；可按需再 `fetch upstream && merge upstream/main`  
- [ ] 审计 P1：NEW-02 / CP-15 / WB-04 / GD-03  

## 下一步

1. [x] 工作台 fork + 提交推送  
2. [x] 控制面私有远程  
3. [ ] 审计 P1（金额上界、grant 最小权限、HTTPS、子仓 CI）  
4. [ ] （可选）真实 PG 并发钱包测试  

## 明确不做（本期）

工作室协作、邀请码、注册送积分、在线支付、多 Worker、企业实例。
