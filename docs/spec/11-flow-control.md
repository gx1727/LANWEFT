# 11 流控（Flow Control）

## 两级在途上限

本协议有**两级**在途上限，二者**必须**同时满足：

| 层级 | 参数 | 作用域 | 归属 |
|------|------|--------|------|
| 会话级 | `window` | 单个会话的在途 **symbol** 数上限 | Server 在 accept 中下发 |
| 连接级 | `connection_window` | **一条控制连接上所有会话**在途 **symbol** 数之和的上限 | Server 在 accept 中下发 |

### 会话级：`window`

- **滑动窗口（`window`）是「在途上限」**：已发送但尚未被对端确认接收的 **symbol** 数上限。
- `window` 由 Server 在 `upload_accept` / `download_accept` 中下发。
- **协议层参数**（互操作相关）：

  | 参数 | 归属 | 约束 |
  |------|------|------|
  | `window` | Server 下发 | **Client 不得擅自修改**；**规范默认值 8192** |
  | `connection_window` | Server 下发 | **Client 不得擅自修改**；**规范默认值 16384** |
  | `chunk_size` | 协商确定 | `symbol_size`（1200）的整数倍，`1 ≤ S ≤ 64`；**规范默认 64800**（S=54，见 08 章） |

- **无逐包 ACK**：可靠性由接收方**信用**（`window_update`）与 `missing_chunks` 裁决共同提供
  （见 12 章）；窗口前进的节奏由信用驱动，而非固定墙钟周期。

### 连接级：`connection_window`（规范性）

一条控制连接**可以**承载多个并发会话（见 09 章）。
若每个会话各自遵守自己的 `window`，则整条连接的数据面流量
等于各会话 `window` 之和 —— 单个会话看起来合规，整机流量却可能失控。

- Server **必须**保证：同一控制连接上**全部活跃会话**的 `window` 之和
  **不超过** `connection_window`。
- 发送方**必须**保证：同一控制连接上**全部会话**的**在途量之和**
  **不超过** `connection_window`。
  会话之间的额度分配由发送方自行决定，**不构成**互操作要求。
- `connection_window` 的当前值随 accept 消息下发（见 06 章）；
  发送方**必须**采用**最新**收到的值。
- Server **应当**按目标链路速率设定 `connection_window`；
  **规范默认值 16384** 允许两个满窗口会话并发（8192 × 2）。

### 窗口推进信用与吞吐（规范性）

窗口靠**信用**推进：接收方把「已收多少 **symbol**」告知发送方，发送方据此把已收数 `R` 前移，
让出在途额度。信用由两条消息承载：`window_update`（只带计数，事件驱动）
与 `missing_chunks`（`mode=report`，其 `missing_count` 同样构成信用）。

**信用下发触发（规范性）**：接收方**必须**在满足下列**任一**条件时下发 `window_update`：

1. 自上次信用以来新收到的不重复 **symbol** 数达到 `credit_batch`；
2. 自上次信用以来有新 symbol 到达，且距上次信用已达 **50 ms**；
3. `generation` 发生变化（位图清零并切换代号后立即同步新基线）。

`credit_batch` 的规范取值为 `clamp(window / 8, 16, 1024)`，且**不得**超过 `window`。
它由接收方依据 accept 消息下发的 `window` 计算，**不构成**互操作协商项（见 02 章）。

**空闲抑制（规范性）**：当没有新块到达且没有缺失块时，接收方**不承担**周期性下发信用的
义务；活性由「窗口推进判据」第 4 条的 **1000 ms** 索要机制保证 ——
发送方在需要信用时主动索要，接收方**必须**在 50 ms 内以 `mode=report` 应答。

**吞吐上界（规范性）**：设链路排空速率为 `D`（**symbol**/秒）、单向反馈延迟为 `d`、
每批信用覆盖 `C` 个 symbol，则在 `window ≥ D·d + C` 时稳态吞吐趋近 `D`；即

```
throughput ≈ min(D, window / (d + C / D))     // 单位：symbol/秒
字节吞吐 = throughput × symbol_size
```

