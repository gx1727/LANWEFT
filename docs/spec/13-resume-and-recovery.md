# 13 中断与恢复（Resume & Recovery）

## 中断处理

- 可随时中断
- 保留已写入与位图
- 中断不回滚已写入数据
- **控制连接断开时，其上承载的全部会话一并进入中断**（见 09 章）
- **帧失步**导致的断连（见 06、07 章「帧同步与失步处理」）同样属于
  **断线重连**路径：失步的连接**不得**就地续解，
  恢复一律经 `login` / `login_ack` 的**权威快照**重建

## 恢复的两条路径（规范性）

| 路径 | 触发条件 | 消息 | 权威状态载体 |
|------|---------|------|-------------|
| **断线重连** | 控制连接断开后重新建立 | `login`（恢复列表） → `login_ack` | `login_ack` 的 `sessions[]` 快照记录 |
| **暂停后恢复** | 会话处于 `PAUSED`，连接仍存活 | `resume_session` → `resume_ack` | `resume_ack` |

两条路径的语义**一致**：都返回接收方的权威续传位置与数据面端口，
都使会话回到**可传输状态**。区别只在于**是否需要重建连接**。

> **恢复后的状态（规范性）**：恢复后**各视角各自回到断线前的状态**
> （共享状态按快照，接收方本地校验与提交阶段按持久化记录，见「数据传输的恢复判定」）。
> 「暂停后恢复」路径**必须**回到 `TRANSFERRING`（该路径的前提就是解除暂停）；
> 「断线重连」路径则**必须**按上表处理 ——
> `PAUSED` 保持 `PAUSED`，`VERIFY` / `COMMIT` 的接收侧回到 `VERIFY` / `COMMIT`
> （发送侧**没有**这两个状态，回到 `TRANSFERRING`）。

## C↔C peer 会话的恢复（Stage 1）

- peer 会话横跨两条控制连接。**任一端断开**时 Server **必须**：
  1. 把该 peer 会话置为**中断**（保留位图/临时文件与 generation，**可恢复**）；
  2. 向**仍在线的另一端**经其**现有**控制连接发布 `session_pause`
     （`session_id` 为该 peer 会话），作为「对端掉线、会话中断」的**通知**；
     在线端收到后**必须**停止数据面发送、保留位图/临时文件，进入中断态。
- **在线端不重复 `login`（规范性）**：在线端的控制连接**未**断开，
  **不得**、也无须重新握手；它仅依据 Server **重发**的 `peer_accept` 重建数据面端点与信用基线。
- **中断的解除（规范性）**：peer 中断**不**通过 `resume_session` / `resume_ack` 解除 ——
  当**两端都重新在线**后，Server **必须**向两端**重发** `peer_accept`
  （含最新端点、`transfer_token`、`security_level` / `security_suite`）；
  双方**必须**重新 peer PROBE 并按原安全等级重新派生 `traffic_key`，
  位图/临时文件**必须**保留，续传起点仍是第一个缺失 symbol。
  这与「显式 `session_pause` 经 `resume_session` / `resume_ack` 解除」是
  **两条不同的恢复路径**（见 10 章「暂停与恢复」）：对 `direction = peer` 的会话，
  由 Server 发布的 `session_pause` **仅**用于上述中断通知，不再叠加显式暂停语义。
- 每个设备的 `resume[]` **必须**只包含它在其中担任 sender 或 receiver 的 peer 会话；
  `login_ack.sessions[]` 的 `state`/参数按该设备视角返回；
  断开的另一端重连时按一次正常 `login` 恢复（peer 会话**没有** C↔C 的 login）。
- 恢复后数据端点可能变化：Server **必须**在**两端**均恢复后，
  对每个恢复的 peer 会话向两端**重发** `peer_accept` ——
  重连端经其**新**连接、在线端经其**既有**连接各收一份。
