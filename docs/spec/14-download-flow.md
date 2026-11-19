# 14 下载流程（Server → Client）

## 原则

- Client 主动发起
- Server 不向未知端口推送 UDP（客户端端口由 `download_accept.udp_port` 与 UDP 探测确定）
- 控制面与可靠性机制与上传一致
- 会话类型：Upload（C→S）、Download（S→C）

## 下载控制消息

| 消息 | 方向 | 用途 |
|------|------|------|
| download_start | Client→Server | 请求下载文件 |
| download_accept | Server→Client | 接受下载请求，下发会话参数与数据面端口 |
| missing_chunks | 双向 | 缺失 chunk 列表报告 / 索要（`mode=report` / `mode=request`） |
| download_complete | Client→Server | 下载完成（由接收方 Client 发布） |

## 下载流程时序

### 1. 会话建立

Client 发送 download_start → Server 返回 download_accept（含 `session_id`（`u64`）/
`chunk_count`（`u32`）/ `window`（`u32`）/ `connection_window`（`u32`）/
`chunk_digest`（`enum8`）/ `udp_port`（`u16`）/ `tcp_port`（`u16`））

### 2. UDP 探测

Client 发送 UDP_PROBE → Server 返回 UDP_PROBE_ACK → Server 发送 udp_ready

Server 以 PROBE 报文的**源地址:端口**作为该会话的对端数据面地址。

**数据面端口的优先级（规范性）**：Client **必须**按以下顺序取用**最新**的端口值：

| 优先级 | 来源 | 生效时机 |
|--------|------|----------|
| 1（最高） | `login_ack` 的 `sessions[]` 快照记录中的 `udp_port` | **断线重连**后的权威快照 |
| 2 | `resume_ack.udp_port` | **暂停后恢复**的应答 |
| 3 | `udp_ready.udp_port` | 探测完成时（最新的探测结果） |
| 4 | `download_accept.udp_port` | 参数协商时（初始值） |

四者的 `udp_port` 均为 `u16`（见 06 章各消息的定长区布局）。

四者不一致时**必须**取优先级最高者；端口变更**必须**通过上述消息显式下发，
Client **不得**自行推断。

> **权威 vs 增量**：优先级 1、2 是**权威快照**（整体替换本地会话状态，
> 见 13 章），优先级 3、4 是同一连接内的**增量通知**。
> 快照到达时**必须**以其覆盖本地保存的端口，不得与旧值并存。

### 3. 数据传输

Server 按 `window` 连续发送 UDP chunk（批量发送，节奏见 11 章），
每个数据包**必须**携带 `chunk_digest`（见 08 章）。
Server **必须**同时遵守连接级的 `connection_window`
（该连接上所有会话的在途量之和，见 11 章）。

### 4. 缺失重传

Server 每 50ms 下发 `missing_chunks`（`mode=report`）裁决；
Client 收到后按 11 章补发缺失块。
收到 Client 的 `missing_chunks`（`mode=request`）时，Server **必须**在 50ms 内应答。

`mode` 为 `enum8`（`0` = report、`1` = request）；
`chunks` 为 `chunk_list`（`u32` 条数 + `u32` `chunk_id` 数组，**升序**），
恒为「发布方自己尚未收到的块」（见 06 章「missing_chunks」）。

### 5. 进度上报

Client 每 500ms 发布 `progress_update`（`received` / `total` 为 chunk 数，
均为 `u64`），Server 据此估算链路丢包率并驱动 AIMD（见 11 章）。

**进度消息由接收方发布**：下载方向的接收方是 Client，
只有它知道本端已接收的 chunk 数。

### 6. 完成与终止

Client 检测位图全真 → 校验 hash → 原子重命名 → 发送 download_complete
（**接收方发布完成消息**，见 06 章）

**复核轮**：Client 校验 hash 失配时**必须**进入复核轮
（清空位图 → 发布带复核轮标志的 `missing_chunks` → Server 全量重读重发），
**不得**直接终止会话；复核轮后仍失配才以
`session_abort`（`reason` = `FILE_HASH_MISMATCH`）终止（见 12 章）。

## 与上传对称性

| 阶段 | 上传（C→S） | 下载（S→C） |
|------|-------------|-------------|
| 会话建立 | upload_start | download_start |
| 参数下发 | upload_accept | download_accept |
| 数据方向 | Client→Server | Server→Client |
| 完成通知 | upload_complete（**Server** 发布） | download_complete（**Client** 发布） |
| 缺失报告 | Server→Client（Server 报告自己缺的块） | Client→Server（Client 报告自己缺的块） |
| 缺失索要 | Client→Server（`mode=request`） | Server→Client（`mode=request`） |
| 裁决节奏 | 接收方（Server）每 50ms 下发 | 接收方（Client）每 50ms 下发 |
| 进度上报 | Server→Client（**Server** 发布 `received`） | Client→Server（**Client** 发布 `received`） |
| 恢复提示来源 | Server 自有位图（Client 不携带） | Client 自有位图（Client **必须**携带） |

**完成消息一律由接收方发布（规范性）**：接收方持有位图与临时文件，只有它能完成
「校验 hash → 原子重命名」并判定成败。
