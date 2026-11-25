# 20 安全模型（Security Model）

## 假设

- **lv1** 假设可信局域网；**lv2/lv3** 可用于不可信网络（含公网路径）。
- Server 与客户端受控；Server 是认证与密钥分发的信任根。
- 跨公网部署**必须**启用控制面 TLS，并**不得**将 `security_min_level` 配为 1。

## 控制面

- 控制通道**必须**支持 TLS；**应当**启用（见 21 章）
- 认证在**连接握手**阶段完成，绑定唯一 `device_id`
  （共享令牌或客户端证书，见 21 章）
- **一条控制连接只承载一个 `device_id`**；
  跨 `device_id` 的会话在协议层无法表达
- 凭据**不得**由 `device_id` 直接推导（见 23 章「隐私」）
- **表示形式（规范性）**：
  - 认证凭据由 `login` 的 `token` 字段承载，类型为 `str`
    （`u16` 长度 + UTF-8）；采用客户端证书时**必须**为空串（长度 0）
  - `device_id` 同样以 `str` 承载
  - 协议版本以三个 `u8` 承载（`proto_major` / `proto_minor` / `proto_patch`），
    载于 `login` 与 `login_ack`（见 06 章）
  - 错误码以**符号名字符串**承载（`code` / `reason` 字段，类型为 `str`），
    **不得**填写自由文本

## 数据面安全等级（规范性）

数据面支持三个**会话级**安全等级；**默认 lv1**。等级在会话建立时由 Server 选定，
**会话生命周期内不可变**；配置变更只影响新会话。

| 等级 | 尾部 `trailer` | 完整性 | 对端认证 | 机密性 |
|------|----------------|--------|----------|--------|
| **lv1** | CRC32（4B） | 非密码学 | 无 | 无 |
| **lv2** | BLAKE3 keyed MAC（16B） | 密码学 | 有 | 无 |
| **lv3** | AEAD tag（16B） | 密码学 | 有 | 有 |

- lv1 是**兼容默认**，只适用于可信 LAN；PROBE token 仍然启用。
- lv2 用 `BLAKE3-keyed` 替换 CRC32，覆盖「16B 头 + payload」；不加密。
- lv3 用 **AES-256-GCM** 或 **ChaCha20-Poly1305**（由 `security_suite` 选定）：
  - `payload` 为密文，长度与明文**完全相等**；
  - `header` 保持明文，作为 **AAD**；
  - tag 覆盖 AAD + 密文；
  - nonce = `(generation, chunk_id, chunk_symbol, K)` 的规范编码，**必须**在同一
    `traffic_key` 下唯一（K 参与，避免「同起点不同长度」复用 nonce）。
- **AEAD/MAC 单元 = 数据报载荷（K 个 symbol）**，不是单个 symbol：
  - 允许信任模式 `K > 1`（一个 64KB 数据报一个 tag）；
  - 明文长度与 symbol 偏移映射均不变，接收方仍按 `chunk_symbol + K` 标位；
  - 丢包/坏 tag 的代价仍是该包覆盖的 K 个 symbol，可靠性模型不变。
- 接收方**必须**按会话表选定的等级解析 `trailer` 长度；未知 `session_id` 直接丢弃，
  **不得**猜测等级。TCP 数据面同理：lv1 无尾部，lv2/lv3 尾部 16B 且计入 `frame_len`。

### 密钥派生

- 每个会话有且只有一个根秘密：
  - C↔S：`login_ack.link_token`（每控制连接 16B，成功时非零）；
  - C↔C：`peer_accept.transfer_token`（每 peer 会话 16B）。
- `probe_token`：
  - lv1：根秘密**直接**作为 `probe_token`（PROBE 携带它；无数据密钥，泄露不危及数据）；
  - lv2/lv3：`probe_token = KDF(root, "probe", 16)`，**不得**在线上发送根秘密。
- `traffic_key`（仅 lv2/lv3）：`KDF(root, "data" ‖ session_id ‖ direction, 32)`。
  - C↔S 的 `link_token` 每连接重新签发；重连后按新根秘密重新派生，
    旧密钥的数据包自然失效并走重传。
  - C↔C 的 `transfer_token` 随 `peer_accept` 恢复重发；同一会话密钥稳定。
- `KDF` **必须**为 BLAKE3 的 keyed/derive-key 模式（或等强度的 HKDF）；
  标签 `"probe"` / `"data"` **必须**参与派生，避免密钥复用。
- lv2/lv3 **必须**在已认证的控制连接上分发根秘密；因此 **lv2/lv3 要求控制面 TLS**。
  Server 配置 `security_min_level ≥ 2` 而 TLS 未启用时，**必须**拒绝启动或拒绝会话。
- Server 参与 C↔C 的密钥分发，因此 lv3 提供的是**路径保护**，
  不是「对 Server 保密」；后者超出本规范范围。

### 协商与 Server 配置

Server 配置：

| 参数 | 含义 | 默认 |
|------|------|------|
| `security_min_level` | 允许的最低等级；低于它拒绝 | **1** |
| `security_default_level` | 双方都支持时优先选用的等级 | **1** |
| `security_max_level` | 允许的最高等级 | **3** |
| `security_suites` | lv3 允许套件及顺序 | AES-256-GCM → ChaCha20-Poly1305 |

- Client 在 `login` 中声明 `max_security_level` 与 `security_suite_mask`（见 06 章）。
- **C↔S**：Server 为每个会话选择
  `chosen = clamp(security_default_level, security_min_level, min(client_max, security_max_level))`；
  若 `client_max < security_min_level`，以 `SECURITY_LEVEL_UNSUPPORTED` 拒绝。