- **安全等级不可变**：恢复的 peer 会话**必须**使用首次建立的等级/套件；
  若 Server 配置已不再允许该等级，会话**必须**失败（`SECURITY_LEVEL_UNSUPPORTED`），
  **不得**静默降级或升级。
- R1 的中转由两段既有会话组成：分别按 upload/download 恢复；
  `transfer_id` 关联两段结果。
- **会话内 transport 切换（relay_r2）**：Server 通过 `peer_transport_switch` 切换
  direct ⇄ relay_r2。双方**必须**停用旧端点、清空在途估计并重建信用基线，
  **保留**位图/临时文件，从第一个缺失 symbol 继续；`session_id`/方向/generation 不变。
  切换前 Server **必须**确认目标端点/容量可用（见 06、07 章）。
- 断线重连**不得**把 peer 会话降级为同方向的 upload/download；拓扑/角色不变，
  只重新建立端点与信用基线。

## 断线重连（连接重建）

### 恢复的两层语义（规范性）

断线重连同时涉及两件事，**必须分开判定**：

1. **数据传输的恢复**：是否继续发送/重传 symbol；由 `login.resume[]` 与
   `login_ack.sessions[]` 快照表达。
2. **结果交付的恢复**：文件已经提交，但完成回执或 `complete_ack` 尚未送达；
   由完成消息（`upload_complete` / `download_complete`）与 `complete_ack` 表达。

`COMPLETED` **不列入** `resume[]` 只表示**不再恢复数据传输**，
**不表示**可以不交付结果。结果交付不占活跃会话配额，也不能仅凭快照宣告成功
（详见「最终回执的交付」）。

### 数据传输的恢复判定（规范性）

判定以 **Client 断线前的本地视角**为准；Server 可能已经前进到 `COMPLETED`。
「待恢复」在这里仅指**数据传输**仍可继续的会话：

| 断线前（Client 本地）状态 | 列入 `login.resume[]`？ | 恢复后的数据传输状态 | 重连后谁先发 | 说明 |
|---------------------------|------------------------|----------------------|--------------|------|
| `INIT` / `NEGOTIATING` | **否** | 不恢复 | — | 未建立传输，按新会话重新发起 |
| `TRANSFERRING` | **是** | `TRANSFERRING` | **接收方**先发报告，发送方后发 DATA | 由接收方位图决定续传起点 |
| `PAUSED` | **是** | **保持 `PAUSED`** | 无数据面消息 | 断线**不解除**显式暂停；须 `resume_session` / `resume_ack` |
| `VERIFY` / `COMMIT`（仅接收方） | **是** | 接收侧回到 `VERIFY` / `COMMIT`；发送侧回 `TRANSFERRING` | 接收方按校验/提交状态继续 | 不再重传文件内容，除非复核轮明确要求 |
| `COMPLETED` | **否** | 数据传输已完成 | 无 DATA | 结果交付见下一节；**不得**仅凭快照宣告成功 |
| `ABORTED` | **否** | 终态 | — | 不可恢复（见 10 章） |

> **为何断线不解除暂停（说明）**：暂停是**显式**的用户/策略意图，
> 网络抖动**不是**解除暂停的理由。若断线即自动恢复传输，
> 「暂停」将退化为「建议」—— 用户无法保证文件在暂停期间不被继续传输。
> 因此 `PAUSED` 会话在重连后**必须**仍处于 `PAUSED`，
> 由 `resume_session` / `resume_ack` 显式恢复。

**本地视角与 Server 权威状态不一致（规范性）**：若 Client 本地仍认为
`TRANSFERRING` 而 Server 已提交完成，Server **必须**在快照中返回
`result = success`、`state = COMPLETED`、`next_chunk_id = chunk_count`、
`missing_count = 0`；这表示**数据传输不再恢复**，转入结果交付。
Client **不得**再发送 DATA，也**不得**仅凭该快照宣告成功。

