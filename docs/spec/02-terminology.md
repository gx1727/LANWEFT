# 02 术语（Terminology）

> 本章定义**协议字段与核心概念**；**消息与消息方向速查**见
> [99 章「术语表」](99-glossary.md)。两章如有出入，以本章为准。

## 基础术语

- `session_id`（u64）：会话唯一标识；控制帧、UDP 数据包与 TCP 数据面帧中
  **均以 u64 承载**（见 06、07、08、09 章）
- `file_hash`（hash32）：文件哈希；**32 字节原始 Blake3 摘要**（非十六进制串，见 06 章）
- `file_name`（str）：文件名（`u16` 长度 + UTF-8 字节）
- `size`（u64）：文件大小（字节）
- `mtime`（u64）：文件修改时间戳（UTC 秒）
- `symbol_size`（常量，**1200 字节**）：线缆与修复的最小单位；
  块内掩码、缺失上报与选择性重传**均以 symbol 为单位**（见 08、18 章）
- `chunk_size`（u32）：**逻辑块**大小（字节），**必须**是 `symbol_size` 的整数倍；
  记 `S = chunk_size / symbol_size`，**必须**满足 `1 ≤ S ≤ 64`；规范默认 **64800**（S = 54）
- `chunk_id`（u32）：逻辑块标识；从 0 开始
- `chunk_count`（u32）：总块数 = `ceil(size / chunk_size)`；
  **必须** ≤ 2³² − 1（文件大小上限，见 09 章）
- `chunk_symbol`（u16）：数据包/数据帧中**块内 symbol 起始索引**（从 0 开始）；
  字节偏移 = `chunk_id × chunk_size + chunk_symbol × symbol_size`
- `symbol_count`（u32）：总 symbol 数 = `ceil(size / symbol_size)`；
  **必须** ≤ 2³² − 1（文件大小上限，见 09 章）
- `K`：一个数据报承载的 symbol 数（`1 ≤ K ≤ K_cap`），由载荷长度推出：
  `K = ceil(L / symbol_size)`，**不单独编码**
- `S`：块内 symbol 数 = `chunk_size / symbol_size`（≤ 64），**结构上限**
- `K_nofrag`：不分片的 `K` 上限 =
  `min(S, floor(min(路径 MTU − overhead, 65507 − 16 − TRAILER_SIZE) / symbol_size))`；
  `overhead`：lv1 IPv4 **48** / IPv6 **68**，lv2/lv3 IPv4 **60** / IPv6 **80**
  （见 08、11 章）
- `K_cap`：**策略上限**，`K_nofrag ≤ K_cap ≤ S`；默认 `K_nofrag`（不分片），
  **信任模式**取 `S`（显式允许 IP 分片，见 11 章）
- `frag_loss_budget`：信任模式下整报文丢失率的建议预算（0.05%–0.1%）
- `L`：数据报载荷长度；**不**在应用头中编码，由传输层长度反推
  （UDP：`总长 − 16 − TRAILER_SIZE`；TCP 数据面：`frame_len − 28 − TRAILER_SIZE`，
  见 07、08 章）
- `TRAILER_SIZE`：数据包尾部校验/标签长度；lv1 **4**，lv2/lv3 **16**
- `security_level`（enum8）：会话安全等级，`1` = lv1（CRC32，默认）、`2` = lv2（BLAKE3 keyed MAC）、
  `3` = lv3（AEAD），见 20 章
- `security_suite`（enum8）：lv3 套件，`0` = 无、`1` = AES-256-GCM、`2` = ChaCha20-Poly1305
- `traffic_key`：lv2/lv3 的数据面密钥，由会话根秘密派生（见 20 章）
- `flags`（u16）：标志位
- `client_id`（device_id，str）：客户端设备 ID（见 23 章）

## 会话与方向

- `direction`（enum8）：会话方向，`0` = `upload`、`1` = `download`、`2` = `peer`
  —— **决定接收方与发送方的身份**（见 06 章、09 章、10 章「视角定义」）
  - `upload` / `download` 相对 **Server**；
  - `peer` 表示 **C↔C**：`sender_device_id` 与 `receiver_device_id` 都是 Client，
    数据传输不经过 Server（直连或 R2 中转）；控制消息仍经 Server 中继。
