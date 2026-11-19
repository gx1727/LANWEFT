# 07 数据面（UDP / TCP Fallback）

## UDP 原则

- 无连接、无逐包 ACK、允许丢包与乱序
- payload_len ≤ chunk_size（建议 chunk_size ≤ 1400，避免 IP 分片）
- crc32 包级校验 + `chunk_digest` 逐块摘要（见 08 章）
- 数据面端口**可以**被多个会话共用，`session_id`（u64）用于区分（见 08 章）

## 发送端

- **按批次发送**：连续发送 `burst_size` 个 chunk，批间隔 `batch_gap_us`
  （初值 2000µs；`burst_size` 初值 = `window`）。详见 11 章「发送节奏」。
  - 批**内**不逐包停顿；间隔施加在**批与批之间**，而非包与包之间。
- **仅对 `missing_chunks`（`mode=report`）报告的缺失块重传**，重传优先级高于新数据
- **逐块摘要**：会话协商 `chunk_digest` = 1 时，`FLAG_DATA` 包**必须**携带
  `chunk_digest`；协商为 0 时**不得**携带（见 08、09 章）；
  摘要与 payload **必须**取自同一次读取
- **数据面不得改变会话状态**，只能更新接收侧位图（见 10 章「推进规则」）

## 接收端

- 校验头、crc32 与（若携带）`chunk_digest`；**校验顺序**：先 crc32，再摘要，再写盘
- 随机写盘
- 标记位图
- 不直接推进状态机（位图变化只是接收侧状态推进的**输入**）

## UDP 可用性探测

### 交互流程

1. Client 发送 UDP_PROBE
2. Server 返回 UDP_PROBE_ACK
3. Server 通过控制通道发送 udp_ready

### PROBE 数据包

- flags.bit3=1，flags.bit0（FLAG_DATA）**必须**为 0
- payload 为 session_id（u64）的 **8 字节小端编码**
- `payload_len` = **8**

### PROBE_ACK 数据包

- flags.bit3=1，flags.bit0（FLAG_DATA）**必须**为 0
- payload 为 session_id（u64）+ 1 字节状态码（0=成功，1=失败），共 **9 字节**
- `payload_len` = **9**
- **判别规则（规范性）**：PROBE 与 PROBE_ACK 共用 `flags.bit3`，
  接收方**必须**以 `payload_len` 区分：`payload_len == 8` 为 PROBE，
  `payload_len == 9` 为 PROBE_ACK。其余长度**必须**按 `INVALID_PACKET` 丢弃。
  - **判别前提（规范性）**：该规则**仅**适用于 `FLAG_PROBE` 置位且 `FLAG_DATA`
    **未**置位的包。`FLAG_DATA` 包一律按数据路径处理，
    **不得**用 `payload_len` 判别类型（文件末尾块的 `payload_len` 可能恰好为 8 或 9）。

### 端口与地址绑定（规范性）

- Server 的数据面 socket **必须**绑定 accept 消息中下发的 `udp_port`。
- Server **必须**以 PROBE 报文的**源地址:端口**作为该会话的对端数据面地址；
  Server 不得向未经 PROBE 确认的地址发送数据面数据包（见 20 章）。
- Server 返回的 PROBE_ACK **必须**从该会话的数据面端口发出，
  以保证客户端的 NAT 映射命中。

### 超时

- Client 等待 PROBE_ACK 超时（建议 2s）则判定 UDP 不可用
- 回退到 TCP

## TCP 降级

> **术语澄清**：本节的「TCP 通道」指**数据面**的降级通道，
> 与**控制面**的 TCP 长连接（见 06 章）**完全无关** ——
> 二者是不同的通道、不同的端口、不同的消息。

- UDP 不可用或异常时启用
- 保持 chunk 与 bitmap 语义
- **TCP 通道的线路格式见本章「TCP 数据面线路格式」**：
  帧边界、逐块摘要、绑定与权限校验均**必须**与 UDP 通道语义一致
- TCP 端口由 accept 消息的 `tcp_port` 字段下发；**`tcp_port = 0` 表示不支持 TCP 降级**，
  此时探测失败即判定传输不可用

## TCP 数据面线路格式（规范性）

