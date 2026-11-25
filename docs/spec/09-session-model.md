# 09 会话模型（Session Model）

## 会话参数

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | u64 | 会话唯一标识，Server 生成 |
| client_id | str | 客户端设备 ID；**必须**等于控制连接绑定的身份（见 21 章） |
| direction | enum8 | `0` = `upload`、`1` = `download`、`2` = `peer` —— **接收方 / 发送方角色** |
| sender_device_id | str | **仅 peer**：发送方 Client 的 `device_id` |
| receiver_device_id | str | **仅 peer**：接收方 Client 的 `device_id` |
| transport | enum8 | **仅 peer**：`0` = direct，`1` = relay_r2（S 转发）；R1 不是 peer transport |
| transfer_token | token16 | **仅 peer**：会话根秘密（lv1 直接作 PROBE token；lv2/lv3 派生 `probe_token` / `traffic_key`） |
| security_level | enum8 | 会话安全等级（`1`/`2`/`3`，默认 `1`，见 20 章）；生命周期内不可变 |
| security_suite | enum8 | lv3 套件（`0` = 无，`1` = AES-256-GCM，`2` = ChaCha20-Poly1305） |
| transfer_id | u64 | **仅 R1**：两段会话的关联 id |
| file_hash | hash32 | 文件哈希（**32 字节原始 Blake3 摘要**） |
| file_name | str | 文件名 |
| size | u64 | 文件大小（字节）；**必须**满足「文件大小上限」（见下） |
| mtime | u64 | 文件修改时间戳 |
| state | enum8 | 会话状态（见 10 章） |
| symbol_size | 常量 | 线缆/修复单位，**1200 字节**（见 08 章） |
| chunk_size | u32 | **逻辑块**大小（字节），`symbol_size` 的整数倍，`1 ≤ S ≤ 64` |
| window | u32 | 滑动窗口大小（**会话级在途 symbol 上限**，见 11 章） |
| connection_window | u32 | **连接级**在途 **symbol** 上限（见 11 章） |
| chunk_count | u32 | 总块数 = `ceil(size / chunk_size)` |
| symbol_count | u32 | 总 symbol 数 = `ceil(size / symbol_size)` |
| udp_port | u16 | UDP 端口号 |
| tcp_port | u16 | TCP 端口号 |
| last_activity | u64 | 最后活动时间戳 |

**`direction` 字段是必需的（规范性）**：本协议的 `missing_chunks` 是**双向**消息，
其含义依赖会话方向（见 06 章）。Server 侧的会话记录**必须**能区分
「我是接收方」还是「我是发送方」，否则无法正确解释对端的缺失报告。

| direction | 接收方 | 发送方 | 完成消息发布方 |
|-----------|--------|--------|----------------|
| `upload` | Server | Client | Server（`upload_complete`） |
| `download` | Client | Server | Client（`download_complete`） |
| `peer` | `receiver_device_id` | `sender_device_id` | 接收方（`peer_complete`，经 Server 中继） |

## 文件大小上限与块参数校验（规范性）

`chunk_count`、`symbol_count` 与 `chunk_id` 均为 **u32**（见 08 章），
因此单个文件的大小**必须**同时满足：

```
chunk_count  = ceil(size / chunk_size)  ≤ 2³² − 1
symbol_count = ceil(size / symbol_size) ≤ 2³² − 1     // symbol_size = 1200
size ≤ 1200 × (2³² − 1) ≈ 5.15 TB
```

- `chunk_size` **必须**是 `symbol_size`（1200）的整数倍，且
  `S = chunk_size / symbol_size` **必须**满足 `1 ≤ S ≤ 64`；规范默认 **64800**（S = 54）。
- **Client 必须**在 `upload_start` / `download_start` 中声明的 `size`
  **不超过 4 TiB − 1024 字节**（保守的全局上限，与本次协商结果无关）。
