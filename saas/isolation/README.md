# `isolation/`

SaaS **隔离 B**：

| 项 | 行为 |
| --- | --- |
| 项目目录 | `projects/org/<org_id>/<project_name>/` |
| 已删除项目 | `deleted_projects/org/<org_id>/…` |
| 对象存储 key | `…/org/<org_id>/user/<user_id>/…` 前缀 |

自托管（`DEPLOYMENT_MODE=self_hosted`）不改路径。Worker 依赖入队时戳记的 billing context。
