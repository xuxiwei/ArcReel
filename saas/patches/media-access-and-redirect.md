# 媒体访问需登录 + 已存进 OSS 的媒体直接从 OSS 下载

## 问题

1. `/api/v1/files/{项目}/{路径}`、`/api/v1/global-assets/...` 不校验身份（`<img>` / `<video>` 带不了 Bearer）。
   SaaS 下知道项目名和路径的人就能看别人的图片、视频、成片。
2. 视频经工作台转发会占服务器带宽；已经存进 OSS 的文件可以让浏览器直接从 OSS 下载。

## 改法

- `saas/isolation/media_access.py`：每次带令牌的 API 调用（`server/auth.py` 的 `get_current_user`）都会按需刷新一个
  HttpOnly Cookie `arcreel_media`，内容为组织、用户和过期时间，用工作台密钥派生的 HMAC 签名，有效期 12 小时，
  剩余不到 6 小时时自动换新。Path 为 `/api/v1`，SameSite=Lax，HTTPS 下带 Secure。内嵌 Agent 不发 Cookie。
- `server/routers/files.py`
  - 项目媒体：只在 Cookie 所属组织里找项目；没有或无效的 Cookie 返回 401，别的组织的项目返回 404。
  - 全局资产媒体：需要有效 Cookie。
  - 媒体（不含 `?w=` 缩略图）已在 OSS 时返回 302，跳到有效期 1 小时的签名地址；跳转本身可在浏览器私有缓存 5 分钟。
    判断逻辑在 `saas/storage/media_redirect.py`：
    - 远端内容版本的工作文件（正式对象），或镜像副本与本地文件一致（`project_mirror`），
    - 并且对象在当前连接的桶里。
    - 其他情况照旧由工作台直接返回。
- 前端不需要改：浏览器访问同域名媒体时自动带上 Cookie。自托管不变。

## 部署要求

- OSS 桶要配 **CORS**（前端有些地方用 fetch 读音频、视频或下载文件，跟随 302 后是跨域请求）：
  - 来源：`https://你的域名`
  - 方法：GET、HEAD
  - 允许头：`*`
  - 暴露头：`ETag, Content-Length, Content-Range, Accept-Ranges, Content-Type`
- 桶保持**私有**读写（签名地址才能读）。

## 已知

- 退出登录后 Cookie 最长再有效 12 小时（只能看到自己组织的媒体）。
- 项目导出、剪映草稿下载（`download_token` 路由）不经过这里，另行处理。

测试：`tests/unit/saas/test_media_access.py`。
