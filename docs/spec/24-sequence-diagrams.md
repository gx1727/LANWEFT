# 24 端到端时序（TCP + UDP）

## 时序流程

### 控制连接建立

```
Client                                        Server
  |------------ TCP connect ------------------>|
  |--- login {proto_major/minor/patch,         |
  |           max_security_level, suite_mask,  |
  |           device_id, token, resume[]} ---->|
  |                                            |  校验认证（21 章）/协商安全等级（20 章）
  |<-- login_ack {result, code,                |
  |             proto_major/minor/patch,       |
  |             link_token, sessions[]} ------>|
  |                                            |
  |<=========== 会话控制消息（长连接）==========>|
```

- `login` **必须**是连接上的**第一条**消息；Server **必须**丢弃此前的任何消息。
- `login_ack.sessions` 是**权威快照**（见 13 章）。
- `login_ack.link_token` 是**本次控制连接**的 PROBE / 数据密钥根秘密；重连后更换，
  恢复会话**必须**用新 token 重新 PROBE（见 07、13、20 章）。
- 每个会话的安全等级/套件在 accept 类消息中下发；**默认 lv1**（见 20 章）。
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

### 缺失统计、信用与重传

窗口推进由**信用**驱动：接收方在收到新块时下发 `window_update`
（`received_symbols`，事件驱动，阈值 `credit_batch`）；
当本会话**存在缺失**时，接收方每 50ms 下发 `missing_chunks`（`mode=report`）裁决；
发送方据此推进窗口并重传缺失块（重传优先级高于新数据）。

**推进依据是信用（规范性）**：窗口推进由 `window_update.received_symbols`
（或 `missing_chunks.missing_count`）驱动，二者在同一代号内**必须**一致；
缺失列表为空时**不**要求周期下发。发送方在 **1000 ms** 内未收到任何信用时，
**必须**发布 `missing_chunks`（`mode=request`）主动索要。

> **立即裁决（推荐性）**：接收方**可以**在检测到空洞的即刻下发裁决，
> 不必等待 50ms 周期（见 06 章「missing_chunks」）。

### 校验与提交

接收方校验 hash、原子重命名，发布完成消息
（上传方向 `upload_complete`，下载方向 `download_complete`）

数据发送方持久化结果后回复 `complete_ack`。以下为断线互操作验收条件（见 13 章）：

| 断线点 | 重连后的可观察结果 |
|--------|--------------------|
| 上传已提交，Client 未收到 `upload_complete` | Server 重发同一结果和 `asset_id`；素材记录仍只有一条，不重传文件 |
| 下载已提交，Server 未收到 `download_complete` | Client 不恢复数据面；登录后重发原回执，Server 记录后应答 |
| 完成结果已记录，但 `complete_ack` 未到达接收方 | 再次交付只产生确认，不重复提交、建记录或触发完成业务 |

**互操作边界用例**（上传与下载共用的数据规则须在两个方向验证）：

| 输入或事件 | 必须观察到的结果 |
|------------|------------------|
| 下载已提交，Server 未收到回执，离线超过 60 秒再登录 | 超时只释放传输资源，结果仍未知；Server 接受原成功回执并确认，不重开传输 |
| 定点修复切到代号 1，或全量复核切到 2；旧代 DATA 先于新代抵达 | 旧包不写盘、不标位；新代正确块仍能写入并通过最终哈希 |
| 复核已收 60/100 块时断线 | 恢复报告为代号 2、`missing_count=40`；发送方 `S=R=60`，不再清位重启整轮 |
| 投递的 `chunk_count` 与文件大小不符 | Client 拒绝并诊断 `SERIALIZATION_ERROR`；Server 以 `DELIVERY_DECLINED` 终止 |
| 重连快照给出端口 A，随后暂停恢复给出 B | 从 B 重新探测；迟到的 A 就绪通知无效，双方不再用旧绑定发 DATA |
| `size=2500, chunk_size=1200` | 块 0/1/2 长度只能为 1200/1200/100；UDP 和 TCP 对非末短块均不写盘、不标位 |

**摘要对帐（文件级失配时，恢复阶梯第 ① 级）**

```
  |--- reconcile_request {ranges=[根区间]} -->|   接收方发起
  |<-- reconcile_response {digests[]} --------|   发送方返回该区间的摘要
  |                                            |   接收方用临时文件同区间摘要比对
  |--- reconcile_request {ranges=[左半,右半]}>|   逐层二分，每层一次往返
  |<-- reconcile_response {digests[]} --------|
  |                                            |   可疑块 → 清零位图
  |--- missing_chunks {mode=report, 可疑块} ->|   复用既有裁决机制定点补发
  |=============== 定点补发 =================|
```

- 根区间摘要**一致** → 双方内容相同 → 请求的 `file_hash` 有误 →
  `session_abort(SOURCE_FILE_MISMATCH)`，不再进入复核轮
- 对帐后仍失配 → 进入复核轮（恢复阶梯第 ② 级）

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
都使会话回到**可传输状态**（见 13 章）。
断线重连后**各视角各自回到断线前状态** —— `PAUSED` 保持 `PAUSED`，
`VERIFY` / `COMMIT` 的接收侧回到原状态（见 13 章「待恢复会话的判定」）。

### 主动投递（Server → Client，无客户端请求）

