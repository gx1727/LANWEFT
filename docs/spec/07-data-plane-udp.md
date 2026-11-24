# 07 数据面（UDP / TCP Fallback）

## UDP 原则

- 无连接、无逐包 ACK、允许丢包与乱序
- 一个数据报承载 `K` 个 symbol（`K × symbol_size` 字节，见 08 章）；
  `symbol_size` = 1200，`chunk_size` 为其整数倍（默认 64800，`S` = 54）
- crc32 包级校验（见 08 章）
- 数据面端口**可以**被多个会话共用，`session_id`（u64）用于区分（见 08 章）

## 发送端

- **按批次发送**：连续发送 `burst_size` 个 chunk，批间隔 `batch_gap_us`
  （初值 2000µs；`burst_size` 初值 = `min(256, window)`）。详见 11 章「发送节奏」。
  - 批**内**不逐包停顿；间隔施加在**批与批之间**，而非包与包之间。
- **仅对 `missing_chunks`（`mode=report`）报告的缺失块重传**，重传优先级高于新数据
- **数据面不得改变会话状态**，只能更新接收侧位图（见 10 章「推进规则」）

## 接收端

- 校验头与 crc32
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
- 载荷长度（由报文总长反推）= **8**

### PROBE_ACK 数据包

- flags.bit3=1，flags.bit0（FLAG_DATA）**必须**为 0
- payload 为 session_id（u64）+ 1 字节状态码（0=成功，1=失败），共 **9 字节**
- 载荷长度（由报文总长反推）= **9**
- **判别规则（规范性）**：PROBE 与 PROBE_ACK 共用 `flags.bit3`，
  接收方**必须**以**载荷长度**区分：`8` 为 PROBE，`9` 为 PROBE_ACK。
  其余长度**必须**按 `INVALID_PACKET` 丢弃。
  - **判别前提（规范性）**：该规则**仅**适用于 `FLAG_PROBE` 置位且 `FLAG_DATA`
    **未**置位的包。`FLAG_DATA` 包一律按数据路径处理，
    **不得**用载荷长度判别类型（数据报的 `K × symbol_size` 可能恰好为 8 或 9 字节）。

### C↔C peer PROBE（规范性）

仅用于 `direction = peer` 的**直连**：发送方向接收方声明的数据端点发送探测。

- `flags.bit7 = 1`（`FLAG_PEER_PROBE`）、`flags.bit0 = 0`；`chunk_id = 0`、`chunk_symbol = 0`。
- **PROBE** 载荷 = `session_id`（u64，8 字节）‖ `transfer_token`（16 字节），`L = 24`。
- **PROBE_ACK** 载荷 = 上述 24 字节 ‖ 1 字节状态（0=成功，1=失败），`L = 25`。
- 接收方**必须**校验 `transfer_token` 与 `session_id`，并从**同一数据面端口**回 ACK；
  校验失败按 `PEER_TOKEN_INVALID` 丢弃（见 19 章）。
- 接收方**必须**把 PROBE 的**源地址:端口**绑定为该会话的发送方端点；
  之后**只接受来自该端点**的数据包。发送方**必须**只接受来自接收方端点的 ACK。
- 端点由 Server 经 `peer_accept` 下发（见 06 章）；PROBE 不改变端口。
- **R1 预选中转不使用 peer PROBE**：它沿用标准 upload/download 的 PROBE 与端点规则。

### R2 会话内中转（relay_r2，规范性）

`transport = relay_r2` 时，Server 在同一 peer 会话内转发数据：C1 → S → C2。

- **中转端点**：Server 为本会话分配 `relay_udp_port` / `relay_tcp_port`，
  经 `peer_accept` / `peer_transport_switch` 下发（见 06 章）。
- **UDP**：
  - C1 向 S 的中转端点发送 peer PROBE（携带 `session_id` + `transfer_token`）；
    S 校验 token / session / 源地址后回 ACK。
  - C1 的数据包发往 S；S **必须**校验 token/源地址后转发到 C2 声明的接收端点。
  - C2 **只接受**来自 S 中转端点的数据；旧端点（直连对端）上的包**必须**丢弃。
- **TCP**：C1 连接 S 的中转 `tcp_port` 并发送 `FLAG_BIND`；S 作为连接方连接 C2 的
  `tcp_port` 并发送 `FLAG_BIND`。两条 leg 分别校验会话、角色、源地址与 token。
- **不存整文件**：S 只需**有界转发队列**；队列溢出/丢包由 C2 的 `missing_chunks`
  驱动 C1 重传，可靠性模型不变。