- **接收方**：持有位图与临时文件的一方；完成消息由它发布，缺失裁决由它发起
- **发送方**：发送数据的一方；上传方向为 Client，下载方向为 Server，peer 方向为
  `sender_device_id` 指向的 Client

## C↔C peer 传输

- `peer_start` / `peer_offer` / `peer_response` / `peer_accept`：C↔C 传输的握手消息，
  **全部经 Server**（没有 C↔C 的 `login`，见 06 章）
- `peer_relay_plan`：预选中转（R1）计划，返回 C1→S upload 与 S→C2 download 两段会话
- `peer_complete`：peer 会话的完成消息，**恒由接收方发布**，经 Server 中继
- `transport`（enum8）：`0` = `direct`（C1→C2 直连）、`1` = `relay_r2`（S 在会话内转发）；
  R1 **不是** peer 会话的 transport，而是两段既有会话
- `peer_transport_switch`：direct ⇄ relay_r2 的**中途切换**（S 发布，携带新端点）；
  不改变 `session_id`、方向或 generation
- `switch_reason`（enum8）：切换原因（direct 不可达/停滞、策略、direct 恢复）
- `transfer_token`（token16）：Server 为 peer 会话签发的**根秘密**；lv1 直接作为
  `probe_token`，lv2/lv3 用于派生 `probe_token` / `traffic_key`（见 07、20 章）
- `link_token`（token16）：Server 在 `login_ack` 中为**本次控制连接**签发的根秘密；
  C↔S 的 PROBE / 数据密钥由它派生（lv1 直接作为 PROBE token）
- **share grant**：`(sender_device_id, receiver_device_id, file_hash, expiry)`，
  由 Server 维护；peer 传输必须在授权范围内
- `sender_device_id` / `receiver_device_id`：peer 会话的两个 Client；
  二者都必须在线且各自绑定一条控制连接

## 状态与控制

- `bitmap`：**两级**接收进度（见 18 章）：
  - **块完成位图**：每个 `chunk_id` 1 位，表示该块**所有 symbol 均已收到**；
  - **块内 symbol 掩码**：仅对「部分收到」的块维护一个 `u64`，bit `i` = 1 表示第 `i` 个
    symbol **已收到**；`S ≤ 64` 故一个 `u64` 足够。**上报的 `received_mask` 与之同语义**。
- `window`（u32）：滑动窗口大小（**会话级在途 symbol 上限**，Server 下发，
  Client 不得修改，见 11 章）
- `connection_window`（u32）：**连接级**在途 **symbol** 上限；
  一条控制连接上所有会话的在途 symbol 数之和**不得超过**该值（见 11 章）
- `window_update`：窗口推进**信用**消息（`0x1C`）；恒由**接收方**发布，
  携带 `generation` / `received_symbols` / `max_ok_payload`（见 06、11 章）
- `received_symbols`（u32）：当前修复代号下**已收到**的不重复 symbol 数；
  与 `missing_count` 满足 `received_symbols + missing_count = symbol_count`，
  在同一代号内**单调不减**（见 06、11、18 章）
- `max_ok_payload`（u16）：接收方最近成功收到的最大载荷长度 `L`；
  发送方据此选择 `K`（见 06、11 章）
- `generation`（u8）：数据修复代号，取值对应 DATA 的 `flags.bit4–5`
  （0 初传、1 摘要对帐定点修复、2 全量复核，见 08、12 章）
- `credit_batch`（u32）：接收方下发 `window_update` 的批阈值（**symbol 数**）；
  规范取值 `clamp(window / 8, 16, 1024)` 且不超过 `window`（见 11 章）
- **在途量**：已发出但尚未被对端确认接收的 **symbol 数**；不得超过 `window`（见 11 章）
- `missing_chunks`：两级缺失上报（见 06 章）：
  - `chunks`：**完全缺失块**列表（`u32` 条数 + `u32` 数组，**必须**升序）；
  - `partial[]`：**部分缺失块**列表，每条 `chunk_id`（u32）+ `received_mask`（u64，
    bit `i` = 1 表示第 `i` 个 symbol **已收到**）；发送方取补集
    `missing = full_mask ^ received_mask` 得到待重传 symbol；
  - `missing_count`（u32）：缺失 **symbol 精确总数**；
  - 发布方恒为**接收方**（`mode=report`）；发送方发布时（`mode=request`）两级列表**必须**为空