### 帧结构（小端序）

TCP 是字节流，**必须**有帧边界；且 TCP 已提供字节流校验，
因此 TCP 数据面帧**不重复** CRC32（与 06 章控制帧同理）。

| 字段 | 偏移 | 大小 | 类型 | 说明 |
|------|------|------|------|------|
| frame_len | 0-3 | 4 | u32 | 本帧总字节数（含本帧头） |
| session_id | 4-11 | 8 | u64 | 会话 ID；与 UDP 通道同一取值域 |
| chunk_id | 12-15 | 4 | u32 | 逻辑位置（从 0 开始） |
| payload_len | 16-17 | 2 | u16 | 载荷长度 |
| flags | 18-19 | 2 | u16 | 标志位（取值见 08 章；bit6 = FLAG_BIND） |
| payload | 20.. | N | bytes | 文件数据 |
| chunk_digest | 20+N | 8 | bytes | 逐块摘要；**可选字段**：仅当会话协商启用摘要且本帧为 `FLAG_DATA` 时携带 |

```
FRAME_HEADER_SIZE = 4 + 8 + 4 + 2 + 2 = 20 字节
```

**帧长核算（规范性）**：

```
frame_len = 20 + payload_len + (携带 chunk_digest ? 8 : 0)
```

- `frame_len` **必须** ≥ **20**
- 接收方**必须**按 `frame_len` **读满**后再解析：
  **不得**假设一帧一次 `recv` 到达；**不得**按换行或任何字节模式切分。
- `payload_len` **必须** ≤ 本会话协商的 `chunk_size`；
  越界即按 `INVALID_PACKET` 关闭该 TCP 数据面连接。
- 携带 `chunk_digest` 的帧，接收方**必须**独立校验，
  失配按 `CHUNK_DIGEST_MISMATCH` 丢弃该帧并按常规缺失路径请求该块
  （语义与 UDP 通道一致，见 08 章、12 章）。
- **无 CRC32**：TCP 提供字节流校验与可靠重传，TCP 数据面帧**不**携带 `crc32`
  —— 载荷完整性由 TCP 自身保证，帧内**不重复**逐块摘要之外的任何校验。
  摘要启用时，它承担的是**端到端**的块内容绑定（见 08 章）。

### 绑定帧（FLAG_BIND）

TCP 数据面连接**不**承载认证凭据，其权限**必须**通过绑定建立。

- Client 建立 TCP 数据面连接后，**必须**先发送一个**绑定帧**：
  `flags` 置位 `FLAG_BIND`（bit6）、**未**置位 `FLAG_DATA`，`payload_len` = **0**，
  `session_id` 为待绑定会话。
- Server **必须**校验：
  1. 该 `session_id` 存在且处于可传输状态（`NEGOTIATING` / `TRANSFERRING` / `PAUSED`）；
  2. 该会话的 `client_id` 与**持有该会话的控制连接**所绑定的 `device_id` 一致；
  3. 该 TCP 数据面连接的来源 IP 与该控制连接的对端 IP 一致。
  任一项不满足即**必须**关闭该 TCP 数据面连接，且**不得**发送任何数据面帧。
- 绑定成功后，该 TCP 数据面连接**只能**承载**该 `session_id`**；
  收到其他 `session_id` 的帧**必须**按 `SESSION_ID_MISMATCH` 丢弃该帧。
- 同一会话**已有**活动的 TCP 数据面连接时，新的绑定**必须**替换旧连接
  （旧连接**必须**被关闭）—— 重连语义因此是幂等的。
- **多个会话**可以各自建立独立的 TCP 数据面连接；`session_id` 用于区分。

### 与 UDP 通道的关系

- 两条通道的**块语义完全一致**：`chunk_id`、`chunk_size`、偏移映射
  `offset = chunk_id × chunk_size`、`chunk_digest` 算法与覆盖区间。
- 两条通道的**可靠性机制一致**：位图、缺失裁决、重传优先级、
  文件级校验与原子提交（见 12 章、17 章）。
- TCP 通道**不**使用 UDP 探测；其可用性由 `tcp_port` 是否为 0 表达
  （`tcp_port` = 0 表示不支持 TCP 降级）。
