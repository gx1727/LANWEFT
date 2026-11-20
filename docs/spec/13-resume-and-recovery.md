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
> （以权威快照的 `state` 字段为准，见「待恢复会话的判定」）。
> 「暂停后恢复」路径**必须**回到 `TRANSFERRING`（该路径的前提就是解除暂停）；
> 「断线重连」路径则**必须**按上表处理 ——
> `PAUSED` 保持 `PAUSED`，`VERIFY` / `COMMIT` 的接收侧回到 `VERIFY` / `COMMIT`
> （发送侧**没有**这两个状态，回到 `TRANSFERRING`）。

## 断线重连（连接重建）

### 通用规则（规范性）

- **待恢复会话的判定（规范性）**：「待恢复」指断线时**处于可恢复状态**的会话，
  判定**按会话断线前的状态**（见 10 章「状态定义」）：

  | 断线前状态 | 列入 `login.resume[]`？ | 恢复后的状态 |
  |-----------|----------------------|------------|
  | `INIT` / `NEGOTIATING` | **否** | 不恢复；会话按新会话重新发起 |
  | `TRANSFERRING` | **是** | 各视角回到 `TRANSFERRING` |
  | `PAUSED` | **是** | **保持 `PAUSED`** —— 断线**不解除**显式暂停；恢复仍走「暂停后恢复」（`resume_session` / `resume_ack`） |
  | `VERIFY` / `COMMIT` | **是** | **各视角各自回到断线前的状态**（接收侧回 `VERIFY` / `COMMIT`，发送侧回 `TRANSFERRING`） |
  | `COMPLETED` / `ABORTED` | **否** | 不恢复（终态，见 10 章） |

  > **为何断线不解除暂停（说明）**：暂停是**显式**的用户/策略意图，
  > 网络抖动**不是**解除暂停的理由。若断线即自动恢复传输，
  > 「暂停」将退化为「建议」—— 用户无法保证文件在暂停期间不被继续传输。
  > 因此 `PAUSED` 会话在重连后**必须**仍处于 `PAUSED`，
  > 由 `resume_session` / `resume_ack` 显式恢复。

- **条目数上界（规范性）**：`resume_count` 与 `login_ack` 的 `sessions_count`
  **必须** ≤ `max_sessions_per_connection`（64，见 09 章）。
  该上界保证两者**始终可编码**：
  `resume[]` 最大 64 × 20 = **1,280 字节**，
  快照最大 64 × (42 + `code_len`) 字节，
  均**远小于** `max_frame_len`（1 MiB，见 06 章）。
  （无该上界时，`u16` 的值域将超出帧长上限 —— 65,535 × 42 字节 ≈ 2.6 MiB > 1 MiB。）
- `login` 的 `resume[]` **必须**列出全部待恢复的会话。
  二进制表示：定长区 `resume_count`（`u16`）给出条目数（无待恢复会话时为 `0`），
  变长区按顺序给出 `resume_count` 条 **20 字节定长**记录，
  每条含 `session_id`（`u64`）/ `next_chunk_id`（`u32`）/ `missing_count`（`u32`）/
  `flags`（`u8`：bit0 = `next_chunk_id` 有效，bit1 = `missing_count` 有效）。
- 续传起点来自**接收方**的位图，因此**只有接收方才可能提供**它：
  - **上传方向**（接收方 = Server）：Client **必须**不提供恢复提示
    （记录 `flags` 的 bit0 / bit1 = 0，相应字段**必须**取 `0`），
    由 Server 用**自己**的位图计算。
  - **下载方向**（接收方 = Client）：Client **必须**依据**自己的位图**提供恢复提示
    （记录 `flags` 的 bit0 / bit1 = 1）。
- Server **必须**在 `login_ack` 的 `sessions[]` 中为**每一个**待恢复会话给出一项，
  标明 `result`（`enum8`：`0` = fail，`1` = success）与 `code`（失败原因，见 19 章）。
  二进制表示：定长区 `sessions_count`（`u16`）给出条目数，
  变长区按顺序给出 `sessions_count` 条**快照记录**，每条 =
  **42 字节定长**（`session_id`(u64) / `result`(enum8) / `direction`(enum8) /
  `state`(enum8) / `chunk_count`(u32) / `chunk_size`(u32) / `window`(u32) /
  `connection_window`(u32) / `next_chunk_id`(u32) / `missing_count`(u32) /
  `udp_port`(u16) / `tcp_port`(u16) / `code_len`(u16)）+
  紧随其后的 `code_len` 字节内联 `code` 字符串。
