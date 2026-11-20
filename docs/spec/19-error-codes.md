# 19 错误码（Error Codes）

## 分类

| 分类 | 说明 |
|------|------|
| SESSION | 会话级错误 |
| TRANSPORT | 传输层错误（UDP/TCP） |
| INTEGRITY | 完整性校验错误 |
| AUTH | 认证与 ACL 错误 |
| TIMEOUT | 超时错误 |
| STORAGE | 持久化与文件系统错误 |
| PROTOCOL | 协议格式与状态错误 |

## 错误码上线路（规范性）

本章的错误码**必须**通过控制面消息上线路，字段映射如下：

| 消息 | 字段 | 语义 |
|------|------|------|
| `session_abort` | `reason` | 终止原因，**必填**（`str`），取值来自本章 |
| `session_abort` | `detail` | 可读补充说明（`str`），仅用于日志与 UI，**不得**用于逻辑判断 |
| `upload_complete` | `code` | 失败时的错误码（符号名，`str`）；成功时为空串（长度 0） |
| `download_complete` | `code` | 失败时的错误码（符号名，`str`）；成功时为空串（长度 0） |
| `asset_recall_complete` | `code` | 未删除时的错误码（符号名，`str`）；成功删除时为空串（长度 0） |

- 发送方与接收方**必须**按错误码做分支判断，**不得**解析 `detail` 自由文本。
- `result` 字段只表达「成功 / 失败」，**不承载**错误码；
  `code` / `reason` 字段**必须**是本章中定义过的标识符。
- **未列在本章的错误码**一律视为 `UNKNOWN_ERROR`。

## 建议错误码

### SESSION

- `SESSION_NOT_FOUND`：会话不存在或已终止
- `SESSION_ABORTED`：会话被服务端终止
- `FILE_NOT_FOUND`：请求的文件在 Server 上不存在或不可拉取
  （含共享清单条目已被移除的情形）；Server **必须**以 `session_abort` 拒绝
- `DELIVERY_DECLINED`：接收方拒绝该次主动投递
  （策略、配额或用户决定）；经 `delivery_response.code` 表达，
  Server **必须**以 `session_abort`（`reason` = `DELIVERY_DECLINED`）终止会话
- `INVALID_STATE`：当前状态不允许该操作
- `TOO_MANY_SESSIONS`：单条控制连接上的并发会话数已达上限
  （`max_sessions_per_connection` = 64，见 09 章）；
  Server **必须**以 `session_abort`（`reason` = `TOO_MANY_SESSIONS`）拒绝该请求

### TRANSPORT

- `UDP_UNAVAILABLE`：UDP 探测失败
- `TCP_ERROR`：TCP 数据面降级通道错误
- `BIND_FAILED`：数据面端口绑定失败
- `CONNECTION_FAILED`：控制通道连接失败
- `CONNECTION_CLOSED`：控制连接已关闭（对端断开或超时）
- `NETWORK_ERROR`：网络错误

### INTEGRITY

- `CRC32_INVALID`：包级校验失败（丢弃该包，不标记位图）
- `FILE_HASH_MISMATCH`：文件级内容哈希不一致（**必须**按恢复阶梯处理：
  摘要对帐 → 复核轮 → 仍失配才以 `session_abort` 终止会话，见 12 章）
- `SOURCE_FILE_MISMATCH`：发送方的源文件与请求的 `file_hash` 不符
  （摘要对帐的**根区间**摘要双方一致时判定，见 12 章）；
  接收方**必须**以 `session_abort` 终止会话，**不得**再进入复核轮
- `INVALID_CHUNK`：chunk_id 越界或非法
- `CHUNK_ALREADY_RECEIVED`：重复 chunk（幂等丢弃）

### AUTH

- `ACL_DENY`：ACL 拒绝访问
- `CLIENT_ID_INVALID`：client_id 非法
- `LOGIN_FAILED`：登录认证失败
- `PROTO_VERSION_UNSUPPORTED`：协议版本不受支持（见 06 章 `login` / `login_ack`）
- `FILE_TOO_LARGE`：声明的文件大小超出该会话 `chunk_size` 可表示的上限
  （见 09 章「文件大小上限」）；Server **必须**以 `session_abort`
  （`reason` = `FILE_TOO_LARGE`）拒绝该请求，且**不得**创建会话

### TIMEOUT

- `TIMEOUT_NO_ACTIVITY`：长时间无活动导致超时（会话级，60 秒）
- `TIMEOUT_PROBE`：UDP 探测超时
- `TIMEOUT_HEARTBEAT`：控制连接心跳超时（30 秒无任何消息，见 06 章）

### STORAGE