信用按数据量事件驱动后，固定的墙钟周期**不**进入除式 ——
只要 `window` 覆盖带宽时延积（BDP）加一批信用，链路即可跑满。

**规范默认值（规范性）**：`window` 默认为 **8192**。

**规范默认值（规范性）**：`connection_window` 默认为 **16384**。

在 `symbol_size = 1200`、`window = 8192` 下，在途数据量约 9.8 MB；
当信用按 `credit_batch ≈ window / 8` 事件驱动下发时，该在途量足以覆盖千兆乃至万兆
局域网的 BDP。资源受限（内存 / 弱网）时可下调 `window`，此时吞吐由
`window / (d + C/D)` 决定。单会话独占链路时，`connection_window`
**应当**取与 `window` 相同的值。

### 在途量与实际接收能力（规范性）

`window` 描述的是**协议层**的在途计数，它**不**等于接收端内核缓冲的实际容量。
接收端**必须**保证其数据面接收缓冲足以吸收发送方的突发，
**否则**突发会被内核直接丢弃，并以丢包的形式反馈给 AIMD
（进而被误判为链路拥塞而错误降速）。

- **接收方（规范性）**：数据面接收缓冲**必须**能够容纳至少**一个发送批次**的突发
  （即 `burst_size × symbol_size` 量级）。
  按默认初值（`burst_size` = 256、`symbol_size` = 1200）计，该要求约 **300 KB**。
- **发送方（推荐性）**：`burst_size` **应当**按对端的吸收能力选取，
  而**不**是直接取满 `window`。

## 发送节奏

- 发送方**必须**按**批次**发送：连续发送 `burst_size` 个 **symbol**（批内**不**逐包停顿），
  批间隔 `batch_gap_us`。
- `burst_size` 初值 = **min(256, `window`)**（**建议值**）；`batch_gap_us` 初值 = **2000 µs**。
- `burst_size` **必须** ≤ `window`。
- **初值为何与 `window` 解耦（说明）**：若 `burst_size` 初值取 `window`，
  默认配置下单个突发将达 8192 × 1200 B ≈ **9.4 MB** ——
  既要求接收方的数据面接收缓冲常备同等容量（见下），
  又极易触发 UDP 内核丢包，被 AIMD 误判为拥塞而**降速**。
  把初值定为 `min(256, window)` 后，默认突发约 **300 KB**，
  接收方的缓冲要求与丢包风险都落在可控范围；
  该初值仍落在 AIMD 的取值区间 `[min(64, window), window]` 内。
- 发送方**必须**持续推进批次，直到全部 symbol 发出；
  任一级在途额度用尽时暂停发送新 symbol（见「窗口推进判据」第 3 条）。

### 变长数据报与 K（规范性）

一个数据报承载 `K` 个连续 symbol（`1 ≤ K ≤ S`），载荷 `L = K × symbol_size`，
由头部与传输层长度唯一确定（见 08 章）。发送方**必须**把 `K` 限制在：

```
Kmax = floor((min(路径 MTU, 65507) − 20) / symbol_size)     // UDP，避免 IP 分片
K ≤ min(S, Kmax)
```

- **1500 MTU 的说明（规范性）**：`(1500 − 20) / 1200 = 1`，因此标准以太网上
  `Kmax = 1` —— 每个数据报只能承载一个 symbol；`K > 1` 只在巨帧（如 9000 MTU）
  或启用分段卸载时才可能。规范**不**要求分段卸载；`K` 的选择是**发送端本地策略**。
- **路径反馈（规范性）**：接收方**必须**在 `window_update.max_ok_payload` 中报告
  最近成功收到的最大载荷长度 `L`；`0` 表示**未知**（此时发送方不受该值约束）。
  非零时，发送方**必须**忽略超过该值的 `K`（除非正在探测）。
- **收缩（规范性）**：仅在**尺寸相关失败**（同一 `K` 连续失败、更小 `K` 成功）时收缩；
  `K ← max(1, floor(K / 2))`。**不得**因随机丢包/拥塞直接收缩 `K`
  （那属于 AIMD 的发送节奏调节，见下）。