- **快照的权威性（规范性）**：Server **必须**以 `login_ack` 的 `sessions[]` 中的状态
  作为唯一权威；Client **必须**以快照**覆盖**其本地保存的对应会话状态
  （位图、续传位置、数据面端口）。
  **不存在**「快照与本地状态并存」的窗口 ——
  控制通道不补发历史消息，重同步是一次**原子的整体替换**。
- 恢复成功后，发送方**必须**丢弃恢复前推导的在途量估计并重建（见 11 章判据第 3 条）。

### 上传方向（Client = 发送方，Server = 接收方）

1. Client 重连 → 发送 `login`，其 `resume[]` 记录只带 `session_id`（`u64`），
   `next_chunk_id` / `missing_count` **必须**未携带（记录 `flags` 的 bit0 / bit1 = 0，
   相应字段取 `0`）
2. Server 加载**自己**的位图 → 计算缺失 → 在 `login_ack` 的 `sessions[]` 快照记录中给出
   `next_chunk_id` / `missing_count` / `udp_port`
3. Client 按快照重建本地状态 → 继续发送
   （双方各自回到断线前状态；发送侧断线前不可能是 `VERIFY` / `COMMIT`）

### 下载方向（Client = 接收方，Server = 发送方）

Server **没有** Client 的位图，无从计算续传起点，
因此由 Client 在 `login` 的 `resume[]` 中提供恢复提示：

1. Client 重连 → 发送 `login`，其 `resume[]` 记录携带
   `session_id`（`u64`）/ `next_chunk_id`（`u32`）/ `missing_count`（`u32`），
   并置记录 `flags` 的 bit0 / bit1 = 1
2. Server 在 `login_ack` 的 `sessions[]` 快照记录中回填权威状态
   （含 `udp_port`、`window`、`connection_window` 与 `state`）
3. Server 按 `next_chunk_id` 起继续向 Client 推送 chunk；
   Client 以 `missing_chunks`（`mode=report`）报告自己的缺失块
4. 双方各自回到断线前状态（发送侧 = Server 回 `TRANSFERRING`；
   接收侧 = Client 回断线前状态）

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
| `next_chunk_id` | **续传顺序起点**：**接收方**位图中**第一个尚未收到的 chunk_id**；位图已全真时为 `chunk_count`（`u32`） |
| `missing_count` | **接收方**位图中尚未收到的 chunk 总数（精确值，`u32`） |
| `udp_port` | 数据面端口（`u16`），可能因会话重建而变化，**Client 必须使用回执中的端口** |

**`next_chunk_id` 的定义（规范性）**：**接收方**位图中**第一个尚未收到**的 `chunk_id`。

本协议显式支持乱序写与随机访问（见 01、17 章），位图可能出现**空洞** ——
存在低于最大已收 id 的缺失块。若以 `max_received_id + 1` 作为续传起点，
空洞块将**永远不会被重传**，文件级 Blake3 校验必然失配并导致会话中止。
因此续传起点**必须**是**第一个缺失块**。

## 空洞块的补发

`next_chunk_id` 只决定**顺序发送流**从哪里继续；位图中低于当前发送位置的空洞
由周期下发的 `missing_chunks`（`mode=report`）负责指认：

- 接收方**必须**在裁决中报告**全部**未收到的 chunk_id，而不只是从
  `next_chunk_id` 开始的连续区间。
- 发送方**必须**优先重传裁决报告的缺失块，优先级高于新数据。
- 包级校验失败（`crc32`）的块同样计入「未收到」，并按本节的**定点补发**处理
  （见 12 章「缺失块的定点补发」）。

## 复核轮与恢复

- 复核轮的计数**必须**与位图一同持久化（见 09 章「持久化」）。
- 摘要对帐的计数**同样必须**持久化：恢复后**不得**因连接重建而重新获得
  一次对帐机会（见 12 章「上限」）。
- 复核轮**进行中**发生断线时，恢复后**必须**继续该复核轮，
  **不得**因连接重建而获得第二次复核轮机会。
- 接收方在恢复后**必须**按 11 章判据第 3 条的「恢复后基线」重建在途量估计；
  若当前处于复核轮，则基线**必须**重置为 `S = R = 0`。

## 失败与清理

- 长时间未恢复可清理，删除临时文件/位图/元数据
- 清理前应确认会话已进入 ABORTED 状态
- 会话超时时长见 09 章「超时与回收」
