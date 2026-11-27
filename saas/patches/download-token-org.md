# 下载链接（导出 ZIP、剪映草稿）在签发者的组织里找项目

## 问题

`GET /projects/{name}/export` 与 `GET /projects/{project_name}/edit-timelines/{id}/jianying-draft/download`
用查询参数里的一次性 `download_token` 自证身份，不走 Bearer 认证，所以没有绑定组织；`get_project_manager()`
退回扁平数据根，SaaS 下项目都在 `projects/org/<org>/` 里，结果报“项目不存在”。

## 改法（`saas/isolation/download_identity.py`，自托管不变）

- `server/auth.py` `create_download_token`：SaaS 下令牌里多带签发者的 `org`、`uid`（签发接口本身已认证）。
- `server/app.py`：两个 `self_auth_router` 挂路由级依赖 `bind_download_identity`。它在路由自己的服务依赖之前运行，
  校验令牌（与路由同一个 `verify_download_token`）通过后绑定该组织身份；校验失败什么也不做，交给路由照旧返回 401/403。
- 上线前签发、还没过期的旧令牌不带组织，几分钟后自然失效，重新点下载即可。

测试：`tests/unit/saas/test_download_identity.py`。