- **探测回升（推荐性）**：同一 `K` 连续成功 `probe_success_threshold`（建议 64）个数据报后，
  **可以**探测 `min(2K, S, Kmax)`；探测失败则回退并记录该路径的 `Kmax_ok`。
  升降**应当**加入迟滞，避免抖动。
- **分片（说明）**：`K × symbol_size + 20` 超过路径 MTU 时发生 IP 分片，
  丢一个分片即整报文作废、其 `K` 个 symbol 全部重传。这正是 `Kmax` 公式存在的原因。

## 窗口推进判据（规范性）

这是发送方在「无逐包 ACK」下继续推进的依据：

1. 发送方持续发送新 **symbol**，直到 `symbol_count` 全部发出。
2. 发送方**必须**以最近一次 `missing_chunks`（`mode=report`）裁决中报告的
   `chunks` 与 `partial[]` 作为重传依据，**重传优先级高于新数据**。
3. 发送方**必须**维护「已发送但尚未被对端确认接收」的 **symbol** 数估计，记为**在途量**。
   在途量**不得超过** `window`；达到上限时，发送方**必须**暂停发送**新数据**
   （重传不受此限），直至收到下一次裁决后重新计算。
   每批开始前，必须在会话和连接两级预算中一次性预留新 symbol 额度：
   `本批新 symbol 数 ≤ min(burst_size, 剩余新 symbol 数, 会话剩余额度, 连接剩余额度)`。
   并发会话不得重复预留同一额度；任一额度为零时不发新 symbol。已计入在途的 symbol
   重发不重复占额，但首次发送某个 symbol 即使来自缺失列表，也必须占额。

   **在途量估算（规范性）**：对端已接收 symbol 数 `R` 由最近一次**信用**推出 ——
   `window_update.received_symbols`，或由 `missing_count` 换算的 `symbol_count − missing_count`：

   ```
   R（对端已接收 symbol 数）= received_symbols，或 symbol_count − missing_count
   Sent（已发不同 symbol 数）= 发送方已发出过的**不同** symbol 数量
   在途量 = max(0, Sent − R)
   ```

   - 「已发不同 symbol 数」**不**重复计数重传：同一 symbol 无论重传多少次，
     `Sent` 只增加一次。顺序发送流覆盖 `0 … symbol_count-1`，
     因此 `Sent` 可由「顺序流的下一个待发 symbol」与「已重传的空洞 symbol 数」推出，
     **无需**维护整幅位图。
   - `R` **已知**（收到 `window_update` 或携带 `missing_count` 的裁决）时按上式计算。
     该估计是真实在途量的**保守上界**：信用反映的是对端在**信用时刻**的已收 symbol 数，
     该值**不晚于**当前真实已收数，因此估计值 ≥ 真实在途量 ——
     按估计值执行上限**不会**突破 `window`。
   - `R` **未知**（既无 `window_update`，裁决也未携带 `missing_count`，即存在标志位为 0）时，
     发送方**必须**采用保守退化：把裁决报告的缺失 symbol **全部视为仍未到达**，
     在途量**不得超过** `window − missing_symbols`；
     两级列表为空时退化为 `window`。
   - **恢复后的基线（规范性）**：会话重建后，发送方**必须**把 `Sent` 的基线
     重置为 `symbol_count − 权威快照的 missing_count`（即 `R`）——
     权威快照为 `login_ack.sessions[].missing_count`（断线重连）
     或 `resume_ack.missing_count`（暂停后恢复）。
     这 `R` 个 symbol 已被对端确认收到，必然已经发出过。
     在恢复后首条**信用**（`window_update` 或 `mode=report`）到达时，以其精确计数更新该基线
     （见 13 章）；
     基线重置后 `Sent = R`，在途量为 0，随后随新数据发送而增长。
   - **恢复后（连接重建）**：发送方**必须**丢弃恢复前推导的在途量估计，
     在收到权威快照（`login_ack.sessions` 或 `resume_ack`）之前**不得**发送新数据；
     收到后按上述基线规则重建估计。
   - **复核轮（规范性）**：收到带**复核轮标志**的裁决时
     （`missing_chunks.flags.bit1` = 1，见 12 章），发送方**必须**：
     ①把顺序流重置到 `chunk_id` = 0、`chunk_symbol` = 0；
     ②仅在首次启动全量复核时把基线重置为 `Sent = R = 0`；恢复同一轮使用实际已收数；
     ③重新打开源文件并从头重读；
     ④按原节奏从文件起始 symbol 起全量重发。
