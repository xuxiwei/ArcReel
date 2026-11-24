# 进度状态

最后更新：2026-11-24（联调验收 + upstream merge 演练）

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

## 进行中 / 阻塞

- [x] 外置库：应用角色 DML 授权 + `alembic stamp head`  
- [x] 工作台 `.env` 已配 `CONTROL_PLANE_ADMIN_TOKEN`  
- [x] 已加 `upstream` remote；`origin` 仍指向官方（fork 未切）  
- [x] 联调验收脚本 `tools/saas_e2e_acceptance.py` 通过  
- [x] upstream merge 演练：worktree `upstream-sync` ← `upstream/main` fast-forward，无冲突；预算触点未落入本次上游 diff  

## 下一步（P0）

1. [x] 控制面：开放注册 / 登录 / 个人组织 / JWT  
2. [x] 控制面：管理 API（Key、汇率、grant、ledger）  
3. [x] 控制面：hold / settle / release + ledger  
4. [x] 工作台：`DEPLOYMENT_MODE` + 鉴权桥 + 扣费钩子 + 平台 Key  
5. [x] 工作台：项目 + OSS 按 org 隔离  
6. [x] 前端：SaaS 注册/登录入口 + 顶栏余额  
7. [x] 联调验收 + upstream merge 演练  
8. [ ] 工作台 fork：`origin` 切自有仓，`upstream` 保留官方；提交 `saas/`（已从 `.gitignore` 移除误伤）  

## 明确不做（本期）

工作室协作、邀请码、注册送积分、在线支付、多 Worker、企业实例。