- **Server 必须**在接受会话前校验：`chunk_size % 1200 == 0`、`1 ≤ S ≤ 64`、
  `ceil(size / chunk_size) ≤ 2³² − 1`、`ceil(size / 1200) ≤ 2³² − 1`；
  不满足时**必须**以 `session_abort`（`reason` = `FILE_TOO_LARGE`）拒绝该请求，
  且**不得**创建会话（见 19 章）。
- **Server 必须**在 `upload_accept` / `download_accept` 中下发的 `chunk_count`
  与 `size` / `chunk_size` **自洽**；Client **必须**核对
  `chunk_count == ceil(size / chunk_size)` 与 `chunk_size % 1200 == 0`，不一致即按
  `SERIALIZATION_ERROR` 视为协议错误。

> **为何必须显式声明上限（说明）**：`size` 以 u64 承载而 `chunk_count` / `symbol_count`
> 以 u32 承载，若不校验则会出现「声明的大小可表示、编号却溢出」的静默不一致。
> 上限必须由两端**共同**校验，而非仅由一端假定。

## 与控制连接的关系（规范性）

- 一个 `device_id`（一条控制连接）**可以**承载**多个并发会话**；
  `session_id` 用于区分。
- **peer 会话横跨两条控制连接**：它同时计入 `sender_device_id` 与
  `receiver_device_id` 各自连接的并发会话数（各占 1 个名额）。
  两份权威快照都**必须**包含该会话（各自视角的 `role` 不同）。
- **单连接并发会话数上限（规范性）**：记 `max_sessions_per_connection` = **64**。
  一条控制连接上的**并发**会话数**必须**不超过该值。
  - 超限时，Server **必须**以 `session_abort`（`reason` = `TOO_MANY_SESSIONS`，
    见 19 章）拒绝**新发起**的会话请求；**不得**因此中断已有会话。
  - 断线重连时的权威快照（`login_ack.sessions[]`）**必须**包含
    该连接上的**全部**会话 —— 因此其条目数同样 ≤ 64
    （64 × 42 字节 = 2,688 字节，**远小于** `max_frame_len` = 1 MiB，见 06 章）。
  - 该上限**不**限制已终止会话的**历史**数量，只限制**并发**数量。
- Server **必须**为每个会话记录其所属的控制连接；
  连接断开时，该连接上承载的**全部**会话进入**中断**处理（见 13 章）。
  **peer 会话的任一端断开**，整个 peer 会话进入中断；另一端**必须**收到通知。
- 会话**不得**跨连接迁移 —— 恢复只能通过 `login` 的恢复列表
  重新建立关联（见 06 章、13 章）。
- **数据面端口可以被多个会话共用**：UDP 包头中的 `session_id` 足以区分（见 08 章）；
  该共用**仅限同一 Server 命名空间**（peer 直连使用独立端点，见 07 章）。
- **连接级在途预算作用于整条连接**：同一连接上所有会话的数据面在途量之和
  **必须**不超过 `connection_window`（见 11 章）。

## 预置素材与共享清单（规范性）

除「客户端上传形成的素材记录」外，Server 还可以**预置**素材，
构成一个**共享清单**（catalog），供已认证的 Client 发现并拉取。

### 两类素材记录（规范性）

| 类别 | 创建者 | 归属 | 可拉取者 | 可撤回者 |
|------|--------|------|----------|----------|
| **私有素材记录** | 客户端上传（`upload_complete`） | 上传方的 `device_id` | 仅归属方 | 归属方（`asset_recall`） |
| **预置素材记录** | Server | Server | **所有已认证设备** | 仅 Server |

- 两类素材记录**互不相交**：私有素材记录**不得**出现在共享清单中；
  预置素材记录**不得**出现在任何 `device_id` 的私有素材视图中。
