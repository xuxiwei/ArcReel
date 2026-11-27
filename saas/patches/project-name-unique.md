# 项目名跨组织唯一

## 问题

SaaS 把项目放在 `projects/org/<org_id>/<项目名>`，但对象存储引用表（`object_storage_formal_object_ref.project_name`）、
已删除项目墓碑名、匿名媒体路由都只按**项目名**区分。两个组织各有一个 `demo` 时，重算一方的对象引用会撤掉另一方的引用，
回收流程随后可能删掉另一方仍在使用的 OSS 对象（数据丢失）。

## 改法（`saas/isolation/project_names.py`，自托管不变）

占用项目目录名的三处都已持有全数据根的 `project_names_lock`，在锁内再检查其他组织是否用了同名：

- `lib/project/project_manager.py`：`creating_project` 遇到他组织同名抛 `FileExistsError`（接口返回“项目已存在”）；
  `generate_project_name` 跳过他组织已用的名字。
- `lib/project/deleted_projects.py`：`move_out`（恢复已删除项目）把他组织同名视为占用，改用 `-2`、`-3` 后缀。
- `server/services/project/project_archive.py`：导入时与他组织同名，一律改名导入，不提示、不覆盖。

## 已有数据

上线前检查一次：`uv run python -m saas.isolation.project_names`，输出 `no duplicate project names` 即可；
有重名时先手工改名再启用对象存储。

测试：`tests/unit/saas/test_project_names.py`。
