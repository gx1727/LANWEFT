# 08 UDP 数据包格式规范（Packet Format）

## 数据包结构（小端序 Little-Endian）

**端序约定（规范性）**：本协议所有多字节整数字段一律采用 **小端序（Little-Endian）**。
该约定**同时适用于控制帧**（见 06 章）、**TCP 数据面帧**（见 07 章）与数据面数据包，
各通道之间**不得**出现端序分歧。

| 字段 | 偏移 | 大小 | 类型 | 说明 |
|------|------|------|------|------|
| session_id | 0-7 | 8 | u64 | 会话唯一标识，由 Server 生成（见 09 章） |
| chunk_id | 8-11 | 4 | u32 | 逻辑块序号（从 0 开始） |
| chunk_symbol | 12-13 | 2 | u16 | `chunk_id` 块内的 **symbol 起始索引**（从 0 开始） |
| flags | 14-15 | 2 | u16 | 标志位 |
| payload | 16.. | N | bytes | 文件数据（`K` 个 symbol） |
| crc32 | 16+N | 4 | u32 | CRC32 校验码（覆盖 header+payload） |

## 头部大小

```
HEADER_SIZE = 8 + 4 + 2 + 2 = 16 字节
CRC_SIZE    = 4 字节
```

**载荷长度由传输层反推（规范性）**：数据报**不**携带 `payload_len` ——
UDP 报文长度已给出总长。接收方**必须**按 `L = 数据报总长 − 16 − 4`
求得载荷长度，并要求 `L > 0`。

**包长核算**：以 `symbol_size = 1200`、`K = 1` 为例，一个数据报的线上长度为
`16 + 1200 + 4 = 1220` 字节；叠加 IPv4 + UDP 的 28 字节头部为 1248 字节，
**小于** 1500 字节的以太网 MTU，**不会**产生 IP 分片。

## 两级单位与长度规则（规范性）

本协议把「寻址单位」与「线缆单位」分开：

- **symbol**（线缆/修复粒度）：`symbol_size` = **1200 字节**，协议常量。
- **chunk**（逻辑块/寻址单位）：`chunk_size` 由会话协商，**必须**是
  `symbol_size` 的整数倍；记 `S = chunk_size / symbol_size`，**必须**满足
  `1 ≤ S ≤ 64`。规范默认 `chunk_size` = **64800**（`S` = 54）。
- 一个数据报承载 `K` 个连续 symbol，`1 ≤ K ≤ S`，载荷长度 `L = K × symbol_size`
  （末报文可短，见下）。`K` **必须**由 `L` 推出：`K = ceil(L / symbol_size)`，
  **不单独编码**。
- `chunk_symbol` 是块内 symbol 索引；第 `chunk_id` 块第 `chunk_symbol` 个 symbol 的
  文件字节偏移为 `chunk_id × chunk_size + chunk_symbol × symbol_size`。
- 数据报**不得**跨块：`chunk_symbol + K ≤ S`。

**长度校验（规范性）**：接收端**必须**校验：

1. `L > 0`；
2. `chunk_symbol + K ≤ S`；对**最后一个块**，还需
   `chunk_symbol + K ≤ ceil((size − chunk_id × chunk_size) / symbol_size)`；
3. **除「最后一个块的最后一个数据报」外**，`L` **必须**是 `symbol_size` 的
   正整数倍（即 `L = K × symbol_size`）；
4. 最后一个块的最后一个数据报**可以**是剩余字节，其长度**必须**精确等于
   `size − chunk_id × chunk_size − chunk_symbol × symbol_size`
   （按**宽整数**计算；结果为负数即非法；此时 `K = 1`，覆盖文件末尾的短 symbol）。

任一不满足即按 `INVALID_PACKET` 丢弃，**不得**写盘或标位。空文件没有 DATA 块。

**MTU、头部开销与分片（规范性 / 说明）**：

- **MTU** = 一条链路能承载的最大 **IP 包**（含 IP 头）。常见取值：以太网 **1500**、
  巨帧 **9000**、环回 **65536**；VPN / 隧道 / 部分 IPv6 路径可能更小（如 1280）。