- 预置素材记录沿用 `asset_id` 标识（见 06 章）。
- Server **必须**为每个预置素材记录维护：素材记录、`file_hash`、`size`、
  `mtime`、`file_name`，以及一个**单调递增**的 `seq`。
- `seq` **必须**在 Server 侧**全局单调递增**且**不复用**；
  Client 以它作为增量水位与分页游标（见下）。

### 发现（规范性）

- Client **必须**通过 `material_list`（`0x17`）查询共享清单；
  Server **可以**在清单变化时主动发布 `material_available`（`0x16`）通知。
- 通知是**至少一次**的提示，**不保证送达**（Client 可能离线、连接可能中断），
  因此 Client **不得**仅凭通知维护完整清单；
  Client **必须**在建立控制连接后查询一次，并**建议**在收到通知后再查询一次。
- Client **必须**按 `seq` 去重：重复的条目**必须**被幂等忽略。
- **增量水位（规范性）**：Client **必须**以**最后收到的条目**的 `seq`
  作为增量水位；**不得**使用应答中的 `max_seq` ——
  `max_seq` 是 Server 侧当前的最大值，可能**超前于**本批已返回的条目，
  用它作水位会**跳过**尚未收到的条目。
- 清单查询**不得**创建任何传输会话 —— 它与数据面完全无关。
- 清单条目被 Server 移除后，Client 的本地视图**可能滞后**；
  此时拉取该条目**必须**被 Server 以 `FILE_NOT_FOUND` 拒绝（见 19 章）。

### 拉取（规范性）

- Client 对清单条目**可以**发起 `download_start`（`0x05`），
  走**既有**的下载流程 —— 数据面、位图、缺失裁决、恢复与提交机制
  **完全复用**，**不引入**任何新的传输路径。
- Server 在处理 `download_start` 时**必须**校验该 `file_hash` 存在且可拉取；
  不存在时**必须**以 `session_abort`（`reason` = `FILE_NOT_FOUND`）拒绝。
- 预置素材的拉取**必须**遵循与会话恢复、权威快照、秒传相同的既有规则
  （见 09、10、13 章）。

### 与私有素材的关系（规范性）

- Client **不得**对预置素材记录发布 `asset_recall` ——
  预置素材记录的归属者是 Server；越权撤回**必须**以 `ACL_DENY` 拒绝
  （见 21 章）。
- 预置素材记录被 Server 移除后，**已建立**的会话**不受影响** ——
  会话引用的是**内容**（`file_hash`），不是清单条目。
- Server 移除预置素材记录**不得**影响任何 Client 的本地文件；
  Client 本地文件的生命周期由**实现**决定。

## 主动投递（Delivery）

Server **可以**在 Client 未请求的情况下，向一个**在线**的 Client 投递文件。

### 前置条件（规范性）

- 投递只**可能**发生在**控制连接存续**期间 —— Server **必须**通过该连接投递；
  Client 离线时**不得**投递。
- 投递方向恒为 **download**（Server → Client）：
  完成消息恒为 `download_complete`（**接收方发布**），
  缺失报告恒由接收方发起（见 10 章「视角定义」）。
- Server **不得**对**已有活跃会话**的同一 `file_hash` 发起投递。
- 投递**不得**要求目标文件在共享清单中；
  投递也**不得**隐式在共享清单中创建条目
  （两条发现路径相互独立，见下）。

### 流程（规范性）

1. Server **必须**生成 `session_id` 与全套会话参数
   （`chunk_size` / `window` / `connection_window` / `udp_port` / `tcp_port`），
   创建会话（状态 `NEGOTIATING`），并发布 `delivery_offer`（`0x19`）。
2. Client 收到 `delivery_offer` 后**必须**作出决定（二选一）：
   - **接受** → 发布 `delivery_response`（`result` = success），
     并**必须**打开数据面 socket、向 `delivery_offer.udp_port` 发出
     `UDP_PROBE`（见 07 章「接收方 socket 生命周期」）；
   - **拒绝** → 发布 `delivery_response`（`result` = fail，
     `code` 填拒绝原因），**不得**发出 PROBE。
