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
| 控制通道 | TCP；一条连接承载**多个并发会话**，帧 = `u32 magic` + `u32 frame_len` + `u32 header_crc32` + `u8 msg_type` + … + **二进制定长消息体**（**16 字节定长帧头**，见 06 章） |
| 帧同步 | 控制帧与 TCP 数据面帧均以 `magic`（`0x574E414C`）+ `header_crc32` + `frame_len` **三项校验**确认帧边界；任一失败即判定**失步**并**断连**，恢复走 `login`/`login_ack` 权威快照（见 06、07、19 章） |
| 角色视角 | 发送侧 / 接收侧各自持有一份状态机（见 10 章） |
| 完成消息 | **一律由接收方发布**（上传方向 Server、下载方向 Client） |
| 缺失裁决 | **一律由接收方发起**：存在缺失时每 50ms 下发；窗口推进由 `window_update` **信用**事件驱动，空列表不再周期强制 |
| 可靠性 | 无逐包 ACK；接收方**信用 + 裁决**、发送方重传；**两层完整性**：包级 CRC32（覆盖头+载荷）+ 文件级 Blake3 |
| 完整性恢复 | **恢复阶梯**：①**摘要对帐**（逐区间比对摘要，零内容流量定位差异 → 定点补发）→ ②**复核轮**（全量重传）→ ③中止；包级校验失败只导致**该块定点补发** |
| 流控 | **两级在途上限**（均按 **symbol** 计）：会话级 `window` + **连接级** `connection_window`（同一连接上所有会话共享）；窗口由接收方 `window_update` 信用按收到量事件驱动推进 |
| 两级单位 | **逻辑块** `chunk_size`（`symbol_size` 的整数倍，`1 ≤ S ≤ 64`，默认 **64800**）+ **线缆/修复单位** `symbol_size`（常量 **1200**）；数据报承载 `K` 个 symbol，头带 `chunk_symbol`，`K`/长度由传输层反推；块内用 `u64` symbol 掩码判定收全；`K` 上限分「不分片」与「信任模式（可到 54，显式允许 IP 分片）」两档 |
| 素材共享 | Server 可**预置素材**构成**共享清单**；Client 查询 + 收通知后，用**既有** `download_start` 拉取（数据面全部复用） |
| 主动投递 | Server 可**主动投递**文件给在线 Client（`delivery_offer` → `delivery_response`）；方向恒为 download，传输流程全部复用 |
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

### 网页版可视化

全部 26 章的**可视化网页**位于 [`docs/site/`](docs/site/)，入口：
[`docs/site/index.html`](docs/site/index.html)（纯静态 HTML + CSS，无外部依赖，可离线打开）。

- [06 TCP 控制帧结构](docs/site/06-control-plane-tcp.html) · [08 UDP 数据包结构](docs/site/08-packet-format.html) · [24 端到端时序图](docs/site/24-sequence-diagrams.html)

**在线浏览**：<https://gx1727.github.io/LANWEFT/>

[![Pages](https://github.com/gx1727/LANWEFT/actions/workflows/pages.yml/badge.svg)](https://github.com/gx1727/LANWEFT/actions/workflows/pages.yml)

### 网页版部署（GitHub Pages）

站点由 GitHub Actions 构建并发布（见 `.github/workflows/pages.yml`）：

1. 仓库 Pages 的 Source 必须是 **GitHub Actions**（Settings → Pages → Build and deployment → Source）
2. `main` 分支推送时自动构建部署；也可在 Actions 页面手动触发（workflow_dispatch）

> ⚠️ **Source 若被改成「Deploy from a branch」，工作流会「成功但线上没更新」**：
> GitHub 会改用内置 Jekyll 构建发布仓库根目录，Actions 里的部署记录仍显示
> success，线上却是 Jekyll 站点、spec 页面全部 404。此时把 Source 改回
> **GitHub Actions**，再重跑一次工作流即可。可用
> `scripts/ensure-pages-source.sh`（需仓库管理员令牌）自动纠正。

构建脚本 `scripts/build-site.sh`（本地与 CI 共用）会：

- 把 `docs/site/*.html` 与 `style.css` 复制到 `_site/`（站点根）
- 把 `docs/spec/*.md` 复制到 `_site/spec/`，使页面内的「规范源文」链接在站点内可用
- 把站内链接 `../spec/` 改写为 `spec/`（仓库内保持 `../spec/`，便于直接浏览源码）
- 生成 `404.html` 兜底页与 `.nojekyll`

本地预览：

```bash
pip install -r scripts/requirements.txt   # 渲染器依赖 Python-Markdown
scripts/build-site.sh          # 生成 _site/
python3 -m http.server -d _site 8000
```

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

> **规范处于 0.x 设计阶段，线路格式尚未冻结**（见 06 章）。
> 版本号在此阶段**不承载兼容承诺** —— 没有发布过实现，也就没有"互不兼容"的对端。
> 实现**必须**以 06、07、08 章**正文**为准；
> 历史草案（JSON 载荷、`session_id` = u32 的二进制布局等）**一律不再可用**。
> 见 [26 章「已知限制」](docs/spec/26-roadmap.md)。

## 规范自检

规范处于 0.x 设计阶段，线路格式尚未冻结 —— **版本号不承载兼容承诺**，
因此真正的风险是「章与章之间对不上」。跨章不变量已固化为可执行检查：

```bash
python3 scripts/check-spec-consistency.py          # 打印报告，FAIL 时退出码 1
python3 scripts/check-spec-consistency.py --quiet  # 只输出失败与告警
```

检查项：

- 帧头长度与 `magic` / CRC 变体一致性（控制面 16 字节 / 数据面 28 字节）；
- **字段表机械校验**：06/07/08 章每张布局表的偏移连续性、
  字段总长与声明值一致、类型宽度与字节数一致（`u8`=1 / `u16`=2 / `u32`=4 / `u64`=8）；
- **状态机覆盖度**：10 章状态定义 / 编码 / 06 章 `state` 枚举三处一致；
  转移表的视角与状态集匹配（发送侧不出现 VERIFY / COMMIT）、
  终态无出边、非终态每个视角都有出边、全状态从 INIT 可达、
  转移触发列的消息名真实存在、消息表方向与正文「恒由 X 发布」一致；
- 定长记录长度跨章一致（06 章 vs 13 章）；
- 错误码集合闭合（引用了但没定义 / 定义了但正文没引用）；
- 规范默认值全章统一（`max_frame_len` / `window` / `chunk_size` …）；
- 章节交叉引用有效（不得引用已删除的章节）；
- **走查结论回归**：端到端走查得出的语义结论必须留在规范里
  （「待恢复会话的判定」表存在 · `PAUSED` 重连后保持暂停 ·
  断线重连不得无条件写「双方回到 TRANSFERRING」· 秒传仅上传方向 ·
  错误码终止类/过程类两分且无遗漏）；
- 站点页面与规范源文同步 · 本地链接可达。

走查记录存档于 [`docs/review/2026-11-walkthrough.md`](docs/review/2026-11-walkthrough.md)
（含已修项、待决项与方案选项）。
CI 在每次 push 与 PR 时自动运行（见 `.github/workflows/pages.yml`）。

## 参考实现


## License

[MIT](LICENSE) © 2026 gx1727
