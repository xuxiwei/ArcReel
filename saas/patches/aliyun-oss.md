# 阿里云 OSS 对象存储

## 问题

上游对象存储只支持火山引擎 TOS（`ObjectStorageClient` 只接受 `kind="tos"`）。SaaS 部署在阿里云，
生成产物要存到阿里云 OSS。

## 改法

- `saas/storage/aliyun_oss.py`：`OssSdkShim` 用 `oss2` 实现 `ObjectStorageClient` 用到的那几个 TOS SDK 调用
  （`head_bucket` / `put_object` / `get_object` / `head_object` / `delete_object` / `pre_signed_url`），
  错误转成同样的 `ObjectStorageError` 分类，界面文案不用改。正式对象、中转副本、断开连接清理都不用动。
- `lib/object_storage/client.py`：`kind` 接受 `oss`；`create_sdk_client` 在 `oss` 时返回上面的 shim。
- `server/routers/object_storage.py`：`kind` 为 `tos` / `oss`；前端不传 `kind`，按 Endpoint 推断。
- `pyproject.toml`：新增依赖 `oss2>=2.18.0`。

## 细节

- 一律 HTTPS；V4 签名（`oss2.AuthV4`，需要 region，`oss-cn-hangzhou` 会自动去掉 `oss-`）。
- 测试连接先 `GetBucketInfo`；RAM 用户没有这项权限时改为 HEAD 一个不存在的 key：`NoSuchKey` 说明有权限，`NoSuchBucket` 报桶不存在。
- 签名下载地址永远不用 `-internal` Endpoint（浏览器和供应商访问不到）：优先 `ARCREEL_OSS_PUBLIC_ENDPOINT`（公网 Endpoint 或自定义域名），否则去掉 `-internal`。签名有效期最长 7 天。

## RAM 权限（最小）

对 `acs:oss:*:*:<bucket>/*`：`oss:PutObject`、`oss:GetObject`、`oss:DeleteObject`；可选对 `acs:oss:*:*:<bucket>`：`oss:GetBucketInfo`。

测试：`tests/unit/saas/test_aliyun_oss.py`。