- **K 与分片**：两段链路 MTU 可能不同，S **应当**把转发载荷规范化为 `K = 1`
  （或按其配置重新分段）；direct 模式的 `K_nofrag`/信任模式策略**不**直接套用到 relay 两段。
  `max_ok_payload` 按 leg 分别反馈。
- **容量**：S **必须**做中转入量控制（连接数、队列、带宽）；不足时**不得**建立/切换 R2，
  以 `PEER_RELAY_UNAVAILABLE` 拒绝或保持 direct。
- **切换**：由 `peer_transport_switch` 完成；切换后按新端点重新绑定，
  接收方保留位图/临时文件，从第一个缺失 symbol 继续（见 06、13 章）。

### 端口与地址绑定（规范性）

- Server 的数据面 socket **必须**绑定 accept 消息中下发的 `udp_port`。
- Server **必须**以 PROBE 报文的**源地址:端口**作为该会话的对端数据面地址；
  Server 不得向未经 PROBE 确认的地址发送数据面数据包（见 20 章）。
- Server 返回的 PROBE_ACK **必须**从该会话的数据面端口发出，
  以保证客户端的 NAT 映射命中。

### 接收方 socket 生命周期（规范性）

「接收方」指持有位图与临时文件的一方（上传方向为 Server，下载方向为 Client）。
**两个方向的接收方都必须有数据面 socket** —— 下载方向更是**强制**的：
Server 不得向未经 PROBE 确认的地址发送数据（见 20 章），
因此 **Client**（下载的接收方、上传的发送方）必须主动发出 PROBE；Server 监听并应答。

- **打开时机**：Client **必须**在发出 PROBE（TCP 降级方向：建立 TCP 数据面连接）
  **之前**打开数据面 socket；**不得**在 PROBE 发出后再去打开
  （否则 PROBE 的源端口与后续接收端口不一致，对端将把数据发往错误地址）。
  - 在**主动投递**场景下（见 09 章），接收方在收到 `delivery_offer` 并接受后
    **必须**按本节打开 socket 并发出 PROBE；拒绝则**不得**发出 PROBE。
  - socket **打开失败**（如端口被占用、无可用端口）时按 `BIND_FAILED` 记录
    （见 19 章），并**必须**放弃该次数据面建立。
- **端口来源**：Client **不必**绑定固定端口，其数据面端口通常为**临时端口**，
  由对端从 PROBE 报文的源地址:端口学到。
  多个会话**可以**共用同一个接收方 socket（`session_id` 用于区分，见 08 章）。
- **保持打开**：接收方**必须**保持该 socket 打开，
  **直到**该会话的数据面通道结束。
- **结束判据**：数据面通道的结束**必须**由**控制面**的状态表达 ——
  会话进入 `COMPLETED` 或 `ABORTED`（见 10 章）。
  接收方**不得**仅凭「位图已全真」就关闭 socket：
  位图全真只表示「文件已收齐」，而对端可能仍有在途数据，
  或仍在等待裁决、准备补发。
- **关闭前的义务**：成功提交后必须持久化完成回执；数据面可关闭，
  回执及 `complete_ack` 只走控制面，断线不影响再次交付（见 13 章）。
  因 `session_abort` 终止时无需发布成功回执。共享 socket 仅在无其他会话使用时关闭。
- **TCP 降级方向**：Client **必须**在 TCP 数据面连接建立后**立即**发送
  `FLAG_BIND` 绑定帧（见下），且该连接**必须**保持到会话进入终态；
  连接中断时**必须**按 13 章走恢复流程，**不得**直接视为数据面通道结束。

### 超时

- Client 等待 PROBE_ACK 超时（建议 2s）则判定 UDP 不可用
  （按 `TIMEOUT_PROBE` 记录；判定结果为 `UDP_UNAVAILABLE`，见 19 章）
- 回退到 TCP；降级通道本身出错（如连接被拒、帧同步失败）按 `TCP_ERROR` 记录

## TCP 降级

> **术语澄清**：本节的「TCP 通道」指**数据面**的降级通道，
> 与**控制面**的 TCP 长连接（见 06 章）**完全无关** ——
> 二者是不同的通道、不同的端口、不同的消息。

- UDP 不可用或异常时启用
- 保持 chunk 与 bitmap 语义
- **TCP 通道的线路格式见本章「TCP 数据面线路格式」**：
  帧边界、绑定与权限校验均**必须**与 UDP 通道语义一致