3. Server 收到接受后**必须**等待该会话的 `UDP_PROBE` ——
   **未收到 PROBE 前不得发送任何数据面数据包**（见 20 章）；
   收到后**必须**从 `udp_port` 发出 `UDP_PROBE_ACK`，随后开始推送数据。
4. Client 收到 `UDP_PROBE_ACK` 后即可接收数据；
   传输过程**完全遵循**既有的下载流程
   （位图、缺失裁决、断点恢复、文件级校验与原子提交，**无一例外**）。
5. Client **必须**发布 `download_complete`（接收方发布完成消息）。

### 拒绝与失败（规范性）

- Client 拒绝时，Server **必须**发布 `session_abort` 并清理资源。
  `delivery_response.code` 为终止类时沿用；过程类（如 `SERIALIZATION_ERROR`）
  或未知诊断一律映射为 `reason = DELIVERY_DECLINED`。原始诊断保留在应答和日志中。
- Client 未在会话超时内应答（60 秒，见 09 章「超时与回收」）时，
  Server **必须**将该会话置为 `ABORTED`。
- 同一文件对同一 `device_id` 的**重复投递必须被幂等忽略**；
  Client **不得**因收到重复的 `delivery_offer` 而重复落盘同一内容。
- Server **不得**在收到拒绝后**立即**重复投递同一文件
  （退避策略由实现决定，但**必须**有）。

### 与共享清单的关系（规范性）

主动投递与共享清单是**两条独立的发现路径**：

| | 主动投递 | 共享清单 |
|---|---|---|
| 触发方 | Server | Client |
| 频次 | 一次性 | 持续可查 |
| 携带内容 | **全套会话参数** + 文件元数据 | 仅文件元数据 |
| 是否创建会话 | **是**（`NEGOTIATING`） | 否 |

## C↔C peer 会话（Stage 1）

### 握手（规范性）

1. 发起方 Client 发送 `peer_start`（`peer_mode` = push/pull）给 Server。
2. Server **必须**校验：share grant、双方在线、`file_hash`/`size`/`chunk_size` 合法、
   对端设备存在且未与该文件有冲突的活跃会话。
3. Server 给**未发起**的一端发送 `peer_offer`（`session_id`、`transfer_token`、
   会话参数、该端的 `role`）。
4. 对端回 `peer_response`；接受时**必须**先打开数据面 socket 并携带其端口。
5. 接受后：
   - **direct**：Server 下发 `peer_accept` 给双方（含对端端点、token）；
     双方执行 peer PROBE，成功后开始数据。
   - **relay_r2**：Server 分配中转端点，下发 `peer_accept`（`transport = relay_r2`，
     端点为 S 中转端点）；C1 向 S 中转端点 PROBE，S 校验后转发给 C2。
   - **R1 预选中转**：Server 下发 `peer_relay_plan`，随后分别下发标准的
     `upload_accept`（给发送方）与 `download_accept`（给接收方）；
     **不**建立 `direction = peer` 的数据面。
   - 直连探测失败且策略不允许中转 → `PEER_UNREACHABLE`；
     中转不可用（无端点/容量/策略）→ `PEER_RELAY_UNAVAILABLE`（见 19 章）。
6. 拒绝：Server **必须**以 `session_abort` 清理；**不得**建立数据面。

### 角色与权威（规范性）

- `direction = peer` 的会话**必须**同时记录 `sender_device_id` 与 `receiver_device_id`；
  二者都是 Client，且各自绑定一条控制连接。
- Server 生成 `session_id`，仲裁状态、超时与终止；接收方是位图/临时文件/
  文件级 Blake3/`peer_complete` 的权威。
- 会话绑定**两条**控制连接；任一条断开 → 会话进入中断（见 13 章）。
- 同一 `(sender_device_id, receiver_device_id, file_hash)` 的活跃传输**必须**复用。