**数据传输阶段的首条消息（规范性）**：登录重同步完成后，
**接收方必须先发**一条普通 `missing_chunks` 报告（`mode=report`，`bit1=0`），
携带已持久化的修复代号与精确 `missing_count`；发送方收到该报告前**不得**发送 DATA。
`PAUSED` 会话在收到成功 `resume_ack` 前同样**不得**发送 DATA。
上传方向接收方是 Server，下载 / peer 方向接收方是 Client。

### 结果交付的恢复判定（规范性）

结果交付以 `(device_id, session_id, direction)` 为键，与数据传输状态**独立**判定。
接收方在提交前持久化提交意图，提交成功后持久化完整完成消息；发送方持久化完整结果后
才回 `complete_ack`。下表列出重连后**结果层**的首条消息：

| 场景 | 接收方（完成发布方）知道 | 发送方（确认方）知道 | 数据面 | 结果交付谁先发 |
|------|--------------------------|----------------------|--------|----------------|
| 上传：Server 已提交并持久化 `upload_complete`，Client 仍以为在传输 | 文件已提交，回执待确认 | 未收到完成回执 | **不传 DATA** | **Server** 先发 `upload_complete`；Client 回 `complete_ack` |
| 上传：Client 已收到 `upload_complete`，但 `complete_ack` 丢失 | 回执待确认 | 已持久化结果，待确认 | **不传 DATA** | **Server** 重发 `upload_complete`；Client 重发 `complete_ack` |
| 下载：Client 已提交并持久化 `download_complete`，Server 未收到 | 文件已提交，回执待发送 | 未收到完成回执 | **不传 DATA** | **Client** 先发 `download_complete`；Server 回 `complete_ack` |
| 下载：Server 已收到回执并持久化，`complete_ack` 丢失 | 回执待确认 | 已持久化结果，待确认 | **不传 DATA** | **Client** 重发 `download_complete`；Server 重发 `complete_ack` |
| 下载：Server 已超时/关闭传输，Client 已完成提交 | 文件已提交，回执待发送 | 传输已关闭，结果未知 | **不传 DATA** | **Client** 先发 `download_complete`；Server 按原会话绑定持久化并确认 |
| 任意：结果已确认或无待交付 | 无 | 无 | 不传 DATA | 无结果消息；按终态处理 |

**总顺序（规范性）**：重连后**恒由 Client 先发** `login`
（即使 `resume_count = 0`，只要还有结果待交付也**必须**登录）；
Server 回 `login_ack`。随后：

1. **数据传输**：接收方先发 `missing_chunks` 报告，发送方后发 DATA；
2. **结果交付**：接收方（完成发布方）先发完成消息，发送方后回 `complete_ack`。

两者**可以同时存在**于同一次重连：先完成登录与数据面重同步，再按上表交付结果；
完成消息不塞入快照，逐条作为普通控制帧发送。

### 通用规则（规范性）
- **条目数上界（规范性）**：`resume_count` 与 `login_ack` 的 `sessions_count`
  **必须** ≤ `max_sessions_per_connection`（64，见 09 章）。
  该上界保证两者**始终可编码**：
  `resume[]` 最大 64 × 20 = **1,280 字节**，
  快照最大 64 × (42 + `code_len`) 字节，
  均**远小于** `max_frame_len`（1 MiB，见 06 章）。
  （无该上界时，`u16` 的值域将超出帧长上限 —— 65,535 × 42 字节 ≈ 2.6 MiB > 1 MiB。）
- `login` 的 `resume[]` **必须**列出全部**需要恢复数据传输**的会话；
  **仅结果交付待确认**的会话**可以**不列入（但仍必须完成 `login` 并交付结果）。
  二进制表示：定长区 `resume_count`（`u16`）给出条目数（无数据传输恢复请求时为 `0`），
  变长区按顺序给出 `resume_count` 条 **20 字节定长**记录，
  每条含 `session_id`（`u64`）/ `next_chunk_id`（`u32`）/ `missing_count`（`u32`）/
  `flags`（`u8`：bit0 = `next_chunk_id` 有效，bit1 = `missing_count` 有效）；
  `next_chunk_id` 为**块级**续传起点，`missing_count` 为**缺失 symbol 总数**。
