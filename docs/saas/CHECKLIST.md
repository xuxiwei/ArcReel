# 实施勾选清单

改完一项就勾一项，并同步 [STATUS.md](STATUS.md)。

## 工程地基

- [x] `docs/saas/` 计划文档落地  
- [x] `saas/` 适配目录占位  
- [x] `arcreel-control-plane` 仓与库模型  
- [x] 外置 Postgres：`alembic stamp head`（表已由 schema.sql 建好）  
- [x] 外置库应用角色 DML 授权（`db/grant_app_role.sql`）  
- [ ] 工作台 fork + `origin` 切自有仓（`upstream` 已加官方）  
- [ ] 控制面推到私有 Git 远程  

## 控制面 API

- [x] 注册 / 登录 / JWT  
- [x] 个人组织 + 钱包 0  
- [x] me  
- [x] hold / settle / release  
- [x] admin grant（按汇率）  
- [x] admin 配 Key / 汇率 / 系数  
- [x] admin 流水对账  
- [x] internal platform-keys
- [x] 工作台 hold/settle/release 钩子
- [x] 平台 Key 注入 + 隐藏 BYOK  

## 工作台

- [x] DEPLOYMENT_MODE  
- [x] 鉴权桥（login/register 代理 + JWT 校验）  
- [x] 计费路径 hold/settle/release 钩子（ledger）  
- [x] 平台 Key 注入 + 隐藏 BYOK  
- [x] 项目/OSS 隔离 B  
- [x] 顶栏余额  
- [ ] 契约测试 + 自托管回归  
- [x] upstream merge 演练一次（fast-forward，无冲突）  

## 验收（上线邀请制内测前）

- [x] 两用户互不可见（项目列表）  
- [x] 无余额拒 hold（402）；充值后可 hold/settle  
- [x] settle 带成本字段；失败/取消 release（冒烟）  
- [x] 失败释放 hold（release 路径冒烟）  
