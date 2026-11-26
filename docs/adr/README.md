# 架构决策记录（ADR）

ADR 是 Architecture Decision Record 的缩写。这里每个文件记录一个重要的技术决策：当时面临什么问题、选了什么、带来哪些好处和代价。

## 规则

- 文件名：`NNNN-短横线连接的英文标题.md`，编号递增，不复用。
- 状态：提议中 / 已接受 / 已废弃 / 被 ADR NNNN 取代。
- 已接受的 ADR 不改正文。决策变了就写一篇新的，把旧的状态改成“被 ADR NNNN 取代”。
- 只记录难以撤回、影响多个模块或会让后来者疑惑“为什么这么做”的决策。日常改动的原因写在 commit 和 PR 里。

## 索引

| 编号 | 标题 | 状态 | 日期 |
| --- | --- | --- | --- |
| [0001](0001-use-fsrs-for-review-scheduling.md) | 复习调度采用 FSRS，不用固定间隔表 | 已接受 | 2026-11-26 |
| [0002](0002-card-key-is-lowercase-word.md) | 复习卡片以小写单词为 key，跨词库共用 | 已接受 | 2026-11-26 |
| [0003](0003-dictation-is-the-only-scheduling-signal.md) | 只有听写结果更新复习调度 | 已接受 | 2026-11-26 |
| [0004](0004-split-storage-globalstate-and-log-files.md) | 卡片存 globalState，作答日志存文件 | 已接受 | 2026-11-26 |
| [0005](0005-bundle-with-esbuild.md) | 改用 esbuild 打包 | 已接受 | 2026-11-26 |
| [0006](0006-study-center-as-editor-webview-panel.md) | 听写和可视化放在编辑器标签页「学习中心」 | 已接受 | 2026-11-26 |

## 模板

```markdown
# NNNN. 标题

- 状态：提议中
- 日期：YYYY-MM-DD

## 背景

当时面临什么问题，有哪些约束。

## 决策

选了什么。考虑过但没选的方案，以及没选的原因。

## 后果

带来的好处、代价和后续要注意的事。
```