4. **信用/裁决索要（单一规则）**：发送方在「等待信用」状态下**必须**保持一个 **1000 ms** 周期：
   距上一次收到信用（`window_update` 或 `mode=report` 的 `missing_chunks`）已超过 **1000 ms** 时，
   **必须**发布 `missing_chunks`（`mode=request`）主动索要；
   每收到一次信用即**重置**该计时器。
   本规则**统一**了 12 章的「保底轮询」与「看门狗」——
   两者是同一机制的不同表述，共享同一周期。
   重复的 `mode=request` 是幂等的（见 06 章「未识别消息必须忽略，保持幂等性」）。
5. **信用与裁决节奏（接收侧义务）**：
   - 窗口推进由**信用**驱动：接收方**必须**按「窗口推进信用」的触发条件下发
     `window_update`，其 `received_symbols` 与 `missing_count` 共同构成 `R` 的依据。
   - 当本会话**存在未收到的 symbol** 时，接收方**必须**至少每 **50 ms** 下发一次
     `missing_chunks`（`mode=report`），以便发送方及时补发。
   - 接收方收到 `missing_chunks`（`mode=request`）时，**必须**在 **50 ms** 内
     以 `mode=report` 应答（该应答同时构成一次信用）。

**活性不依赖空列表周期（规范性）**：信用按数据量事件驱动，空闲时接收方**不**周期下发；
若发送方在 **1000 ms** 内未收到任何信用，**必须**主动以 `mode=request` 索要，
从而避免「窗口填满后永远等不到推进」的死锁。

## 动态流控：AIMD（推荐性）

本节描述**发送端本地策略**，**不属于互操作要求**。
两端实现**可以**采用完全不同的策略，协议行为**必须**保持一致。

发送侧依据对端周期性下发的 `progress_update` 估算链路状况，
据此调节 `burst_size` 与 `batch_gap_us`。

上传方向的发送侧是 Client，下载方向的发送侧是 Server ——
本节对**两个方向同等适用**。
`progress_update` 的发布方恒为**接收方**（见 06 章），两个方向下都成立。

### 丢包率估算

```
loss_rate = 1.0 - (delta_received / delta_sent)
```

- `delta_received`：相邻两次 `progress_update` 之间**接收方**确认的 **symbol** 数增量
- `delta_sent`：同一区间内发送方实际发出的 **symbol** 数增量

**估算约束（规范性）**：

- 估算**必须**基于**滑动窗口内累计值**（窗口长度**建议**为最近 20 个 tick），而非单 tick 差值；
- 样本量不足时（`delta_sent < 16`）**不得**据此调整；
- `delta_sent` 为 0 时**不得**触发除法。

### 调整规则

| 条件 | 动作 |
|------|------|
| 拥塞（loss_rate > 5%） | `batch_gap_us = min(max(batch_gap_us × 1.5, 200), 100000)`<br>`burst_size = max(burst_size × 0.7, min(64, window))` |
| 通畅（loss_rate < 1%） | `batch_gap_us = max(batch_gap_us - 10, 0)`<br>`burst_size = min(burst_size + 2, window)` |
| 中间区间（1% ≤ loss_rate ≤ 5%） | 保持不变 |

- `batch_gap_us` 范围 **[0, 100000] µs**；
  `burst_size` 范围 **[min(64, window), window]** —— 下界取 `min(64, window)`，
  以免 `window < 64` 时下界越过上界。
- 每次调整**应当**加入随机抖动（jitter），避免多个 Client 同步震荡。

### 前提条件

- AIMD **只作用于发送节奏**，不改变协议语义；任何流控参数下协议行为都应一致
- AIMD 依赖 `progress_update` 的周期性下发（发送侧约每 500ms 收到一次）
- 数据面**不做**拥塞控制，AIMD 属于客户端策略而非协议层机制