- TCP 端口由 accept 消息的 `tcp_port` 字段下发；**`tcp_port = 0` 表示不支持 TCP 降级**，
  此时探测失败即判定传输不可用

## TCP 数据面线路格式（规范性）

### 帧结构（小端序）

TCP 是字节流，**必须**有帧边界；且 TCP 已提供字节流校验，
因此 TCP 数据面帧**不重复载荷级** CRC32（与 06 章控制帧同理）；
但帧头**必须**携带 `magic` 与 `header_crc32`（见 06 章「帧格式」与「帧同步与失步处理」）。

| 字段 | 偏移 | 大小 | 类型 | 说明 |
|------|------|------|------|------|
| magic | 0-3 | 4 | u32 | 协议魔数，固定 `0x574E414C`（"LANW"），与控制帧同一常量 |
| frame_len | 4-7 | 4 | u32 | 本帧总字节数（含本帧头） |
| header_crc32 | 8-11 | 4 | u32 | 帧头校验码，见下 |
| session_id | 12-19 | 8 | u64 | 会话 ID；与 UDP 通道同一取值域 |
| chunk_id | 20-23 | 4 | u32 | 逻辑块序号（从 0 开始） |
| chunk_symbol | 24-25 | 2 | u16 | `chunk_id` 块内的 symbol 起始索引 |
| flags | 26-27 | 2 | u16 | 标志位（取值见 08 章；bit6 = FLAG_BIND） |
| payload | 28.. | N | bytes | 文件数据（`K` 个 symbol） |

```
FRAME_HEADER_SIZE = 4 + 4 + 4 + 8 + 4 + 2 + 2 = 28 字节
```

**帧头校验码（规范性）**：`header_crc32` 使用 **CRC-32/ISO-HDLC**
（与 08 章 `crc32`、06 章 `header_crc32` **同一变体**），
覆盖帧头中**除 `header_crc32` 字段自身之外**的 **24 字节**，按下列顺序拼接：

```
magic(4) ‖ frame_len(4) ‖ session_id(8) ‖ chunk_id(4) ‖ chunk_symbol(2) ‖ flags(2)
```

- 上式对应帧内的**两段连续区间**：字节 `0–7` 与字节 `12–27`；
  实现可直接对这两段拼接后的 24 字节计算 CRC32。
- `magic` 在线路上的**四个字节**为 `4C 41 4E 57`（"LANW"，小端序），与控制帧一致。

**帧长核算（规范性）**：

```
frame_len = 28 + L        // L 为载荷长度，由 frame_len 反推
```

- `magic` **必须**为 `0x574E414C`；不匹配即判定**失步**（见下）。
- `frame_len` **必须** ≥ **28**
- 接收方**必须**按 `frame_len` **读满**后再解析：
  **不得**假设一帧一次 `recv` 到达；**不得**按换行或任何字节模式切分。
- 载荷长度 `L = frame_len − 28`，**必须** > 0（`FLAG_BIND` 除外）；
  DATA 帧的 `chunk_symbol + K ≤ S`、长度对齐与末块规则与 08 章**完全一致**
  （`K = ceil(L / symbol_size)`）。不符不得写盘或标位，并关闭该数据连接。
  代号不匹配但边界合法的 DATA 只丢帧；`FLAG_BIND` 使用零载荷（`L = 0`，
  `chunk_symbol = 0`），不适用文件块长度公式。
- **不携带载荷级 CRC32**：TCP 提供字节流校验与可靠重传，
  TCP 数据面帧**不**携带 `crc32` —— 载荷完整性由 TCP 自身保证。
  帧头的 `header_crc32` **不是**载荷校验，而是**帧同步**手段。

### 失步处理（规范性）

接收方**必须**按下列顺序校验帧头，任一不通过即判定**失步**：

1. `magic` == `0x574E414C`；
2. `header_crc32` 校验通过；
3. `frame_len` ∈ `[28, 28 + chunk_size]`。

**失步的处置（规范性）**：

- 失步**必须**导致：**丢弃**该连接上尚未解析的全部数据、**关闭该 TCP 数据面连接**，
  并以 PROTOCOL 类错误码记录（`MAGIC_MISMATCH` / `HEADER_CRC_INVALID` /
  `FRAME_LEN_INVALID`，见 19 章）。
- 失步后**不得**在该连接上继续解析任何帧，**不得**继续写入位图。
- 该会话**必须**按 13 章走恢复流程（由控制面重新裁决缺失块后重传）。
  **不得**在失步的连接上「跳过一帧继续解析」——
  被跳过的帧中**可能**含 `FLAG_BIND` 绑定帧或数据块，
  继续解析会让接收方对「哪些块已收到」的认知与对端分叉。