```
Client                                        Server
  |                                            |  Server 生成 session_id 与全套会话参数
  |<-- delivery_offer {session_id, 参数, -------|  创建会话（NEGOTIATING）
  |    file_hash, file_name}                    |
  |                                            |
  |    接收方决策（策略 / 配额 / 用户）          |
  |--- delivery_response {result=success} ----->|  接受
  |    （result=fail + code 即拒绝）             |
  |                                            |
  |-- UDP: PROBE (从接收方数据面 socket) ------>|  Server 在此学到接收方地址
  |<-- UDP: PROBE_ACK (从 Server 数据面端口) ---|  打通 NAT 映射
  |<========== UDP 数据面推送 ==================|
  |--- download_complete ---------------------->|  接收方发布完成消息
```

- Server **必须**等到 PROBE 才可推送（20 章）
- 方向恒为 **download**：完成消息恒由接收方发布
- 传输过程与普通下载**完全一致**（位图 / 裁决 / 恢复 / 提交全部复用）

### 共享清单与拉取（预置素材）

```
Client                                        Server
  |--- material_list {since_seq=0} ----------->|   查询共享清单
  |<-- material_list_ack {entries[], 末批} ----|   分批返回，seq 单调递增
  |                                            |
  |    （Server 预置新素材时可主动通知）        |
  |<-- material_available {entries[]} ---------|   至少一次，可能丢失
  |                                            |
  |--- download_start {file_hash, ...} ------>|   复用既有下载流程
  |<-- download_accept {session_id, ...} ------|   数据面 / 位图 / 裁决全部复用
  |<=========== UDP 数据面传输 ================|
  |--- download_complete ---------------------->|   接收方发布完成消息
```

- 通知**不保证送达**：Client **必须**另行查询 `material_list`。
- 拉取路径**不引入任何新机制** —— 与普通下载完全一致。

### 下载对称

控制面一致，仅 UDP 方向互换；完成消息改由 Client 发布；
`progress_update` 的发布方同样改为接收方（Client）；
恢复提示改由 Client 提供（下载方向的接收方是 Client）。

### C↔C peer（直连，Stage 1）

```
C1（发送方）              S                    C2（接收方）
  |--- peer_start ------>|                      |
  |                      |--- peer_offer ------>|
  |                      |<-- peer_response ----|   接受时含数据端口
  |<-- peer_accept ------|------ peer_accept -->|   含对端端点 / token
  |-- peer PROBE (UDP, transfer_token) -------->|
  |<------------- PROBE_ACK --------------------|
  |=============== 直连数据 C1 → C2 ===========|
  |                      |<-- missing_chunks ---|   控制经 S 中继
  |<-- missing_chunks ---|                      |
  |                      |<-- peer_complete ----|
  |<-- peer_complete ----|                      |
  |--- complete_ack ---->|------ complete_ack ->|
```

- 拉（C2 发起）：C2 `peer_start`（`mode = pull`）→ S `peer_offer` 给 C1 →
  C1 `peer_response` → S `peer_accept` 双方；后续相同。
- **没有 C↔C 的 `login`**：两端各自保持与 S 的既有 `login` 控制连接。
- 缺失/信用/进度/完成全部经 S 中继；数据面不经 S。

### C↔C peer（R1 预选中转，Stage 1）

```
C1 --- peer_start ---> S --- peer_offer ---> C2
C1 <-- peer_relay_plan --- S --- peer_relay_plan --> C2
C1 <-- upload_accept ---- S ---- download_accept --> C2
C1 ===== upload =======> S ===== download =======> C2     （S 存储）
S publishes upload_complete -> C1；C2 publishes download_complete -> S
```

- R1 是**两段既有会话**，由一个 `transfer_id` 关联；不建立 `direction = peer` 数据面。
- Server **必须**建立临时中转素材/授权，使 C2 能合法下载；完成后回收。
- 直连 PROBE 失败时由 Server 决定走 R1 或 **R2 会话内中转**。

### C↔C peer（R2 会话内中转，S 转发）

```
C1（发送方）              S                    C2（接收方）
  |--- peer_start ------>|                      |
  |                      |--- peer_offer ------>|
  |                      |<-- peer_response ----|
  |<-- peer_accept ------|------ peer_accept -->|   transport=relay_r2, 端点为 S 中转
  |-- peer PROBE（到 S 中转端点, token）------->|
  |<------------- PROBE_ACK --------------------|
  |===== data =========>|===== data ==========>|   S 只在会话内转发，不存整文件
  |                      |<-- missing_chunks ---|   控制经 S 中继
  |<-- missing_chunks ---|                      |
  |                      |<-- peer_complete ----|
  |<-- peer_complete ----|                      |
```

- S 必须校验两段 leg 的 token/源地址；C2 只接受 S 中转端点。
- S 只保有界转发队列；丢失由 C2 的缺失裁决驱动 C1 重传。
- K 由 S 规范化（建议 `K = 1`），direct 的 K 策略不直接套用。

### 会话内 transport 切换

```
S -- peer_transport_switch (direct → relay_r2) --> C1 / C2
C1/C2：停用旧端点 → 清空在途/重建信用基线 → 保留位图/临时文件 → 按新端点重绑定
S -- peer_transport_switch (relay_r2 → direct) --> C1 / C2    （direct 恢复后，带迟滞）
```

- 切换**不改变** `session_id` / 方向 / generation / 会话状态。
- 未完成重绑定的会话由 Server 以 `PEER_RELAY_UNAVAILABLE` / `TIMEOUT_NO_ACTIVITY` 终止。

## 状态机

状态机与合法转移以 10-state-machine 为准
