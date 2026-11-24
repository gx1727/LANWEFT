# 99 术语表（Glossary）

> **字段与概念的权威定义见 [02 章「术语」](02-terminology.md)**；
> 本章提供消息清单与缩写速查。

## 协议相关

| 术语 | 说明 |
|------|------|
| LANWEFT | 协议名称 |
| TCP | 控制面协议（信令 / 裁决），一条连接承载多个并发会话 |
| UDP | 数据面主通道 |
| TCP fallback | 数据面降级通道（**不是**控制通道） |
| 小端序 | 本协议所有多字节整数的字节序（Little-Endian） |
| CRC-32/ISO-HDLC | 本协议包级校验使用的 CRC32 变体（见 08 章） |
| Blake3 | 文件级内容哈希算法（见 08、12 章） |
| 帧 | 控制通道的消息单元：`u32 magic` + `u32 frame_len` + `u32 header_crc32` + 定长帧头（**16 字节**）+ 二进制消息体（见 06 章） |
| 失步 | desync：帧边界不再可信；判定后**必须**断连并按 13 章恢复（见 06 章） |
| 权威快照 | Server 下发的会话关联、参数与进度摘要，不覆盖接收方的位图或提交阶段（见 13 章） |

## 会话与数据

| 术语 | 说明 |
|------|------|
| session | 一次文件传输会话 |
| session_id | 会话唯一标识（**u64**，由 Server 生成；跨进程重启不复用，见 09 章） |
| client_id / device_id | 设备唯一标识（设备级粒度）；与认证主体绑定（见 23 章） |
| chunk | 逻辑块（寻址/位图/对帐单位） |
| chunk_id | 逻辑块序号（u32，从 0 开始） |
| chunk_size | 逻辑块大小（`symbol_size` 的整数倍，`1 ≤ S ≤ 64`；规范默认 **64800**，S=54） |
| chunk_count | 总块数 = ceil(size / chunk_size) |
| symbol_size | 线缆/修复单位，常量 **1200 字节** |
| chunk_symbol | 块内 symbol 起始索引（u16）；字节偏移 = `chunk_id×chunk_size + chunk_symbol×symbol_size` |
| symbol_count | 总 symbol 数 = ceil(size / 1200) |
| K / L | 一个数据报承载的 symbol 数 / 载荷长度（均由传输层与头部推出，不单独编码） |
| K_nofrag / K_cap | 不分片上限（由路径 MTU 决定）/ 策略上限（信任模式可达 S，允许分片）；见 11 章 |
| flags | 数据包标志位（u16） |
| bitmap | **两级**位图：块完成位图 + 未完成块的 `u64` symbol 掩码 |
| missing_chunks | 两级缺失上报：`chunks`（完全缺失块）+ `partial[]`（部分缺失块 + `u64` received_mask，bit=1 已收到）；发布方恒为接收方 |
| reconcile_request / reconcile_response | 摘要对帐请求 / 应答；请求恒由**接收方**发布，应答恒由**发送方**发布（见 12 章） |
| missing_count | 位图中尚未收到的 **symbol 精确总数**；未携带时由**存在标志位**表示 |
| udp_ready | UDP 可用性就绪通知 |
| file_hash | 文件哈希，**32 字节原始 Blake3 摘要**（hash32，非十六进制串） |
| asset_id | 素材记录标识（Server 分配） |
| 私有 / 预置素材记录 | 客户端上传产生（归属该 device_id）/ Server 创建（所有已认证设备可拉取）；见 09 章 |
| 共享清单 | Server 侧全部预置素材记录的集合；`material_list` 查询、`material_available` 通知（见 09 章） |
| material_available / material_list / material_list_ack | 共享清单变更通知 / 清单查询 / 查询应答（见 06 章） |
| delivery_offer / delivery_response | 主动投递提议（Server 发布，携带全套会话参数）/ 投递应答（Client 发布，接受或拒绝）；见 09 章 |
| window | 滑动窗口大小（**会话级在途 symbol 上限**，Server 下发，Client 不得修改） |
| connection_window | **连接级**在途 **symbol** 上限；同一控制连接上所有会话的在途 symbol 数之和的上限（见 11 章） |
| window_update | 窗口推进**信用**（接收方发布，携带 `generation` / `received_symbols` / `max_ok_payload`）；按收到量事件驱动（见 06、11 章） |
| received_symbols / credit_batch | 当前代号下已收到的不重复 symbol 数 / 信用下发批阈值（见 02、11 章） |
| 复核轮 | 文件级失配后接收方要求发送方重新读取源文件并全量重发的恢复过程，**至多一次**（见 12 章） |
| 停滞 / 定点重读 | `missing_count` 在 `stall_timeout`（10 秒）内不动即停滞；首次停滞触发 `flags.bit6` 定点重读，再次停滞以 `TRANSFER_STALLED` 终止（见 12 章） |
| burst_size | 发送批次大小（发送端本地参数，初值 = `min(256, window)`） |
| batch_gap_us | 批间隔（微秒，发送端本地参数，初值 2000） |
| direction | 会话方向（`0` = `upload` / `1` = `download`），决定接收方与发送方 |
| AIMD | 加性增乘性减动态流控算法（**发送端策略**，非协议层机制） |

