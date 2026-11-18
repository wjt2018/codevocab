# 参与贡献

感谢你愿意改进 CodeVocab！这份文档介绍开发环境、项目结构和发布流程。

## 开发环境

需要：

- [Node.js](https://nodejs.org/) 18 或更高版本
- [VS Code](https://code.visualstudio.com/) 1.85 或更高版本
- Python 3（只有重新生成词库或图标时才需要）

```bash
git clone https://github.com/wjt2018/codevocab.git
cd codevocab
npm install
```

用 VS Code 打开项目，按 **F5** 会启动一个「扩展开发宿主」窗口，插件在这个窗口里运行。修改代码后会自动重新编译，在扩展开发宿主窗口里按 **Ctrl+R** 重新加载即可看到效果。

常用命令：

| 命令 | 作用 |
|---|---|
| `npm run compile` | 编译 TypeScript 到 `out/` |
| `npm run watch` | 监听文件变化并自动编译（F5 会自动运行） |
| `npm run package` | 打包成 `.vsix`，可以在本地安装测试 |

## 项目结构

```
codevocab/
├── src/
│   ├── extension.ts        # 插件主体：单词本加载、播放流程、状态栏、命令
│   └── webview.ts          # 发音面板：用 Web Speech API 朗读，提供按钮和跳转控件
├── wordbooks/              # 内置词库（由脚本生成，不要手动修改）
│   ├── cet4.json ...
│   └── ECDICT-LICENSE.txt
├── scripts/
│   ├── build_wordbooks.py  # 从 ECDICT 生成内置词库
│   └── make_icon.py        # 生成商店图标 images/icon.png
├── images/                 # 图标和 README 截图
├── media/icon.svg          # 底部面板标签的图标
└── package.json            # 插件清单：命令、快捷键、设置项、商店信息
```

### 工作原理

VS Code 插件运行在 Node.js 环境里，没有发声能力，所以朗读交给一个 Webview（嵌在底部面板里的网页）完成：

```
extension.ts（播放进度、状态栏）  ── speak / stop / show ──▶  webview.ts（speechSynthesis 朗读）
                                 ◀── done / error / 按钮操作 ──
```

- 插件决定“现在读哪个词”，发送 `speak` 消息；网页读完后回复 `done`，插件等待 `codevocab.interval` 毫秒后切换到下一个词。
- 每次朗读都有一个递增的 `id`，用来丢弃过期的 `done` 消息（比如用户在读到一半时切换了单词）。
- Webview 注册时开启了 `retainContextWhenHidden`，所以收起面板也不会中断发音。
- 静音模式下不发送 `speak`，改用 `codevocab.mutedDuration` 定时切换。

## 重新生成内置词库

内置词库来自 [ECDICT](https://github.com/skywind3000/ECDICT)。如果 ECDICT 有更新，或者想调整释义的整理规则：

1. 从 ECDICT 仓库下载 `ecdict.csv`（约 66 MB，不要提交到本仓库）。
2. 运行：

   ```bash
   python scripts/build_wordbooks.py path/to/ecdict.csv
   # 默认按词频排序，加 --alpha 改为按字母顺序
   ```

3. 检查 `git diff wordbooks/` 中的变化是否符合预期。

释义的整理规则（取第一个词性的前 3 个义项作为简短释义、专业领域释义排在最后等）都写在脚本的注释里。

## 提交代码

- 一个 Pull Request 只做一件事，方便审查。
- 提交前确认 `npm run compile` 没有错误，并在扩展开发宿主里实际试过改动。
- 用户能感受到的变化，请记录在 [CHANGELOG.md](CHANGELOG.md) 的 `## [Unreleased]` 下面。
- **不要修改 `package.json` 里的版本号**，版本号在发布时统一修改。
- 不要提交 `out/`、`node_modules/` 和 `.vsix` 文件（已在 `.gitignore` 中忽略）。

### 新增内置词库

只接受授权允许再分发的词库数据（例如 MIT、CC BY、CC BY-SA）。请在 Pull Request 中注明数据来源和授权，并在 `wordbooks/` 中附上对应的许可证文件。

## 发布流程（维护者）

1. 把 `CHANGELOG.md` 中 `[Unreleased]` 下的内容移到新的版本号下面，提交。
2. 发布并自动升级版本号：

   ```bash
   npx vsce publish patch   # 修复 bug：0.1.0 → 0.1.1
   npx vsce publish minor   # 新增功能：0.1.0 → 0.2.0
   ```

   `vsce` 会修改 `package.json` 中的版本号，并自动提交、打上版本标签。首次发布时版本号已经是 `0.1.0`，直接运行 `npx vsce publish` 即可，不需要加参数。

3. 推送提交和标签：`git push --follow-tags`。
4. （可选）发布到 [Open VSX](https://open-vsx.org/)，方便 Cursor、VSCodium 等编辑器的用户安装：`npx ovsx publish -p <token>`。