### 数据面（规范性）

- **direct**：C1 → C2，复用 07/08 的 UDP/TCP 数据面、symbol/chunk、位图、
  缺失裁决、信用与 K 策略；`session_id` 由 Server 生成。
  `transfer_token` 用于 **peer PROBE/端点确认**，数据包按端点做源地址校验；
  每包 keyed MAC 属于后续安全增强。
- **relay_r2**：S 转发同一会话的数据包；接收方仍按 symbol 记账。
  S 只保有界转发队列，不存整文件；收到/发往两段 leg 的端点、token 与源地址
  必须校验。容量不足时不得建立或切换。
- **transport 切换**：Server **可以**通过 `peer_transport_switch` 在同一会话内
  direct ⇄ relay_r2；`session_id`/方向/generation 不变，接收方位图/临时文件保留。
- **R1**：两段既有会话；Server **必须**建立**临时中转素材记录/授权**，
  使接收方能够合法 `download_start`；完成后回收。`transfer_id` 关联两段结果。

### 控制中继（规范性）

- peer 会话的 `missing_chunks` / `window_update` / `progress_update` /
  `peer_complete` / `reconcile_request` / `reconcile_response` / `complete_ack` /
  `session_pause` / `session_abort` **必须**经 Server 转发到对端（见 06 章）。
- Server **必须**校验发布方是该会话的对应角色；越权按 `ACL_DENY` 丢弃并审计。
- **不得**建立 C↔C 的控制连接；**不得**要求 C↔C 的 `login`。

### 授权（规范性）

- peer 传输**必须**落在 share grant
  `(sender_device_id, receiver_device_id, file_hash, expiry)` 内。
  - **push** 的 `peer_start` 由发送方发起，Server **可以**据此创建/刷新 grant；
  - **pull** 的 `peer_start` 由接收方发起，**必须**命中已存在的 grant
    （由之前的 push 或实现/管理面预置）。
- 未授权：`ACL_DENY`；接收方拒绝：`PEER_DECLINED`。
- 私有素材归属不变；peer 传输不改变 Server 侧归属（R1 的临时素材除外，完成后回收）。

### 持久化（规范性）

- peer 会话元数据**必须**持久化：`session_id` / `direction = peer` /
  `sender_device_id` / `receiver_device_id` / `transport` / `transfer_token` / 参数；
  R1 还**必须**持久化 `transfer_id` 与两段会话 id。
- **不**持久化数据面内容（R2 无存储；R1 由 S 的临时素材承载）。

## 创建规则

1. **session_id 由 Server 生成**
   - Server **必须**保证 `session_id` 在**跨进程重启**后**也不被复用**，
     且在同一时刻**全局唯一**。
   - **`session_id` 的位宽为 u64**（见 06、08 章）。
     32 位空间在会话数达到百万量级时必然出现碰撞
     （生日界：约 2³² 次分配即有 50% 碰撞概率），
     且跨重启复用会让**迟到的旧数据包**命中新会话（见 20 章「重放保护」）。
   - **生成方式（规范性）**：Server **必须**采用**时间有序**的分配方式，
     使「跨重启不复用」成为**构造性保证**而非依赖外部状态。
     推荐结构（Snowflake 式）：

     ```
     | 1 位恒为 0 | 41 位毫秒时间戳 | 10 位机器位 | 12 位同毫秒计数器 |
     ```

     - **机器位**：Server 首次启动时随机生成，并**必须持久化**；
       重启后**必须**沿用同一机器位。
     - **计数器**：同一毫秒内自增，上限 4095；溢出时**必须**等待下一毫秒。
     - **时间戳部分**：**必须**使用单调不回退的毫秒时钟；
       因此进程重启后分配到的 `session_id` **必然大于**重启前的全部取值。
   - 实现**可以**采用其他方案，但**必须**同时满足：
     ①同一时刻全局唯一；②跨进程重启不复用；
     ③**必须**能区分「同一 Server 实例的不同进程」，
     即同一台机器上多个 Server 实例**不得**分配到相同 `session_id`。
   - 冲突后果严重：`session_id` 同时是控制面关联键、UDP 头字段与 TCP 数据面帧字段
     （见 06、07、08 章），串号会导致跨会话数据污染。