- 续传起点来自**接收方**的位图，因此**只有接收方才可能提供**它：
  - **上传方向**（接收方 = Server）：Client **必须**不提供恢复提示
    （记录 `flags` 的 bit0 / bit1 = 0，相应字段**必须**取 `0`），
    由 Server 用**自己**的位图计算。
  - **下载方向**（接收方 = Client）：Client **必须**依据**自己的位图**提供恢复提示
    （记录 `flags` 的 bit0 / bit1 = 1）。
- Server **必须**在 `login_ack` 的 `sessions[]` 中为**每一个出现在 `resume[]` 的会话**
  给出一项，标明 `result`（`enum8`：`0` = fail，`1` = success）与 `code`
  （失败原因，见 19 章）；即使 Server 判定数据传输已完成，也**必须**返回
  `state = COMPLETED` 的快照供结果交付使用。
  二进制表示：定长区 `sessions_count`（`u16`）给出条目数，
  变长区按顺序给出 `sessions_count` 条**快照记录**，每条 =
  **42 字节定长**（`session_id`(u64) / `result`(enum8) / `direction`(enum8) /
  `state`(enum8) / `security`(enum8：bit0-1 等级，bit2-3 套件) /
  `chunk_count`(u32) / `chunk_size`(u32) / `window`(u32) /
  `connection_window`(u32) / `next_chunk_id`(u32) / `missing_count`(u32) /
  `udp_port`(u16) / `tcp_port`(u16) / `code_len`(u16)）+
  紧随其后的 `code_len` 字节内联 `code` 字符串。
- **快照的权限边界（规范性）**：Server 确定会话关联、协商参数和端口；
  只有数据接收方的持久化位图决定块是否收到。两个计数不能表示稀疏位图，
  **不得**用于重建或覆盖它。下载时 Server 必须回显 Client 提供的续传摘要；
  Client 保留本地 VERIFY / COMMIT 阶段。位图丢失且无法可靠重建时不得凭摘要续传。
- 恢复成功后，发送方**必须**丢弃恢复前推导的在途量估计并重建（见 11 章判据第 3 条）。
- **C↔S 的安全状态恢复（规范性）**：成功 `login` 的 `login_ack.link_token`
  **必须**是本次连接的新值；Client 与 Server **必须**用它重新派生 `probe_token`
  （以及 lv2/lv3 的 `traffic_key`），并对每个恢复会话重新 PROBE。
  旧连接上的 `link_token` / 数据密钥**必须**失效；旧密钥的在途包**必须**丢弃并按缺失重传。
  快照的 `security` 字节给出恢复会话的等级/套件，**必须**与断线前一致；
  若 Server 配置不再允许该等级，按 `SECURITY_LEVEL_UNSUPPORTED` 失败，**不得**静默变更。

### 上传方向（Client = 发送方，Server = 接收方）

1. Client 重连 → 发送 `login`，其 `resume[]` 记录只带 `session_id`（`u64`），
   `next_chunk_id` / `missing_count` **必须**未携带（记录 `flags` 的 bit0 / bit1 = 0，
   相应字段取 `0`）
2. Server 加载**自己**的位图 → 计算缺失 → 在 `login_ack` 的 `sessions[]` 快照记录中给出
   `next_chunk_id` / `missing_count` / `udp_port`
3. **Server（接收方）先发**一条普通 `missing_chunks` 报告（`mode=report`，`bit1=0`），
   携带持久化的修复代号与精确缺失；Client 收到后才继续发送 DATA。
   `PAUSED` 保持暂停，等待 `resume_session`；`COMPLETED` 不传 DATA，
   按「结果交付的恢复判定」等待/重发 `upload_complete`。
   （双方各自回到断线前状态；发送侧断线前不可能是 `VERIFY` / `COMMIT`）

