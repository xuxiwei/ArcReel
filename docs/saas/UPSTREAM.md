# 工作台与上游日更

官方可能一天多次更新。控制面**不**跟上游。

## Remotes（目标）

| remote | 指向 | 用途 |
| --- | --- | --- |
| `upstream` | `https://github.com/ArcReel/ArcReel.git` | 只读拉取（本机已加） |
| `origin` | 你的 workbench fork | 推含 `saas/` 的发布（**当前仍误指官方，待切 fork**） |

## 演练记录（2026-11-24）

- `git fetch upstream main`
- 独立 worktree：`upstream-sync` ← `HEAD`，再 `git merge upstream/main` → **fast-forward**，**0 conflicts**
- 本次上游 diff 未触及 `saas/PATCH_BUDGET.md` 白名单文件
- 演练分支/worktree 已删；日常合并仍按下方流程，先切 fork 再 push

## 分支

- `main`：可部署  
- `upstream-sync`：合并官方的缓冲分支  

## 最小流程

```bash
git fetch upstream
git checkout upstream-sync
git merge upstream/main
# 冲突应几乎只在 PATCH_BUDGET 触点或 saas/
uv run python scripts/gate.py --changed
git checkout main
git merge upstream-sync
git push origin main
```

策略固定用 **merge**（适合频繁官方更新）。

## 补丁预算

见仓库根下 [`saas/PATCH_BUDGET.md`](../../saas/PATCH_BUDGET.md)。  
非 `saas/` 的长期 diff 控制在很少文件；超了先收回 `saas/`。
