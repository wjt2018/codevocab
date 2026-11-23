# 参与贡献

感谢你愿意改进 CodeVocab！这份文档介绍开发环境、项目结构、词库的生成方法和发布流程。

- 只想修正某个词的释义或音标？直接看[修改人工整理的词库](#修改人工整理的词库)。
- 想改插件功能？从[开发环境](#开发环境)开始。

## 开发环境

需要：

- [Node.js](https://nodejs.org/) 18 或更高版本
- [VS Code](https://code.visualstudio.com/) 1.85 或更高版本
- Python 3.10 或更高版本（只有重新生成词库或图标时才需要）

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
│   ├── extension.ts              # 插件主体：单词本加载、播放流程、状态栏、命令
│   └── webview.ts                # 发音面板：用 Web Speech API 朗读，提供按钮、跳转和词库切换
├── wordbooks/                    # 内置词库（由脚本生成，不要手动修改）
│   ├── programmer.json ...
│   └── ECDICT-LICENSE.txt
├── scripts/
│   ├── build_wordbooks.py        # 生成全部内置词库
│   ├── programmer_words.tsv      # 程序员词汇词表（人工整理）
│   ├── mispronounced_words.tsv   # 程序员易读错词词表（人工整理）
│   ├── business_words.tsv        # 商务英语词表（人工整理）
│   ├── phonetic_overrides.tsv    # 人工补充的音标
│   └── make_icon.py              # 生成商店图标 images/icon.png
├── images/                       # 商店图标和 README 截图
├── media/icon.svg                # 底部面板标签的图标
└── package.json                  # 插件清单：命令、快捷键、设置项、商店信息
```

### 插件工作原理

VS Code 插件运行在 Node.js 环境里，没有发声能力，所以朗读交给一个 Webview（嵌在底部面板里的网页）完成：

```
extension.ts（播放进度、状态栏）  ── speak / stop / show ──▶  webview.ts（speechSynthesis 朗读）
                                 ◀── done / error / 按钮操作 ──
```

- 插件决定“现在读哪个词”，发送 `speak` 消息；网页读完后回复 `done`，插件等待 `codevocab.interval` 毫秒后切换到下一个词。
- 每次朗读都有一个递增的 `id`，用来丢弃过期的 `done` 消息（比如用户在读到一半时切换了单词）。
- 单词有 `speak` 字段时，英文语音朗读 `speak` 而不是 `word`。
- Webview 注册时开启了 `retainContextWhenHidden`，所以收起面板也不会中断发音。
- 静音模式下不发送 `speak`，改用 `codevocab.mutedDuration` 定时切换。
- 面板里的按钮、进度条、下拉框通过 `control`、`jump`、`selectBook` 等消息调用插件里的同一套逻辑，所以和快捷键、命令面板的状态始终同步。

## 词库是怎么生成的

所有内置词库都由 `scripts/build_wordbooks.py` 生成，分两类：

| 类型 | 词库 | 词条来源 | 释义来源 |
|---|---|---|---|
| 考试词库 | 四级、六级、考研、雅思、托福、GRE、高考、中考 | ECDICT 的考试标签 | ECDICT |
| 人工词库 | 程序员词汇、程序员易读错词、商务英语 | `scripts/*_words.tsv` | 词表本身（附 ECDICT 通用释义对照） |

### 生成流程

1. **读取 ECDICT**：按 `tag` 字段（`cet4`、`ky`、`gre`……）把词分到各考试词库。
2. **清理数据**（考试词库）：
   - 去掉基础词：中考词汇中词频排名在 `BASIC_RANK`（默认 1000）以内的词，以及首字母大写的词。规则见 `is_basic()`。
   - 修正拼写错误（`WORD_FIXES`），排除误收录的词条（`EXCLUDED_WORDS`）。
3. **整理释义**：取第一个词性的前 3 个义项作为简短释义（`meaning`），全部释义放进 `detail`；`[计]`、`[医]` 等专业领域释义排在最后。
4. **查找音标**，按以下顺序：
   1. 人工词表的第 4 列
   2. ECDICT 的音标（转换为标准 IPA 字符；多个读音只取第一个）
   3. `scripts/phonetic_overrides.tsv` 人工补充表
   4. 自动推导：根据 ECDICT 的词形变化找到原形并加上后缀读音（miles ← mile + /z/），或者处理英美拼写差异、合成词和 -ly、-ness、-ment 等常见后缀
5. **排序并写出**：默认按词频排序（加 `--alpha` 改为字母顺序）；易读错词保持词表中的顺序。

脚本最后会提示没有音标的词、重复的词和 ECDICT 中查不到的词，提交前请确认这些提示都已处理。

### 重新生成

1. 从 [ECDICT](https://github.com/skywind3000/ECDICT) 仓库下载 `ecdict.csv`（约 66 MB，不要提交到本仓库）。
2. 运行：

   ```bash
   python scripts/build_wordbooks.py path/to/ecdict.csv
   ```

3. 用 `git diff wordbooks/` 检查变化是否符合预期。

## 修改人工整理的词库

| 词库 | 词表 |
|---|---|
| 程序员词汇 | [scripts/programmer_words.tsv](scripts/programmer_words.tsv) |
| 程序员易读错词 | [scripts/mispronounced_words.tsv](scripts/mispronounced_words.tsv) |
| 商务英语 | [scripts/business_words.tsv](scripts/business_words.tsv) |

每行一个词，**用 Tab 分隔**（不是空格）：

```
单词  词性  释义  [音标]  [常见误读]  [朗读文本]
```

| 列 | 必填 | 说明 |
|---|---|---|
| 单词 | ✅ | |
| 词性 | ✅ | 如 `n.`、`v.`、`adj.` |
| 释义 | ✅ | 会被中文语音朗读，**不要在里面写英文**（中文语音读英文容易读错） |
| 音标 | | 留空时自动从 ECDICT 查找；易读错词必须填写 |
| 常见误读 | | 显示在悬停提示和面板里，主要用于易读错词 |
| 朗读文本 | | 系统语音读错单词时填写，例如 Nginx 填 `engine x` |

写释义时请注意：

- 写这个词在对应领域里最常用的意思，比如程序员词汇里 commit 写“提交”。
- 多个意思用中文分号 `；` 分隔，一般不超过三个。
- 有多种公认读法的词，在“常见误读”里说明，不要把常见的另一种读法说成错误。

修改后重新运行 `build_wordbooks.py`，把词表和生成的 `wordbooks/*.json` 一起提交。

### 补充音标

如果脚本提示某些词没有音标，把它们加进 [scripts/phonetic_overrides.tsv](scripts/phonetic_overrides.tsv)（`单词<Tab>音标`，按字母顺序），这个文件对所有词库都生效。

## 新增一本内置词库

**人工整理的词库**（比如“前端词汇”）：

1. 在 `scripts/` 下新建 `xxx_words.tsv`，格式同上。
2. 在 `build_wordbooks.py` 的 `CURATED_BOOKS` 中加一项，设置显示名称、释义标签、排序方式，以及是否附加 ECDICT 通用释义。
3. 在 `src/extension.ts` 的 `BUILTIN_BOOKS` 中加一项。
4. 在 `package.json` 的 `codevocab.builtinWordbook` 中，把它加进 `enum` 和 `enumItemLabels`。
5. 在 README 的词库表格里补充说明，并在 CHANGELOG 中记录。

**来自外部数据的词库**：只接受授权允许再分发的数据（例如 MIT、CC BY、CC BY-SA）。请在 Pull Request 中注明数据来源和授权，并在 `wordbooks/` 中附上对应的许可证文件。

## 提交代码

- 一个 Pull Request 只做一件事，方便审查。
- 提交前确认 `npm run compile` 没有错误，并在扩展开发宿主里实际试过改动。
- 用户能感受到的变化，请记录在 [CHANGELOG.md](CHANGELOG.md) 的 `## [Unreleased]` 下面。
- **不要修改 `package.json` 里的版本号**，版本号在发布时统一修改。
- 不要提交 `out/`、`node_modules/`、`.vsix` 文件和 `ecdict.csv`。

## 发布流程（维护者）

1. 把 `CHANGELOG.md` 中 `[Unreleased]` 下的内容移到新的版本号下面，提交。
2. 发布并自动升级版本号：

   ```bash
   npx vsce publish patch   # 修复问题：0.1.0 → 0.1.1
   npx vsce publish minor   # 新增功能：0.1.0 → 0.2.0
   ```

   `vsce` 会修改 `package.json` 中的版本号，并自动提交、打上版本标签。
   如果用网页上传：先运行 `npm version patch` 或 `npm version minor`，再运行 `npx vsce package`，然后到 [插件管理页面](https://marketplace.visualstudio.com/manage) 上传生成的 `.vsix`。

3. 推送提交和标签：`git push --follow-tags`。
4. （可选）发布到 [Open VSX](https://open-vsx.org/)，方便 Cursor、VSCodium 等编辑器的用户安装：`npx ovsx publish -p <token>`。
