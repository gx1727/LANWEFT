# 12 可靠性模型（Reliability）

## 分层保障

- 控制面统计缺失并下发 `missing_chunks`（`mode=report`）；接收端乱序写盘与位图
- crc32 包级完整性；文件级内容 hash 校验（Blake3）
- 重传：UDP 不即时重传；聚合缺失后统一下发；重传优先级高于新数据
- 中断与恢复：不回滚已写入；恢复后加载位图并补传缺失
- 完成与提交：bitmap 全真 → 校验 hash → 原子重命名 → 发布完成消息

**裁决是唯一的推进依据（规范性）**：接收方**必须**至少每 50ms 下发一次 `missing_chunks`
（`mode=report`），**包括缺失列表为空的情况**；发送方据此推进窗口。
详见 11 章「窗口推进判据」。

`missing_chunks` 的 `mode` 为 `enum8`（`0` = report、`1` = request）；
`chunks` 为 `chunk_list`（`u32` 条数 + `u32` `chunk_id` 数组，**升序**），
「缺失列表为空」即 `chunk_list` 的条数为 `0`；`missing_count` 为位图中
**尚未收到**的 chunk **精确总数**（`u32`），**不是**本批 `chunks` 的长度。
见 06 章「missing_chunks」。

## 保底轮询（Keep-Alive Polling）

- Client 发送完全部数据后，若 Server 持续返回 `missing_chunks`（`mode=report`）
  且 `chunks` 为空（缺失列表为空），但**始终未下发** `upload_complete`，
  Client 进入保底轮询状态。
- 保底轮询**使用** 11 章判据第 4 条的**同一个 1000 ms 索要规则**：
  Client **必须**按该周期发布 `missing_chunks`（`mode=request`）
  持续索要缺失列表，直至收到 `upload_complete` 或触发超时。
- 目的：防止对端状态机卡死导致的会话悬挂。

## 连接断开的语义（规范性）

控制连接断开时，该连接承载的**全部**会话**必须**视为**中断**（可恢复），
**不得**直接置为 ABORTED：

- 断连**不**回滚已写入的数据，位图与临时文件**必须**保留。
- Client 重连后通过 `login` 的恢复列表恢复（见 13 章）。
- 只有会话活动超时（60 秒，见 09 章）才把会话置为 ABORTED 并清理资源。

## 看门狗（Watchdog）

看门狗的职责与 11 章判据第 4 条的索要规则**完全一致**：
发送方每 **1000 ms** 至少索要一次裁决，直到收到 `mode=report` 为止。
重复的 `mode=request` 是幂等的，与幂等要求兼容
（见 06 章「未识别消息必须忽略，保持幂等性」）。

## 完整性校验

- **包级**：每个 UDP 包尾部携带 CRC32，校验失败直接丢弃，**不得**写入位图
- **文件级**：传输完成后，接收方计算全文件 Blake3 哈希，与请求中的 `file_hash` 比对
  （`file_hash` 为 **32 字节原始 Blake3 摘要**，`hash32` 类型，非十六进制串）；
  一致才进入 COMMIT 并发布完成消息（上传方向 `upload_complete`，
  下载方向 `download_complete`）
- **文件级校验失败**：接收方**必须**发布 `session_abort`（`reason` = `FILE_HASH_MISMATCH`）
  终止会话。
  这是**接收侧唯一有权发起的终止**（见 10 章「终止权」）；
  其余终止原因一律由 Server 发起。
  由于包级 CRC32 已经过校验，文件级失配通常意味着**会话参数错误**
  （如 `chunk_size` 协商不一致）而非个别数据损坏，因此**不作为可重传事件处理**。
- **秒传路径**：跳过数据传输时没有位图，完成条件为「既有文件校验通过并原子提交」
  （见 10 章「秒传路径」）。
