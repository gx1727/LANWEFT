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
`udp_port`（`u16`）/ `tcp_port`（`u16`））

### 2. UDP 探测

Client **必须**先打开数据面 socket，再从该 socket 发出 UDP_PROBE
→ Server 返回 UDP_PROBE_ACK → Server 发送 udp_ready

Server 以 PROBE 报文的**源地址:端口**作为该会话的对端数据面地址。
下载方向的**接收方是 Client**，因此 Client 的数据面 socket 是**强制**的：
Server 不得向未经 PROBE 确认的地址发送数据（见 20 章）。
Client 的端口通常为**临时端口**，由 Server 从 PROBE 的源地址学到；
socket 的生命周期见 07 章「接收方 socket 生命周期」。

**数据面端口按生效时序更新（规范性，上传与下载相同）**：accept 或 offer 给出初始端口。
重连立即作废旧连接的地址绑定；以成功快照为新起点，同一连接随后成功的
`resume_ack` 替换此前端口。失败应答不建立绑定。Client 从可传输状态在当前端口
重新 PROBE，Server 不得向旧绑定发数据；暂停或仅等待完成回执时不探测。
`udp_ready` 只确认当前探测，不改变端口；无待决探测或端口不匹配的就绪通知必须忽略。

### 3. 数据传输

Server 按 `window` 连续发送 UDP chunk（批量发送，节奏见 11 章），
Server **必须**同时遵守连接级的 `connection_window`
（该连接上所有会话的在途量之和，见 11 章）。

### 4. 缺失重传

Client 在收到新块时下发 `window_update`（`received_count`）推进窗口；
当存在缺失时每 50ms 发送 `missing_chunks`（`mode=report`）；Server 按 11 章补发缺失块。
收到 Server 的 `missing_chunks`（`mode=request`）时，Client **必须**在 50ms 内应答。

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

Server 持久化完成回执后回复 `complete_ack`；断线交付见 13 章。
Client 校验 hash 失配时先执行 12 章的摘要对帐，再按该章条件进入复核轮或终止。

## 与上传对称性

| 阶段 | 上传（C→S） | 下载（S→C） |
|------|-------------|-------------|
| 会话建立 | upload_start | download_start |
| 参数下发 | upload_accept | download_accept |
| 数据方向 | Client→Server | Server→Client |
| 完成通知 | upload_complete（**Server** 发布） | download_complete（**Client** 发布） |
| 缺失报告 | Server→Client（Server 报告自己缺的块） | Client→Server（Client 报告自己缺的块） |
| 缺失索要 | Client→Server（`mode=request`） | Server→Client（`mode=request`） |
| 窗口信用 | Server→Client（**接收方** Server 发布 `window_update`） | Client→Server（**接收方** Client 发布 `window_update`） |
| 裁决节奏 | 存在缺失时接收方（Server）每 50ms 下发 | 存在缺失时接收方（Client）每 50ms 下发 |
| 进度上报 | Server→Client（**Server** 发布 `received`） | Client→Server（**Client** 发布 `received`） |
| 恢复提示来源 | Server 自有位图（Client 不携带） | Client 自有位图（Client **必须**携带） |

**完成消息一律由接收方发布（规范性）**：接收方持有位图与临时文件，只有它能完成
「校验 hash → 原子重命名」并判定成败。
