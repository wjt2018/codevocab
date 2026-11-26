# 0005. 改用 esbuild 打包

- 状态：已接受
- 日期：2026-11-26
- 相关：[设计文档 · 技术方案 · 打包](../design/0.4-daily-dictation.md#打包)

## 背景

0.3.0 用 `tsc` 直接把 `src/` 编译到 `out/`，`.vscodeignore` 排除了 `node_modules/**`。所以插件包里带不了任何运行时依赖，一直以来也没有运行时依赖。

0.4.0 要引入 `ts-fsrs`（见 [ADR 0001](0001-use-fsrs-for-review-scheduling.md)），必须解决依赖怎么进插件包的问题。

可选方案：

- **A. esbuild 打包**：把源码和依赖打成单文件 `out/extension.js`。
- **B. vendor**：把 `ts-fsrs` 源码拷进 `src/vendor/`，继续用 `tsc`。
- **C. 带上 node_modules**：从 `.vscodeignore` 里放开 `node_modules`。

## 决策

采用方案 A：esbuild 打包成单文件。

- `compile` 脚本改为先 `tsc --noEmit` 做类型检查，再用 esbuild 打包。
- `vscode` 模块标记为 external。
- CI 和 `vscode:prepublish` 跟着调整。

没选 B：升级 `ts-fsrs` 要手动同步源码，容易忘，也不方便看出改过哪些地方。

没选 C：会把开发依赖和传递依赖一起打进去，插件包变大、启动变慢，VS Code 官方也不推荐。

## 后果

- 以后再加运行时依赖不需要额外处理。
- 单文件加载比多文件快，插件激活更快。
- 构建链多了一个工具。调试需要生成 sourcemap，`.vscodeignore` 已经排除了 `**/*.map`，发布包不受影响。
- 单元测试（`node:test`）直接跑 `src/srs/` 下的模块，不经过 esbuild。
