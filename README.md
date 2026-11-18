# CodeVocab · 码上背单词

写代码的时候在后台朗读单词本：先读英文单词，再读中文释义。播到哪个单词，VS Code 底部状态栏就显示哪个单词的词性和释义。

## 功能

- 🔊 自动朗读单词和中文释义（使用系统自带语音，不需要联网）
- 🔇 静音模式：单词照常在状态栏轮播，但不发出声音
- 📌 状态栏同步显示当前单词、词性和释义，悬停可查看音标和完整释义
- ⌨️ 快捷键控制播放、暂停、显示和隐藏
- 📚 内置 8 本考试单词本：四级、六级、考研、雅思、托福、GRE、高考、中考
- 💾 自动记住每个单词本的播放进度

## 快捷键

| 功能 | Windows / Linux | macOS |
|---|---|---|
| 播放 / 暂停 | `Ctrl+Alt+P` | `Cmd+Alt+P` |
| 静音 / 取消静音 | `Ctrl+Alt+M` | `Cmd+Alt+M` |
| 显示 / 隐藏单词 | `Ctrl+Alt+H` | `Cmd+Alt+H` |
| 下一个单词 | `Ctrl+Alt+]` | `Cmd+Alt+]` |
| 上一个单词 | `Ctrl+Alt+[` | `Cmd+Alt+[` |
| 跳转到单词 | `Ctrl+Alt+G` | `Cmd+Alt+G` |

点击状态栏上的单词也可以播放或暂停；底部「CodeVocab」发音面板里也有对应的按钮，可以用鼠标操作。

**从指定位置开始听**：按 `Ctrl+Alt+G`（或运行命令 `CodeVocab: 跳转到单词…`），可以：

- 输入单词或中文意思搜索，例如 `abandon`、`放弃`
- 输入序号跳到第几个，例如 `500`
- 输入百分比跳到对应位置，例如 `50%`

也可以在底部「CodeVocab」发音面板里拖动进度条，或在输入框里输入序号、百分比、单词后按回车。

跳转后会从那个单词接着播放。每本单词本的进度会自动保存。所有快捷键都可以在「键盘快捷方式」中修改。

> 第一次播放时，底部面板会自动打开「CodeVocab」发音面板。开始播放后可以收起面板，不影响发音。

## 单词本

运行命令 `CodeVocab: 选择单词本…`，可以切换内置单词本，或者导入自己的文件。默认使用四级单词本。

### 内置单词本

| 单词本 | 词数 |
|---|---|
| 大学英语四级 | 3849 |
| 大学英语六级 | 5407 |
| 考研 | 4801 |
| 雅思 IELTS | 5040 |
| 托福 TOEFL | 6974 |
| GRE | 7503 |
| 高考 | 3677 |
| 中考 | 1603 |

内置单词本按词频排序，常用词在前面。状态栏显示简短释义，鼠标悬停或打开发音面板可以看到完整释义。

### 自定义单词本格式

**JSON**（`phonetic`、`pos`、`detail` 都可以省略）

```json
[
  { "word": "abandon", "phonetic": "/əˈbændən/", "pos": "v.", "meaning": "放弃；抛弃", "detail": "vt. 放弃；抛弃；遗弃
n. 放任；无拘束" }
]
```

**CSV / TSV / TXT**（每行一个单词，`#` 开头的行是注释）

```
abandon,v.,放弃；抛弃
ability,n.,能力
hello,你好
```

## 设置

| 设置项 | 默认值 | 说明 |
|---|---|---|
| `codevocab.builtinWordbook` | `cet4` | 内置单词本 |
| `codevocab.wordbookPath` | 空 | 自定义单词本路径，填写后优先于内置单词本 |
| `codevocab.interval` | `2000` | 两个单词之间间隔的毫秒数 |
| `codevocab.mutedDuration` | `5000` | 静音时每个单词停留的毫秒数 |
| `codevocab.speakMeaning` | `true` | 是否朗读中文释义 |
| `codevocab.rate` | `0.9` | 朗读语速 |
| `codevocab.maxMeaningLength` | `30` | 状态栏里释义最多显示的字符数 |

## 常见问题

**没有声音或中文读不出来？** 打开底部的「CodeVocab」面板，查看检测到的英文和中文语音。Windows 可以在「设置 → 时间和语言 → 语音」中添加中文语音包。

## 致谢

内置单词本的数据来自 [ECDICT](https://github.com/skywind3000/ECDICT)（MIT License，许可证见 `wordbooks/ECDICT-LICENSE.txt`），由 `scripts/build_wordbooks.py` 转换生成。