- 数据面 TCP 通道的**块级自愈**能力来自位图与缺失裁决（见 12 章），
  而非帧内重同步。

**与 06 章接收状态机的关系（规范性）**：
数据面 TCP 通道**必须**采用与 06 章「接收状态机」**相同**的三态
（`SYNC` / `RESYNC` / `CLOSED`）与**相同**的三项校验顺序。
差异仅在于：

| 项 | 控制面（06 章） | 数据面 TCP（本章） |
|----|-----------------|------------------|
| 帧体内容 | 消息体（定长区 + 变长区） | chunk 载荷 |
| `frame_len` 上界 | `max_frame_len`（1 MiB） | `28 + chunk_size` |
| 失步后的数据处置 | 丢弃未解析数据 | 丢弃未解析数据，且**不得**写入位图 |
| 恢复路径 | 13 章「断线重连」（`login` / `login_ack` 权威快照） | 13 章恢复流程，由控制面重新裁决缺失块后重传 |
| 候选判据 / 扫描上限 | 见 06 章 | 同 06 章（同一 `resync_max_scan`） |

### 绑定帧（FLAG_BIND）

TCP 数据面连接**不**承载认证凭据，其权限**必须**通过绑定建立。

- **连接方向**：upload/download 中 **Server 监听、Client 连接**；
  `direction = peer` 中由**接收方**（`receiver_device_id`）监听 `tcp_port`、
  **发送方**连接。无论哪种，连接方**必须**先发送一个**绑定帧**：
  `flags` 置位 `FLAG_BIND`（bit6）、**未**置位 `FLAG_DATA`，
  载荷长度 `L = 0`、`chunk_symbol` = 0，`session_id` 为待绑定会话。
  - 绑定帧**必须**是连接上的**第一条**数据面帧（**首帧锚点**）；
    绑定完成前**不得**发送任何其他数据面帧。
  - 连接方**必须**在绑定帧发出后**保持连接打开**，直到会话进入终态。
- Server **必须**校验收到的**首帧**：若首帧不是 `FLAG_BIND` 绑定帧，
  或首帧的 `magic` / `header_crc32` / `frame_len` 校验不通过，
  **必须**关闭该 TCP 数据面连接，且**不得**发送任何数据面帧。
- Server **必须**校验：
  1. 该 `session_id` 存在且处于可传输状态（`NEGOTIATING` / `TRANSFERRING` / `PAUSED`）；
  2. 该会话的 `client_id` 与**持有该会话的控制连接**所绑定的 `device_id` 一致；
  3. 该 TCP 数据面连接的来源 IP 与该控制连接的对端 IP 一致。
  任一项不满足即**必须**关闭该 TCP 数据面连接，且**不得**发送任何数据面帧。
- 绑定成功后，该 TCP 数据面连接**只能**承载**该 `session_id`**；
  收到其他 `session_id` 的帧**必须**按 `SESSION_ID_MISMATCH` 丢弃该帧。
- **peer 模式（规范性）**：`direction = peer` 时，接收方监听、发送方连接。
  接收方**必须**校验：
  1. 该 `session_id` 存在且属于该 peer 会话；
  2. 发送方身份 = 会话的 `sender_device_id`（来自 `peer_accept` / 控制面）；
  3. TCP 连接来源 IP 与 `peer_accept` 下发的对端端点一致。
  peer **没有** C↔C 控制连接，因此**不得**套用「与控制连接绑定」的 Server 校验。
  Stage 1 只做源地址 + `session_id` 绑定；每包 keyed MAC 属 Stage 2。
- 同一会话**已有**活动的 TCP 数据面连接时，新的绑定**必须**替换旧连接
  （旧连接**必须**被关闭）—— 重连语义因此是幂等的。
- **多个会话**可以各自建立独立的 TCP 数据面连接；`session_id` 用于区分。

### 与 UDP 通道的关系

- 两条通道的**块与 symbol 语义完全一致**：`chunk_id`、`chunk_symbol`、`chunk_size`、
  `symbol_size`，字节偏移映射为
  `offset = chunk_id × chunk_size + chunk_symbol × symbol_size`。
- 两条通道的**可靠性机制一致**：位图、缺失裁决、重传优先级、
  文件级校验与原子提交（见 12 章、17 章）。
- TCP 通道**不**使用 UDP 探测；其可用性由 `tcp_port` 是否为 0 表达
  （`tcp_port` = 0 表示不支持 TCP 降级）。