### 下载方向（Client = 接收方，Server = 发送方）

Server **没有** Client 的位图，无从计算续传起点，
因此由 Client 在 `login` 的 `resume[]` 中提供恢复提示：

1. Client 重连 → 发送 `login`，其 `resume[]` 记录携带
   `session_id`（`u64`）/ `next_chunk_id`（`u32`）/ `missing_count`（`u32`），
   并置记录 `flags` 的 bit0 / bit1 = 1
2. Server 在 `login_ack` 的 `sessions[]` 快照记录中回填权威状态
   （含 `udp_port`、`window`、`connection_window` 与 `state`）
3. **Client（接收方）先发**一条普通 `missing_chunks` 报告（`mode=report`，`bit1=0`），
   携带持久化的修复代号与精确缺失；Server 收到后才从 `next_chunk_id` 起继续推送 DATA。
4. 双方各自回到断线前状态（发送侧 = Server 回 `TRANSFERRING`；
   接收侧 = Client 回断线前状态）；若 Client 已提交，按「结果交付的恢复判定」
   先发 `download_complete`，不再传 DATA。

### 恢复失败

`login_ack` 的 `sessions[]` 中该会话的 `result`（`enum8`）= `0`（fail），
其记录内联 `code` 字符串取值为**符号名**：

| code | 含义 |
|------|------|
| `SESSION_NOT_FOUND` | 会话不存在（Server 重启且状态已丢弃，或从未存在） |
| `SESSION_ABORTED` | 会话已进入终态（见 10 章），不可恢复 |
| `INVALID_STATE` | 当前状态不允许恢复 |

Client **必须**把 `result` = `0`（fail）的会话视为**已终止**，
**不得**继续使用其本地状态。

## 最终回执的交付（规范性）

完成交付不属于恢复数据传输。接收方以 `(device_id, session_id, direction)` 为键，
在提交前持久化提交意图（含目标、预分配的 `asset_id` 和预期哈希）。文件和素材记录提交
成功后持久化不可变的完整 `upload_complete` 或 `download_complete`，再发布回执。
进程若在提交与记录回执之间退出，必须先依据意图核对并幂等完成同一笔提交，
不得再次创建素材、分配新 `asset_id` 或在提交成功前公布成功。

- 接收方保留待交付回执直到收到对应 `complete_ack`；60 秒活动超时只回收未完成传输，
  不得清除待交付回执。回执不占活跃会话配额；存储不足时应限制新会话，而非驱逐未确认结果。
- 每次成功登录后，双方必须在各自发送 `login_ack` 或收到成功 `login_ack` 后，
  向已认证的原对端重发所有未确认回执（逐条普通控制帧，不塞入快照）。
  发送方必须持久化会话与设备、方向的绑定，直到最终结果可确认；
  传输超时本身不是对端提交失败的证明。
- 上传时，若 Client 把本地仍在传输的会话列入 `resume[]`，Server 已有成功回执，
  则快照返回 `result=success, state=COMPLETED`，`next_chunk_id=chunk_count, missing_count=0`，
  随后交付原回执。Client 不再传数据，**不得仅凭快照宣告成功**。下载时，已提交的
  Client 不将终态列入 `resume[]`，直接在握手后重发 `download_complete`。
- 数据发送方核对设备、会话与消息方向，持久化完整结果后才发 `complete_ack`；
  相同回执再次到达只重发确认，不重复业务操作。相同键但内容不一致不得覆盖既有结果或确认。
  收到确认的一方可删除待交付副本，不得因重复确认重新打开会话。

**下载超时后的结果**：发送方的传输资源与业务结果分别记账。Server 超时后停止传输，
业务结果保持「未知」（本地记录，不新增线上状态）。已认证 Client 迟到的成功或失败
`download_complete` 仍必须按原会话绑定持久化并确认，不重建数据面、不改变已关闭的传输状态。
若 Client 请求恢复已过期的下载，Server 回失败快照 `code=TIMEOUT_NO_ACTIVITY`；
无提交意图的 Client 停止传输，持久化并交付同码的失败回执。已有提交意图的 Client
必须先核实提交，交付实际结果；恢复被拒不推翻已提交的文件。

