# 0004. 卡片存 globalState，作答日志存文件

- 状态：已接受
- 日期：2026-11-26
- 相关：[设计文档 · 数据模型与存储](../design/0.4-daily-dictation.md#数据模型与存储)

## 背景

0.4.0 要持久化三类数据：

| 数据 | 特点 |
| --- | --- |
| 复习卡片 | 每个学过的词一条，几千条，读写频繁，希望跨设备同步 |
| 今日计划、统计、成就 | 很小，希望跨设备同步 |
| 作答日志 | 每次作答一行，只增不减，一年几百 KB |

VS Code 给插件的存储方式：

- `ExtensionContext.globalState`：键值存储，跨工作区共用。可以用 `setKeysForSync` 让指定 key 随 Settings Sync 同步。插件激活时整份读进内存，每次 `update` 整个值重写。Settings Sync 对同步内容有大小限制，具体数值没有公开文档。
- `ExtensionContext.globalStorageUri`：插件专属目录，自己读写文件，不会同步。

## 决策

- 卡片、今日计划、统计放 `globalState`，用 `setKeysForSync` 声明同步。卡片压成紧凑数组，每个词约 50 字节，5000 词约 250 KB。
- 作答日志写成 `<globalStorageUri>/reviews-YYYY.jsonl`，按年切分，只追加，不同步。
- key 带版本后缀（`.v1`），值里也有 `v` 字段，方便以后迁移。
- 提供“导出 / 导入学习记录”命令，作为同步的兜底。

没选全部放 globalState：日志无限增长，会拖慢插件激活，也容易超过同步的大小限制。

没选全部放文件：失去 Settings Sync 的免费跨设备同步。

没选自建云端同步：需要账号体系和服务端，超出当前阶段。

## 后果

- 开了 Settings Sync 的 VS Code 用户换设备时，复习进度能跟着走；历史作答点不会跟过去，但曲线仍能按当前稳定性画出来。
- Cursor、VSCodium 等用户以及没开同步的用户只能靠导出导入迁移数据。
- 多个 VS Code 窗口共用一份 globalState，写入前要重新读取并按单词合并，同一个词保留 lastReview 较新的那条。
- 上线前要用 5000 张卡片实测同步是否成功。