## 控制面消息

| 消息 | 方向 | 说明 |
|------|------|------|
| login / login_ack | C→S / S→C | 连接握手、认证与**权威快照** |
| upload_start / upload_accept | C→S / S→C | 上传会话建立 |
| download_start / download_accept | C→S / S→C | 下载会话建立 |
| udp_ready | S→C | UDP 可用性就绪通知 |
| missing_chunks | 双向 | 两级缺失上报（`mode=report`，**接收方发布**：完全缺失块 + 部分缺失 symbol 掩码）/ 索要（`mode=request`，**发送方发布**） |
| window_update | 双向（**接收方发布**） | 窗口推进信用：`generation` + `received_symbols` + `max_ok_payload`（见 06、11 章） |
| progress_update | 双向 | 传输进度更新（单位：symbol 数；**接收方发布**） |
| session_pause / session_abort | 双向 | 会话暂停 / 中止（`session_abort` 发布方受限，见 10 章） |
| resume_session / resume_ack | C→S / S→C | 暂停后的会话恢复（恢复提示由**接收方**提供，见 13 章） |
| upload_complete / download_complete | S→C / C→S | 传输完成（**完成消息一律由接收方发布**） |
| complete_ack | C→S / S→C | 数据发送方确认已持久化完成回执 |
| asset_recall / asset_recall_complete | C→S / S→C | 资产撤回请求与回执 |
| ping / pong | 双向 | 心跳与应答（10 秒周期，30 秒空闲超时） |

## 章节索引

| 章 | 主题 | 章 | 主题 |
|----|------|----|------|
| 00 | 概览 | 13 | 中断与恢复 |
| 01 | 架构 | 14 | 下载流程 |
| 02 | 术语（**字段与概念的权威定义**） | 15 | NAT 与网络限制 |
| 03 / 04 | 设计目标 / 非目标 | 16 | 移动端后台限制 |
| 05 | 协议栈 | 17 | 存储与内存模型（非规范性） |
| 06 | 控制面（TCP） | 18 | 位图与块图 |
| 07 | 数据面（UDP / TCP 兜底） | 19 | 错误码 |
| 08 | UDP 数据包格式 | 20 | 安全模型 |
| 09 / 10 | 会话模型 / 状态机 | 21 | 认证与访问控制 |
| 11 / 12 | 流控 / 可靠性模型 | 23 | Client Identity |
| | | 24 | 端到端时序 |
| | | 25 | 非规范性内容标注规范 |
| | | 26 | 下一阶段与路线图（非规范性） |
