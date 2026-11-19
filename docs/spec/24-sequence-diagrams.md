# 24 端到端时序（TCP + UDP）

## 时序流程

### 控制连接建立

```
Client                                        Server
  |------------ TCP connect ------------------>|
  |--- login {proto_major/minor/patch,         |
  |           device_id, token, resume[]} ---->|
  |                                            |  校验认证（21 章）
  |<-- login_ack {result, code,                |
  |             proto_major/minor/patch,       |
  |             sessions[]} ------------------>|
  |                                            |
  |<=========== 会话控制消息（长连接）==========>|
```

- `login` **必须**是连接上的**第一条**消息；Server **必须**丢弃此前的任何消息。
- `login_ack.sessions` 是**权威快照**（见 13 章）。
- 图中 `{...}` 为**消息体字段名的列举**，不表示线上表示形式；
  控制帧为二进制定长布局，各字段的偏移与大小见 06 章。

### 心跳

```
  |--- ping {ts} ----------------------------->|   每 10 秒
  |<-- pong {ts} ------------------------------|
```

- 双向**必须**每 10 秒一次；**30 秒**无任何消息即关闭连接（见 06 章）。

### 会话建立

upload_start → upload_accept（含会话参数与数据面端口）

### UDP 探测

UDP_PROBE → UDP_PROBE_ACK → udp_ready

### 数据传输

Client 连续发送 UDP chunk；Server 乱序随机写盘

### 缺失统计与重传

接收方每 50ms 下发 `missing_chunks`（`mode=report`）裁决；
发送方按裁决重传缺失块（重传优先级高于新数据）

**裁决循环是发送方推进的唯一依据（规范性）**：接收方**必须**周期性下发裁决，
**即使缺失列表为空**（空 `chunk_list` = 「可以继续推进」）。
发送方在 1000ms 内未收到任何裁决时，**必须**发布
`missing_chunks`（`mode=request`）主动索要。

> **立即裁决（推荐性）**：接收方**可以**在检测到空洞的即刻下发裁决，
> 不必等待 50ms 周期（见 06 章「missing_chunks」）。

### 校验与提交

接收方校验 hash、原子重命名，发布完成消息
（上传方向 `upload_complete`，下载方向 `download_complete`）

**复核轮（文件级失配时）**

```
  |--- missing_chunks {mode=report,          |   接收方清空位图，
  |    flags.bit1=复核轮, chunks=[]} ------->|   要求全量重发
  |                                            |
  |<=============== 全量重发 =================|   发送方重新读取源文件
  |                                            |
  |                                            |   重新校验文件级 Blake3
```

- 复核轮**至多一次**；复核轮后仍失配才 `session_abort(FILE_HASH_MISMATCH)`
  （见 12 章）。

### 中断与恢复

**路径一：断线重连（连接重建）**

```
Client                                        Server
  |------------ TCP connect ------------------>|
  |--- login { ..., resume[]{session_id,       |
  |           next_chunk_id, missing_count}} ->|
  |<-- login_ack { ..., sessions[]{快照...}}   |
  |                                            |
  |=============== 继续传输 ==================>|
```

**路径二：暂停后恢复（连接存活）**

```
  |--- resume_session {session_id, ...} ------>|
  |<-- resume_ack {result, next_chunk_id,      |
  |              missing_count, udp_port} -----|
```

两条路径的语义一致：都返回**接收方**的权威续传位置与数据面端口，
都使双方回到 `TRANSFERRING`（见 13 章）。

### 下载对称

控制面一致，仅 UDP 方向互换；完成消息改由 Client 发布；
`progress_update` 的发布方同样改为接收方（Client）；
恢复提示改由 Client 提供（下载方向的接收方是 Client）。

## 状态机

状态机与合法转移以 10-state-machine 为准