## 暂停后恢复（连接存活）

1. Client 发送 `resume_session`，其定长区携带
   `session_id`（`u64`）/ `next_chunk_id`（`u32`）/ `missing_count`（`u32`），
   并以 `flags` 存在标志位表明恢复提示是否携带
   （bit0 = `next_chunk_id` 有效，bit1 = `missing_count` 有效；
   标志位为 `0` 时该字段**必须**为 `0`）
   —— 恢复提示的方向规则与断线重连**相同**：
   上传方向**必须**不携带，下载方向**必须**携带。
2. Server 回 `resume_ack`（含 `result` / `code`、
   `next_chunk_id` / `missing_count` / `udp_port` / `connection_window`）
3. 双方回到 TRANSFERRING（该路径的前提就是解除暂停）

### resume_ack 语义

| 字段 | 语义 |
|------|------|
| `result` / `code` | 恢复是否成功（`result` 为 `enum8`，`0` = fail、`1` = success）；`code` 为 `str`，失败时的机器可判定错误码（见 19 章、06 章） |
| `next_chunk_id` | **续传顺序起点**：**接收方**位图中**第一个尚未收全的 chunk_id**；位图已全真时为 `chunk_count`（`u32`） |
| `missing_count` | **接收方**位图中尚未收到的 **symbol 总数**（精确值，`u32`） |
| `udp_port` | 数据面端口（`u16`），可能因会话重建而变化，**Client 必须使用回执中的端口** |

**`next_chunk_id` 的定义（规范性）**：**接收方**位图中**第一个尚未收全**的 `chunk_id`。

本协议显式支持乱序写与随机访问（见 01、17 章），位图可能出现**空洞** ——
存在低于最大已收 id 的缺失块。若以 `max_received_id + 1` 作为续传起点，
空洞块将**永远不会被重传**，文件级 Blake3 校验必然失配并导致会话中止。
因此续传起点**必须**是**第一个缺失块**。

## 空洞块的补发

`next_chunk_id` 只决定**顺序发送流**从哪里继续；位图中低于当前发送位置的空洞
由周期下发的 `missing_chunks`（`mode=report`）负责指认：

- 接收方**必须**在裁决中报告**全部**未收到的 symbol（完全缺失块 + 部分缺失掩码），
  而不只是从 `next_chunk_id` 开始的连续区间。
- 发送方**必须**优先重传裁决报告的缺失块，优先级高于新数据。
- 包级校验失败（`crc32`）的块同样计入「未收到」，并按本节的**定点补发**处理
  （见 12 章「缺失块的定点补发」）。

## 复核轮与恢复

- 复核轮的计数**必须**与位图一同持久化（见 09 章「持久化」）。
- 摘要对帐的计数**同样必须**持久化：恢复后**不得**因连接重建而重新获得
  一次对帐机会（见 12 章「上限」）。
- 复核轮**进行中**发生断线时，恢复后**必须**继续该复核轮，
  **不得**因连接重建而获得第二次复核轮机会。
- 暂停恢复或重连后，可传输会话的接收方须先发一条普通 report（bit1=0），携带
  已持久化的修复代号及精确 `missing_count`；发送方收到前不得发 DATA。
  发送方按该报告重建 `Sent = R = symbol_count − missing_count`，从恢复起点续传。
  若代号为 2，须重新打开源文件，但不得重新清位或从零启动第二次全量复核。
  即使启动裁决在断线前未送达，首次恢复报告也足以确定当前代号。

## 失败与清理

- 长时间未恢复可清理，删除临时文件/位图/元数据
- 清理前应确认会话已进入 ABORTED 状态
- 会话超时时长见 09 章「超时与回收」
