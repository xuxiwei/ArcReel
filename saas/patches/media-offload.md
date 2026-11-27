# 视频、音频也保存到对象存储

## 问题

上游只有图片内容版本会随“新增内容保存位置 = 对象存储”写进对象存储（`stores_remotely` 只认 `.png`，
也只有图片提交包在 `formal_commit` 里）。SaaS 要求生成产物全部进 OSS。

## 改法（逻辑在 `saas/storage/media_offload.py`，自托管不变）

- `lib/material/formal_objects.py`
  - `stores_remotely`：SaaS 下 `.mp4`（videos、reference_videos）与 `.wav`（audio）也返回真。
  - `ObjectContentStorage.store`：视频/音频按文件流式计算摘要、`put_file_sync` 上传，不整块读进内存；按后缀设 Content-Type。
- `lib/object_storage/client.py`：新增 `put_file_sync`（TOS `put_object_from_file`；OSS 见 `aliyun_oss.py`）。
- `server/services/tasks/generation_tasks.py`：`execute_generation_task` 对 `video` / `reference_video` / `tts` / `voice_sample`
  任务包一层 `media_commit_scope` → `formal_commit(project_name)`，版本提交走与图片相同的登记、引用、结算、恢复。
- `lib/material/work_files.py`：闲置缓存清理跳过视频/音频工作文件。成片、时间线渲染、剪映导出、缩略图等会直接读本地文件，
  不会先从对象存储取回；对象存储是持久副本与下载来源，本地副本保留。

## 生效条件

仍由全局设置决定：设置 → 素材库 → 对象存储，“新增图片保存位置”选对象存储后，之后提交的图片、视频、音频都进对象存储；
已有版本不搬迁。

## 不在本补丁内

- 成片 / 时间线导出 / 剪映草稿等不走版本管理的输出仍只在本地（下一步按需处理）。
- 手动上传的视频（非生成任务）仍只在本地。
- 任务执行期间更换桶 / Endpoint 会让这次提交失败（与图片相同），不要在有任务运行时修改连接。

测试：`tests/unit/saas/test_media_offload.py`。
