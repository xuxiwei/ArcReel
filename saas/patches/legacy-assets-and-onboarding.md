# 历史资产归属、成员新手引导

## 历史资产归属

`saas/isolation/assign_legacy_assets.py`：把 SaaS 之前建的全局资产（`assets.org_id = ''`，谁都看不到）一次性交给一个组织。
默认只预览，`--apply` 才执行；目标组织里已有同类同名的条目会跳过并列出，不覆盖。

    python -m saas.isolation.assign_legacy_assets --org <org_id>
    python -m saas.isolation.assign_legacy_assets --org <org_id> --apply

从空库开始（例如 11 月 27 日的 `arcreel`）不需要跑。

## 成员新手引导

`frontend/src/onboarding/OnboardingTour.tsx`：SaaS 普通成员打不开“供应商”“ArcReel Agent”两个设置页，引导里这两步对成员跳过，
避免卡在找不到的锚点上。管理员和自托管不变。

测试：`tests/unit/saas/test_legacy_assets_and_mirror_settings.py`。
