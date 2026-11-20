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

- `DATABASE_ERROR`：SQLite 持久化失败
- `STORAGE_FULL`：接收方存储空间不足，无法容纳投递的文件；
  经 `delivery_response.code` 表达
- `FILESYSTEM_ERROR`：文件系统操作失败

### PROTOCOL

- `INVALID_PACKET`：数据包格式非法（长度不足、越界等）
- `SESSION_ID_MISMATCH`：session_id 不匹配
- `FILE_ID_MISMATCH`：file_hash 不匹配
- `SERIALIZATION_ERROR`：控制帧解码失败（定长区长度不足、变长区越界、取值违反约束等）
- `CONTROL_ERROR`：控制面错误
- `UNKNOWN_ERROR`：未分类错误

## 行为

- 错误记录日志
- INTEGRITY 错误包直接丢弃，且**不得**写入位图
- SESSION 错误触发 `session_abort`（`reason` 填对应错误码）
- CHUNK_ALREADY_RECEIVED 属幂等情形，静默丢弃即可
- 同一错误不得导致状态机进入非法状态