2. **同文件正在同步 → 返回现有会话**
   - 活跃会话的判定键为 `(client_id, direction, file_hash)`；先复用同方向活跃会话，不重复创建素材或执行秒传。
   - 返回现有会话时，`upload_accept` **必须**复用既有的 `session_id`，
     并重新下发当前的 `window` / `connection_window` / `chunk_size` / `udp_port`。
3. **已存在完整文件 → 秒传**
   - 仅当该设备已有权读取相同内容（设备自己的素材记录或对其可见的预置记录），且既有文件校验通过时，`upload_accept.file_exists = 1`（bool 真），
     走 10 章定义的秒传路径（**不进入 TRANSFERRING，不产生位图**）。
   - 此处指接收侧跳过数据传输；发送侧仍等待最终回执。仅有其他设备的私有记录时，
     必须与文件不存在时一样返回 `file_exists = 0` 并正常接收、校验；不得凭哈希创建授权记录。
     完成提交时可以在存储层去重，但素材归属与回执必须按本次会话独立处理。
4. **否则新建会话并生成新的 session_id**

## 持久化（规范性）

接收方**必须**持久化以下状态，使其在进程重启或设备重启后仍可恢复：

- **临时文件**（含已写入的数据）
- **两级位图**：块完成位图 + 未完成块的 `u64` symbol 掩码（见 18 章）
- **会话元数据**（`session_id` / `direction` / `chunk_size` / `chunk_count` / `symbol_count` / 临时文件路径）
- **复核轮计数**（见 12 章）：已执行的复核轮次数
- **对帐计数**（见 12 章）：已执行的摘要对帐次数
- **定点重读计数**（见 12 章）：已执行的停滞定点重读次数

- 位图**必须**能写入持久化副本并从该副本恢复；
  持久化格式与存储位置由实现决定。
- 写入与位图更新的**先后顺序**由实现决定，但必须保证：
  位图标记为「已接收」的块，其数据**已经**落在临时文件中
  —— 否则恢复后会把未落盘的块当作已接收，导致空洞永不重传
  （见 13 章「空洞块的补发」）。

## 超时与回收

- **会话活动超时**：会话连续 **60 秒**无控制面交互或数据面活动时，Server 停止并回收
  数据传输。对已接受的下载，Server 是发送方，不能仅凭超时判定 Client 的提交结果；
  必须保留设备绑定、会话标识、方向与结果记录，处理 13 章的迟到回执。未提交的上传
  可终止并清理临时数据；已存在提交意图的先按 13 章恢复提交，不得删除待交付回执。
- **超时层级（规范性）**：控制连接的空闲超时（**30 秒**，见 06 章「心跳与超时」）
  **必须**早于会话活动超时（60 秒）触发。
  即：连接先断开（会话转为**中断**，可恢复），
  随后才由会话超时兜底清理传输资源。
- 客户端在超时前可经 `login` 的恢复列表恢复；超时后不再恢复数据传输，
  但终态回执仍可交付。
- 该阈值对应 19 章的 `TIMEOUT_NO_ACTIVITY`。
- **校验阶段的例外（规范性）**：`VERIFY` / `COMMIT` 期间以大文件哈希或提交为主，
  接收方**必须**通过应答控制面请求维持活动；哈希与提交**不得**阻塞控制循环或心跳
  （见 12 章「校验阶段的活性」）。停滞检测（`TRANSFER_STALLED`）**不**在该阶段评估。
