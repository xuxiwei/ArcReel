# 全局资产库按组织隔离

## 问题

全局资产库是一张全平台共用的表（`assets`，`(type, name)` 全局唯一）加一个文件目录，没有组织之分，
所以之前只给平台管理员用。直接开放会让各组织互相看到、修改、删除对方的资产，同名互相占用，图片地址也能跨组织读取。

## 改法

- **数据库**（`lib/db/models/asset.py` + 迁移 `alembic/versions/5a1e0c7d9b42_saas_asset_org_scope.py`）：
  `assets` 加 `org_id`（自托管为 `""`），唯一约束改为 `(org_id, type, name)`。衍生表跟随所属资产，不需要列。
- **读写**（`lib/db/repositories/asset_repo.py` → `saas/isolation/asset_scope.py`）：按 id / 名称 / 列表 / 计数读取都只在
  当前组织内；新建时写入当前组织。SaaS 下没有组织身份的调用读不到任何资产、也不能新建。
- **文件**：库文件本来就是随机文件名（`global_assets/<类型>/<uuid>.png`），各组织不会撞名，目录不动。
  `GET /api/v1/global-assets/...`（`server/routers/files.py`）在 SaaS 下只返回本组织资产或衍生引用的文件，其余 404。
- **权限**（`server/app.py`）：资产库接口不再只限管理员，成员可用；前端恢复顶栏与项目列表的资产库入口，资产库页面不再跳走。

## 上线注意

- 先跑迁移：`uv run python -m alembic upgrade head`（服务器上 `arcreelctl.sh migrate`）。
- 迁移前已有的资产 `org_id` 为空，SaaS 下谁都看不到；测试环境可直接清空，或按需手工把 `org_id` 改成对应组织。
- 合并上游时若上游新增了迁移，本迁移的 `down_revision` 需要接到上游新头上（或加一个 merge revision）。

测试：`tests/unit/saas/test_asset_scope.py`。