- 本协议一个数据报对应的 IP 包长度为
  `L + 16 + 4 + 8 + IP头` = **`L + 48`（IPv4）/ `L + 68`（IPv6）**。
- 若要**避免 IP 分片**：`L ≤ 路径 MTU − 48/68`，且 `L ≤ 65487`
  （UDP 载荷上限 `20 + L ≤ 65507`）。
- 允许分片时 `L` 可以更大（至多 `S × symbol_size`，默认 64800）。是否允许由发送端
  策略决定：`K ≤ K_nofrag` 为不分片模式，`K ≤ K_cap = S` 为**信任模式**
  （见 11 章「变长数据报与 K」）。
- **分片的代价（说明）**：分片是「全有或全无」——丢一个分片即整报文作废，
  其覆盖的 `K` 个 symbol 全部重传；因此信任模式**必须**带丢包预算与自动回退。
- **判断路径 MTU 必须用 DF/PMTUD**：`max_ok_payload` 报告的是「曾成功到达的载荷长度」，
  分片重组成功也会报告完整长度，**不能**据此推断「没有分片」。

## CRC32 变体（规范性）

本协议的 `crc32` 字段使用 **CRC-32/ISO-HDLC**（又称 CRC-32、zlib `crc32`）：

| 参数 | 取值 |
|------|------|
| 宽度 | 32 |
| 多项式 | 0x04C11DB7（反射形式 0xEDB88320） |
| 初值 | 0xFFFFFFFF |
| 输入反射 | 是 |
| 输出反射 | 是 |
| 末尾异或 | 0xFFFFFFFF |
| 校验值 | `"123456789"` → 0xCBF43926 |

**覆盖区间（规范性）**：被校验的字节是数据包的
**第 0 字节到第 `16 + L − 1` 字节**，即 **16 字节头部 + payload**，
**不含**尾部 4 字节 `crc32` 字段本身。

**为何必须固定变体（说明）**：CRC-32/ISO-HDLC 与 CRC-32C（Castagnoli，
多项式 0x1EDC6F41 / 反射 0x82F63B78）**互不兼容** —— 两端各选一种会导致
**所有包校验失败**；而按 12 章「校验失败直接丢弃」的策略，
该故障表现为「传输永远无法完成」，极难定位。
因此本协议显式固定变体，不留实现选择空间。

## 包级校验与块级补救（规范性）

- **接收端必须**在**写盘前**校验 `crc32`；校验失败即丢弃该包，
  **不得**标记任何 symbol（见 12 章「包级校验」）。
- 该包覆盖的 `K` 个 symbol 因此保持「**未收到**」状态，会在随后的缺失裁决中被精确报告，
  发送方**只补发这些 symbol**。
  **单次校验失败的代价是 `K` 个 symbol，与文件大小无关**（见 12 章）。

## Flags 位定义

| 位 | 常量 | 值 | 说明 |
|----|------|-----|------|
| bit0 | FLAG_DATA | 0x0001 | 数据包标志 |
| bit1 | FLAG_RESEND | 0x0002 | 重传包标志；接收方**无需**区别处理（重传是幂等的） |
| bit2 | FLAG_LAST_CHUNK | 0x0004 | 最后一个块标志，置位时该包的 `chunk_id` = `chunk_count - 1`；**可选**，接收方**不得**依赖它判断完成（完成以块内 symbol 掩码为准） |
| bit3 | FLAG_PROBE | 0x0008 | 探测包标志；PROBE 与 PROBE_ACK 共用，以**载荷长度**（由报文总长反推）区分（8 / 9） |
| bit4-5 | DATA_GENERATION | 0x0030 | DATA 修复代号：`(flags >> 4) & 3`，0 初传、1 摘要对帐后的定点修复、2 全量复核；3 非法。非 DATA 帧必须为 0 |
| bit6 | FLAG_BIND | 0x0040 | **仅用于 TCP 数据面帧**的绑定帧（见 07 章）；UDP 包**必须**为 0 |
| bit7-15 | RESERVED | 0x0000 | 保留位；接收方**必须**忽略未知标志位 |

