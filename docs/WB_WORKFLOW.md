# WB 工作流约定

本文档定义本项目在 **WorkBuddy（WB）云任务空间** 与 **CNB 仓库** 之间的协作方式。
所有参与本项目的人（或 AI 任务）在开工前都应先读一遍。

## 核心前提

> **WB 沙箱不跨任务持久化。**

WB 的云任务空间是一次性的临时沙箱：任务结束（或沙箱休眠回收）后，本地的文件、环境变量、已安装依赖、未提交的改动都可能丢失。因此：

- **不要把项目状态存放在 WB 沙箱里。**
- **CNB 仓库 `image-playground/binary-pixel-art` 是施工期的 source of truth（唯一可信来源）。**

任何"只在沙箱里存在"的工作成果，等于不存在。

## 标准工作流

### 1. 任务开始：从 CNB 恢复

每个任务开工的第一步，都是把最新代码从 CNB 拉下来，而不是假定沙箱里还有上次的残留：

```bash
# 初始化 CNB CLI（沙箱首次使用时）
ln -sf /root/.codebuddy/skills/cnb-cool-connector/cnb-cli/bin/cnb.js /usr/local/bin/cnb
chmod +x /usr/local/bin/cnb
export CNB_API_ENDPOINT=https://api.cnb.cool

# 克隆仓库（token 由沙箱内的授权代理自动提供）
git clone https://cnb:<TOKEN>@cnb.cool/image-playground/binary-pixel-art.git
```

进入仓库后，先 `git log --oneline -10` 确认当前进度，再动手。

### 2. 施工中：小步迭代，落在仓库里

- 遵循项目既定原则：小步迭代，施工前先确认阶段与边界，不擅自扩展功能、不过度工程化。
- 新增/修改的文件直接落在仓库工作区内，**不要只写在沙箱临时目录**。
- 临时产物、试验输出、中间结果放在沙箱 scratch 目录，不要提交进仓库。

### 3. 任务结束：commit + push

**在结束任何任务之前，必须先 commit 并 push 到 `main`。** 这是硬性要求——未 push 的工作在下一次任务开始时就不存在了。

```bash
git add -A
git commit -m "<type>: <简要说明>"
git push origin main
```

提交信息使用 Conventional Commits 风格前缀：`feat:` / `fix:` / `docs:` / `refactor:` / `chore:` / `test:`。

### 4. 收尾自检

任务结束前逐项确认：

- [ ] 所有该提交的文件已 `git add`（用 `git status` 检查是否有遗漏、是否有不该提交的临时文件）
- [ ] `git log --oneline -3` 能看到本次 commit
- [ ] `git push` 成功，`git status` 显示与 `origin/main` 同步
- [ ] 在任务回复中报告 commit ID

## 为什么不用 WB 的本地状态作为依据

| 风险 | 后果 | 规避方式 |
|---|---|---|
| 沙箱被回收 | 未提交的改动全部丢失 | 结束前必须 push |
| 跨任务环境漂移 | 上次装的依赖/配置不存在 | 每次任务从零开始按本文档恢复 |
| 多任务/多人并行 | 各自沙箱内容不一致，互相覆盖 | 以 CNB 为唯一 source of truth，开工先 pull |
| 误把沙箱残留当既定事实 | 基于过期代码施工 | 开工先 clone/log 确认状态 |

## 一句话总结

**沙箱是草稿纸，CNB 是账本。草稿纸会被扔掉，所以每件事都要记进账本，并且每笔都要记账后离开。**
