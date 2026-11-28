# 方舟私域素材库：平台 Key 可用、总开关、失败回退

Seedance 2.0 拒收含写实人脸的参考图（`InputImageSensitiveContentDetected.PrivacyInformation`），
需要先把角色图入库到方舟私域素材库，再以 `asset://` 素材 ID 引用。上游已有完整流程（素材库账号、
推理凭证绑定、资产卡片「上传到供应商素材库」、生成时自动替换），但绑定只认工作台数据库里的凭证记录；
SaaS 的方舟 Key 来自控制面（平台 Key），没有记录，所以素材库从未生效。

改动（`saas/adapter/asset_library_platform.py`）：

- 平台方舟 Key 作为 `credential_type="platform"` 的可绑定凭证列出：`ark` 固定 id 1，`ark-agent-plan` 固定 id 2。
  绑定照旧按 Key 实际内容与 endpoint 计算摘要，换 Key 后回到「需要重新确认」。
- 装配方舟视频 backend 时，若本次用的正是平台 Key，报出 `platform` 凭证引用，素材库按绑定生效。
- 后台总开关（系统设置 `saas_asset_library_enabled`，默认开）：关闭后所有调用都不用素材库，直接发图片；
  绑定与已入库记录保留。接口 `GET/PUT /api/v1/saas/admin/asset-library-switch`，仅管理员。
- 入库失败（`failed`）的关联不再阻塞生成，改为直接发图片；入库处理中仍提示等待。
- 成员隐藏「从供应商素材库选择」（浏览接口仅管理员），保留上传。

不受影响：其他供应商从不带素材库凭证；项目文件不变（关联单独记录）；自托管模式全部为空操作。

在火山侧停用素材库前，先在后台关闭总开关，避免生成引用已失效的素材。