- `mode`（enum8）：`missing_chunks` 的判别字段，`0` = `report`（报告缺失）/ `1` = `request`（索要缺失列表）
- **复核轮**：文件级校验失配后，接收方要求发送方**重新读取源文件并全量重发**的
  恢复过程；**至多一次**（见 12 章）。由 `missing_chunks.flags.bit1` 表达
- **摘要对帐**：文件级校验失配后，接收方与发送方**逐区间比对摘要**以定位
  差异区间、进而定点修复的过程；**至多一次**（见 12 章）。
  由 `reconcile_request` / `reconcile_response` 表达
- **对帐区间**：摘要对帐的比较单位，由 `(first_chunk, chunk_count)` 确定，
  以 chunk 为最小粒度（见 12 章「对帐区间」）
- **停滞**（stall）：会话处于 `TRANSFERRING`、`missing_count > 0`，
  且连续 `stall_timeout` 内没有任何此前缺失的块到达的状态（见 12 章「停滞检测与升级」）
- `stall_timeout`（常量）：停滞判定阈值，**10 秒**（见 12 章）
- `reconcile_timeout`（常量）：等待 `reconcile_response` 的超时**下限，30 秒**；
  接收方**应当**按文件规模放宽，超时按「对帐不可用」处理并转入复核轮（见 12 章）
- **定点重读**：停滞升级时接收方置 `missing_chunks.flags.bit6`，
  要求发送方重新读取源文件的对应块（不复用缓存）后重发；每会话**至多一次**（见 06、12 章）
- `missing_count`（u32）：位图中**未收到**的 chunk 总数（精确值）；
  未携带时由**存在标志位**表示（见 06 章、18 章）
- `udp_ready`：UDP 就绪通知
- `resume_session` / `resume_ack`：暂停后的会话恢复请求 / 应答（见 13 章）
- `progress_update`：传输进度更新；发布方恒为**接收方**（见 06 章）
- `session_pause`：会话暂停请求
- `file_exists`（bool，u8 编码：`0` = 假、`1` = 真）：秒传标志；
  已授权引用且既有内容校验通过时为 `1`（见 09、10 章）
- `asset_id`（str）：Server 为素材记录分配的标识（见 06 章）
- **私有素材记录**：由客户端上传产生、归属于该 `device_id` 的素材记录；
  仅归属方可拉取与撤回（见 09 章）
- **预置素材记录**：由 Server 创建、归 Server 所有的素材记录；
  构成**共享清单**，所有已认证设备均可列举与拉取，但不可撤回（见 09 章）
- **共享清单**（catalog）：Server 侧全部**预置素材记录**的集合；
  通过 `material_list` 查询、通过 `material_available` 通知变更（见 09 章）
- `seq`（u64）：共享清单条目的**单调递增**序号；
  Client 的增量水位与分页游标（见 09 章）
- **主动投递**：Server 在 Client 未请求的情况下，向在线 Client 投递文件；
  方向恒为 download，携带全套会话参数（见 09 章）

## 控制通道

- **帧**：控制通道的消息单元；`u32 magic` + `u32 frame_len` + `u32 header_crc32` +
  `u8 msg_type` + `u8 flags` + `u8 body_version` + `u8 reserved` +
  **16 字节定长帧头** + 二进制消息体；
  长度前缀，接收方**必须**读满后解析；`magic` / `header_crc32` / `frame_len`
  三项校验任一失败即判定失步并断连（见 06 章）
- **失步**（desync）：帧边界不再可信的状态；控制面**必须**关闭连接并按 13 章恢复
- `max_frame_len`：控制通道单帧上限（**1 MiB**，见 06 章）
- **权威快照**：`login_ack.sessions` 或 `resume_ack` 携带的会话状态，
  用于同步会话参数，不覆盖接收方持久化位图与提交阶段（见 13 章）
- `ping` / `pong`：心跳与心跳应答，周期 10 秒，空闲超时 30 秒（见 06 章）

## 流控参数（发送端本地）

- `burst_size`（u32）：发送批次大小；初值 = `min(256, window)`，范围 `[min(64, window), window]`
- `batch_gap_us`（u32）：批间隔（微秒）；初值 2000，范围 `[0, 100000]`

> `burst_size` 与 `batch_gap_us` 是**发送端本地策略参数**，
> **不**是协议层参数；不同实现**可以**采用不同取值（见 11 章）。