## 数据包示例

**普通数据包**:
```
session_id: 0x0000000000000001
chunk_id:   0x00000010
chunk_symbol: 0            // 该块第 0 个 symbol（K=1，L=1200）
flags:      0x0001 (FLAG_DATA)
payload:    [1200 bytes data]
crc32:      [4 bytes checksum]
```

**探测包（PROBE）**:
```
session_id: 0x0000000000000001
chunk_id:   0x00000000
chunk_symbol: 0
flags:      0x0008 (FLAG_PROBE)
payload:    [session_id in little-endian, 8 bytes]   // L = 8
crc32:      [4 bytes checksum]
```

> 探测包 payload 为 `session_id`（u64）的 **8 字节小端编码**。

**探测应答包（PROBE_ACK）**:
```
session_id: 0x0000000000000001
chunk_id:   0x00000000
chunk_symbol: 0
flags:      0x0008 (FLAG_PROBE)
payload:    [session_id in little-endian, 8 bytes][status: 0x00]   // L = 9
crc32:      [4 bytes checksum]
```

PROBE_ACK 的 payload 为 9 字节：8 字节 session_id + 1 字节状态码
（0 = 成功，1 = 失败）。
**PROBE 与 PROBE_ACK 共用 `flags.bit3`，以载荷长度区分**（8 / 9）。

## 错误处理

任一关键字段不匹配或校验失败均丢弃。校验失败的数据包**不得**标记任何 symbol。

- `L` 非法（`L ≤ 0`、`chunk_symbol + K > S`、非末报文 `L` 非 `symbol_size` 整数倍）
  → `INVALID_PACKET`，丢弃
- 该 symbol **已收到**（重复包）→ 幂等丢弃，不重复写盘
  （`CHUNK_ALREADY_RECEIVED`，见 19 章）
- `chunk_id` 越界（≥ `chunk_count`）→ `INVALID_CHUNK`，丢弃
- `session_id` 不匹配 → `SESSION_ID_MISMATCH`，丢弃
- CRC32 校验失败 → `CRC32_INVALID`，丢弃

## 扩展

- flags 预留位（bit7–15）；接收方**必须**忽略未知保留位。DATA 代号须与接收方持久化的当前代号相等；不符在写盘和标位前丢弃，见 12 章。
- 不兼容扩展通过控制通道的协议版本协商：`login` 携带 `proto_version`，
  Server 在 `login_ack` 中回填选定的版本；Client 不支持该版本时**必须**关闭连接
  （见 06 章）
- **数据面格式与协议版本绑定（规范性）**：数据包格式的任何不兼容变更
  **必须**伴随 `proto_major` 的提升；Server **不得**向仅支持旧 major 的对端
  建立使用新格式的数据面会话
- **版本比较规则（规范性）**：版本号在控制面上编码为 **三个 `u8`**
  （`major` / `minor` / `patch`，见 06 章 `login`），
  按 major → minor → patch 逐段**数值**比较。
  - Client 声明其**最高**支持的版本；Server **应当**回填两者都支持的**最高**版本。
  - Server 回填的版本其 major **必须**等于 Client 声明的 major
    —— **major 不同即不兼容**，Client **必须**关闭连接，
    并以 `login_ack.code` = `PROTO_VERSION_UNSUPPORTED` 报告。
  - major 相同、minor 或 patch 不同即视为兼容：新增字段一律可选，
    接收方**必须**忽略不认识的字段。
  - **0.x 例外（规范性）**：本规范处于 `0.x` 阶段，
    `minor` 变更**可能**是不兼容的 —— 例如 v0.3.0 相对 v0.2 的控制面即**不兼容**
    （传输层、帧格式、消息集均已改变）。
    因此 `minor` 不同**不得**作为「可互通」的充分依据；
    实现**必须**以 06 章的消息集为准判断实际兼容性。
    版本策略见 26 章。
