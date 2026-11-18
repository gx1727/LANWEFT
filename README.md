# LANWEFT

**LAN**ware **W**ire-**E**fficient **F**ile **T**ransfer — 面向可信局域网的混合文件同步协议。

通过「控制面 TCP + 数据面 UDP」的双通道协作，在保证高吞吐的同时，实现可中断、
可恢复、可裁决的文件同步能力。

```
应用层 → 控制层（TCP：状态机 / 重传裁决 / 权威快照） → 数据层（UDP 主 / TCP 兜底） → 局域网
```

## 核心特性

- 局域网内大文件（照片 / 视频）高效同步
- 不中断可恢复、乱序写盘、内存与文件大小解耦
- 控制与数据分离，可靠性由控制面裁决
- 控制面：TCP 长连接（**二进制定长帧** + 握手快照）；数据面：UDP；位图进度；会话恢复；NAT 探测

## 协议要点

| 主题 | 约定 |
|------|------|
| 控制通道 | TCP；一条连接承载**多个并发会话**，帧 = `u32 frame_len` + `u8 msg_type` + **二进制定长消息体**（见 06 章） |
| 角色视角 | 发送侧 / 接收侧各自持有一份状态机（见 10 章） |
| 完成消息 | **一律由接收方发布**（上传方向 Server、下载方向 Client） |
| 缺失裁决 | **一律由接收方发起**，每 50ms 一次，空列表亦须下发 |
| 可靠性 | 无逐包 ACK；接收方裁决 + 发送方重传，包级 CRC32 + 文件级 Blake3 |
| 恢复 | 断线重连走 `login` 的**恢复列表** → `login_ack` 的**权威快照**；续传起点是**第一个缺失块**（非 `max_received_id + 1`） |
| 身份 | 握手认证，一条连接绑定唯一 `device_id`；在线状态 = 连接存续 |

## 文档

规范正文位于 [`docs/spec/`](docs/spec/)，共 26 篇：

| 章 | 主题 | 章 | 主题 |
|----|------|----|------|
| [00](docs/spec/00-overview.md) | 概览 | [13](docs/spec/13-resume-and-recovery.md) | 中断与恢复 |
| [01](docs/spec/01-architecture.md) | 架构 | [14](docs/spec/14-download-flow.md) | 下载流程 |
| [02](docs/spec/02-terminology.md) | 术语（**权威定义**） | [15](docs/spec/15-nat-and-network-limits.md) | NAT 与网络限制 |
| [03](docs/spec/03-design-goals.md) | 设计目标 | [16](docs/spec/16-mobile-background-limits.md) | 移动端后台限制 |
| [04](docs/spec/04-non-goals.md) | 非目标 | [17](docs/spec/17-memory-and-disk-model.md) | 存储与内存模型 |
| [05](docs/spec/05-protocol-stack.md) | 协议栈 | [18](docs/spec/18-bitmap-and-chunk-map.md) | 位图与块图 |
| [06](docs/spec/06-control-plane-tcp.md) | 控制面（TCP） | [19](docs/spec/19-error-codes.md) | 错误码 |
| [07](docs/spec/07-data-plane-udp.md) | 数据面（UDP / TCP 兜底） | [20](docs/spec/20-security-model.md) | 安全模型 |
| [08](docs/spec/08-packet-format.md) | UDP 数据包格式 | [21](docs/spec/21-acl-and-auth.md) | 认证与访问控制 |
| [09](docs/spec/09-session-model.md) | 会话模型 | [23](docs/spec/23-client-identity.md) | Client Identity |
| [10](docs/spec/10-state-machine.md) | 状态机 | [24](docs/spec/24-sequence-diagrams.md) | 端到端时序 |
| [11](docs/spec/11-flow-control.md) | 流控 | [25](docs/spec/25-normative-marking.md) | 非规范性内容标注规范 |
| [12](docs/spec/12-reliability-model.md) | 可靠性模型 | [26](docs/spec/26-roadmap.md) | 下一阶段与路线图 |

### 阅读顺序

- **首次了解**：00 → 01 → 05 → 10 → 12 → 24
- **实现 Server**：06 → 08 → 09 → 10 → 11 → 13 → 18 → 19 → 21
- **实现 Client**：06 → 08 → 11 → 14 → 16 → 17 → 23

## 状态

| 项 | 值 |
|----|-----|
| 协议版本 | **v0.3.0** |
| 规范状态 | **Draft（草案，尚未冻结）** |
| 变更摘要 | [26 章](docs/spec/26-roadmap.md) |
| 修订记录 | [26 章「修订记录」](docs/spec/26-roadmap.md) |

> **版本策略**：版本号只在上游明确指示时变更；未获明确指示的修订
> **不得**变更版本号，而**必须**记入 26 章「修订记录」。见
> [26 章「版本策略」](docs/spec/26-roadmap.md)。

> **v0.3.0 与早期草案的控制面不兼容**（传输层、帧格式、消息集均已改变），
> 升级**必须**同时升级两端。规范仍在修订中，**不应用于生产环境**。

> **控制面线路格式为二进制定长布局**（见 06 章）。按上游指示本次变更**未**变更版本号，
> 因此 `v0.3.0` 这一版本号先后指代过 **JSON** 与 **二进制**两套互不兼容的线路格式；
> 实现**必须**以 06 章正文为准。见 [26 章「已知限制」](docs/spec/26-roadmap.md)。

## 参考实现


## License

[MIT](LICENSE) © 2026 gx1727