- `DATABASE_ERROR`：持久化失败（位图 / 会话元数据落盘）
- `STORAGE_FULL`：接收方存储空间不足，无法容纳投递的文件；
  经 `delivery_response.code` 表达
- `FILESYSTEM_ERROR`：文件系统操作失败

### PROTOCOL

- `MAGIC_MISMATCH`：帧头魔数不匹配，判定**失步**
  （控制面与 TCP 数据面帧的 `magic` 均为 `0x574E414C`；见 06、07 章）
- `HEADER_CRC_INVALID`：帧头 CRC32（CRC-32/ISO-HDLC）校验失败，判定**失步**
  （见 06、07 章「帧头校验码」）
- `FRAME_LEN_INVALID`：帧长越界（`frame_len` < 帧头长度或 > `max_frame_len`），
  判定**失步**；读取指针无法可信推进
- `INVALID_PACKET`：数据包格式非法（长度不足、越界等）
- `SESSION_ID_MISMATCH`：session_id 不匹配
- `SERIALIZATION_ERROR`：控制帧解码失败（定长区长度不足、变长区越界、取值违反约束等）
- `CONTROL_ERROR`：控制面错误
- `UNKNOWN_ERROR`：未分类错误

## 终止类与过程类（规范性）

错误码按**是否可作为会话终止原因**分为两类：

| 类别 | 含义 | 可否作为 `session_abort.reason` / 完成消息 `code` |
|------|------|------------------------------------------|
| **终止类** | 表示会话**本身**无法继续（会话被终止） | **可以** |
| **过程类** | 表示传输过程中的**局部**异常；会话**未必**终止 | **不可以** —— **必须**只记录到日志 / 指标 |

**终止类错误码清单（规范性）**：
`SESSION_NOT_FOUND`、`SESSION_ABORTED`、`FILE_NOT_FOUND`、`DELIVERY_DECLINED`、
`INVALID_STATE`、`TOO_MANY_SESSIONS`、`FILE_HASH_MISMATCH`、`SOURCE_FILE_MISMATCH`、
`ACL_DENY`、`CLIENT_ID_INVALID`、`LOGIN_FAILED`、`PROTO_VERSION_UNSUPPORTED`、
`FILE_TOO_LARGE`、`TIMEOUT_NO_ACTIVITY`、`DATABASE_ERROR`、`STORAGE_FULL`、
`FILESYSTEM_ERROR`。

**其余错误码一律为过程类**，即：
`UDP_UNAVAILABLE`、`TIMEOUT_PROBE`、`TCP_ERROR`、`BIND_FAILED`、
`CONNECTION_FAILED`、`CONNECTION_CLOSED`、`NETWORK_ERROR`、
`TIMEOUT_HEARTBEAT`、`CRC32_INVALID`、`INVALID_CHUNK`、
`CHUNK_ALREADY_RECEIVED`、`INVALID_PACKET`、`SESSION_ID_MISMATCH`、
`SERIALIZATION_ERROR`、`MAGIC_MISMATCH`、`HEADER_CRC_INVALID`、
`FRAME_LEN_INVALID`、`CONTROL_ERROR`、`UNKNOWN_ERROR`。

**约束（规范性）**：

- 过程类错误码**不得**作为 `session_abort.reason` 或完成消息 `code` 上线路；
  会话因过程类错误而结束时，**必须**以**终止类**错误码说明终止原因
  （如传输层反复失败导致会话超时 → `TIMEOUT_NO_ACTIVITY`）。
- **为何要区分（说明）**：过程类错误描述的是**传输链路**的状态，
  而 `session_abort.reason` 描述的是**会话为何终止**。
  把 `NETWORK_ERROR` 当作终止原因上线路，会让对端误以为「文件有问题」，
  实际只是「链路抖了一下，会话超时被清理了」。
- 失步类错误（`MAGIC_MISMATCH` / `HEADER_CRC_INVALID` / `FRAME_LEN_INVALID`）
  属过程类：它们导致**连接**关闭，会话进入 13 章「中断处理」，
  **不是**会话的终止原因。

## 行为

- 错误记录日志
- INTEGRITY 错误包直接丢弃，且**不得**写入位图
- SESSION 错误触发 `session_abort`（`reason` 填对应错误码）
- CHUNK_ALREADY_RECEIVED 属幂等情形，静默丢弃即可
- 同一错误不得导致状态机进入非法状态
- **失步类错误**（`MAGIC_MISMATCH` / `HEADER_CRC_INVALID` / `FRAME_LEN_INVALID`）
  **必须**导致连接关闭（控制面连接或 TCP 数据面连接），
  **不得**在原连接上继续解析帧；
  受影响会话**必须**按 13 章「断线重连」恢复
- 过程类错误码**必须**记录到日志 / 指标，但**不得**作为终止原因上线路
  （见「终止类与过程类」）