- **C↔C**：Server 取两端 `max_security_level` 的较小值，再按同一规则选择；
  两端都**必须**支持选定等级。无交集且低于 `security_min_level` 时拒绝。
- lv3 套件：从 `security_suites` 中选第一个同时被 Client `security_suite_mask`
  支持的套件；无交集时**必须**降级到 lv2（若 `security_min_level ≤ 2`），
  否则拒绝。**不得**静默使用未协商的套件。
- 选定结果写入 `upload_accept` / `download_accept` / `delivery_offer` / `peer_offer` /
  `peer_accept` 的 `security_level` / `security_suite`；快照记录的重启恢复用
  `security` 字节（见 06、13 章）。
- **禁止静默降级**：协商在已认证控制面内完成；Server **不得**因客户端能力不足
  而选择低于 `security_min_level` 的等级。Client **不得**接受低于自己声明下限的等级。

## 数据面通用约束

- 文件级内容 hash（Blake3）：**32 字节原始摘要**（`hash32`），
  **禁止**以十六进制串承载；日志与 UI 展示时由实现自行转十六进制（见 06 章）。
- 数据面地址必须做**源地址校验**：接收方**必须**校验 UDP 包的源地址:端口
  与该会话经 PROBE 确认的对端地址一致，不一致即丢弃。
  这不能替代认证（地址可伪造），但能挡住非定向的误发与扫描。
- **PROBE 端点绑定（规范性）**：
  - C↔S：PROBE 载荷 = `session_id + probe_token`；Server 校验 token 属于该控制连接，
    并把 PROBE 源地址:端口绑定为该会话端点（见 07 章）。
  - C↔C：PROBE 载荷 = `session_id + probe_token`；接收方校验后绑定发送端端点。
  - token 不匹配按 `PEER_TOKEN_INVALID` 丢弃，**不得**绑定或回 ACK。
  - lv1 的 token 是 bearer，on-path 嗅探后仍可重绑定；lv2/lv3 的派生 token
    不暴露根秘密，但 PROBE 本身的认证仍**应当**在后续版本加 MAC。
- **重放保护**：接收方**必须**拒绝 `chunk_id` **≥** 该会话 `chunk_count` 的包（越界，见 08 章），
  且**必须**校验 `session_id`（u64）与本会话一致；DATA 的修复代号也必须匹配。
  同一代内的重复由位图幂等性兜底（重复 chunk 静默丢弃）。
  lv3 的 nonce 唯一性保证同一密钥下不会因重放而混淆不同明文。
- **C↔C peer（规范性）**：`direction = peer` 的直连数据面**没有** C↔C 的 `login`；
  身份与授权来自双方与 Server 的既有登录 + share grant（见 21 章）。
  - 直连：`transfer_token` 是根秘密；lv1 直接作为 PROBE token，lv2/lv3 派生
    `probe_token` / `traffic_key`。
  - R2 中转：S 转发数据；lv2/lv3 的 tag 由 C1 生成、C2 校验，S 不修改载荷。
    S 参与密钥分发，因此不提供「对 S 保密」。
  - R1：S 完整存储文件，按 Server 侧数据保护。
  - PROBE 可劫持、地址可伪造的既有风险同样适用于 peer；token 只提高门槛。
- **`session_id` 的唯一性是重放保护的前提（规范性）**：
  `session_id` **必须**跨 Server 进程重启**不复用**（见 09 章「创建规则」）——
  否则重启前仍在网络中飞行的数据包会命中重启后新建的会话，
  把数据写入**错误的文件**。为此 `session_id` **必须**为 u64 且采用时间有序的分配方式。
- **复核轮的边界**：复核轮是接收方主动发起的**全量重传**，
  由 `missing_chunks` 的复核轮标志显式表达（见 12 章）；
  它**不是**重放，发送方**必须**重新读取源文件。

## 主动投递的边界（规范性）

- 主动投递**只**发生在**已认证且存续**的控制连接上（见 09 章「主动投递」）；
  Server **不得**向离线设备投递。
- 投递**不携带**任何认证凭据 —— 它复用控制连接已建立的身份边界。
- Server 在收到 `delivery_response`（接受）后**必须**等到该会话的
  `UDP_PROBE` 才可发送数据面数据包：**不得**向未经 PROBE 确认的地址发送
  （见 07 章「端口与地址绑定」）。
- 接收方**可以**拒绝投递；拒绝是**正常**的协议结果，
  **不得**被当作错误或触发重试风暴。
- 重复投递**必须**被幂等忽略：接收方**不得**因重复的 `delivery_offer`
  而重复落盘同一内容。

## 资源消耗（规范性）

摘要对帐会诱导发送方反复读取源文件（见 12 章），因此**必须**设限：

- 每会话的摘要对帐**至多一次**；
- 单次请求的区间数 ≤ 64，单会话累计区间比较数 ≤ 8192，层级 ≤ 32；
- 发送方**必须**拒绝超出上限的请求，**不得**无条件执行。

接收方**不得**通过反复发起对帐来消耗对端的磁盘与 CPU。

## 状态与权限

- UDP 会话**必须**绑定到发起它的控制连接（及其 `device_id`）
- Server 不向未知端口发送 UDP；目标地址必须来自 PROBE 报文（见 07 章）
- TCP 数据面降级需重校验权限

## 审计

- 认证失败尝试、跨 `device_id` 的会话操作与 `session_abort` 原因
