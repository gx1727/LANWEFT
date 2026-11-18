# 页面生成规范（给生成页面的 agent）

目标：把 `docs/spec/*.md` 的规范章节做成与 `docs/site/08-packet-format.html`、
`06-control-plane-tcp.html`、`24-sequence-diagrams.html` **同一视觉风格**的静态 HTML 页面。

## 0. 硬性要求

1. **内容必须忠实于源文**：`docs/spec/NN-*.md`。不得杜撰结论、不得编造字段/数值/状态。
   源文没有的细节不要写；源文的规范性措辞（必须 / 应当 / 可以 / 不得）必须保留其强度。
2. **不写代码实现建议**，只做规范的**可视化呈现**（表格 / 图 / 要点卡片）。
3. 只用**本页专有**的 class（见 §2）。除 `style.css` 外的样式若需要，写在 `<head>` 里的
   `<style>` 块中，并使用带页面前缀的类名（如 `.bm-bit`），避免与他人冲突。
4. 页面必须：UTF-8、HTML5、`<title>` 含章号与标题、无 JS（除确有交互需要）、
   **无外网依赖**（字体用系统字体，不引 CDN）。
5. 顶部导航与底部 footer **必须**与模板一致（见 `_template.html`）。
6. 文件名与章节映射见 §1；输出到 `docs/site/`。

## 1. 章节 → 文件名 / 标题映射

| 文件 | 章 | 标题（H1 用） |
|---|---|---|
| `00-overview.html` | 00 | 00 概览（Overview） |
| `01-architecture.html` | 01 | 01 系统架构（Architecture） |
| `02-terminology.html` | 02 | 02 术语（Terminology） |
| `03-design-goals.html` | 03 | 03 设计目标（Design Goals） |
| `04-non-goals.html` | 04 | 04 非目标（Non-Goals） |
| `05-protocol-stack.html` | 05 | 05 协议栈（Protocol Stack） |
| `07-data-plane-udp.html` | 07 | 07 数据面（UDP / TCP Fallback） |
| `09-session-model.html` | 09 | 09 会话模型（Session Model） |
| `10-state-machine.html` | 10 | 10 Session 状态机 |
| `11-flow-control.html` | 11 | 11 流控（Flow Control） |
| `12-reliability-model.html` | 12 | 12 可靠性模型（Reliability Model） |
| `13-resume-and-recovery.html` | 13 | 13 中断与恢复（Resume and Recovery） |
| `14-download-flow.html` | 14 | 14 下载流程（Server → Client） |
| `15-nat-and-network-limits.html` | 15 | 15 NAT 与网络限制 |
| `16-mobile-background-limits.html` | 16 | 16 移动端后台限制 |
| `17-memory-and-disk-model.html` | 17 | 17 内存与文件大小解耦 |
| `18-bitmap-and-chunk-map.html` | 18 | 18 位图与块图（Bitmap & Chunk Map） |
| `19-error-codes.html` | 19 | 19 错误码（Error Codes） |
| `20-security-model.html` | 20 | 20 安全模型（Security Model） |
| `21-acl-and-auth.html` | 21 | 21 访问控制与认证（ACL & Auth） |
| `23-client-identity.html` | 23 | 23 客户端身份（Client Identity） |
| `25-normative-marking.html` | 25 | 25 非规范性内容标注规范（Normative Marking） |
| `26-roadmap.html` | 26 | 26 下一阶段与路线图（Roadmap） |

导航的「上一章 / 下一章」按**章号顺序**（含已存在的 06 / 08 / 24），例如
`00` 的下一章是 `01-architecture.html`；`05` 的下一章是 `06-control-plane-tcp.html`；
`21` 的下一章是 `23-client-identity.html`；`23` 的下一章是 `24-sequence-diagrams.html`。

## 2. 可用 class 速查（`style.css`）

结构
- `.wrap`（页面容器，勿改）
- `.topnav` + `a`（导航胶囊；`a.active` 高亮当前）
- `h1 h2 h3`

卡片 / 表格
- `.card`（白底圆角卡片；`tbody tr + tr td` 自动画分隔线）
- `table` / `thead th` / `tbody td`；`td.mono`（等宽）、`td.num`（等宽居中）
- `table.sym td:first-child{white-space:nowrap}`（首列不折行）
- 语义色（用于字段名着色，可自行在 `<style>` 里定义自己的）：
  `td.c-session/.c-chunk/.c-len/.c-flags/.c-payload/.c-crc/.c-frame/.c-type/.c-muted`
  对应背景色变量 `--b-session/--b-chunk/--b-len/--b-flags/--b-payload/--b-crc/--b-frame/--b-type/--b-ext`
  对应前景色变量 `--c-session/--c-chunk/--c-len/--c-flags/--c-payload/--c-crc/--c-frame/--c-type/--c-muted`

列表 / 提示
- `ul.spec`（带项目符号的要点列表）
- `.note`（左侧竖线提示条）、`.note.blue`（蓝色）、`.note.warn`（橙色）
- `code`（行内代码）、`strong`（强调）

图示（CSS Grid 位域图 / 通用条带图）
- `.diagram`（外框）> `.fields`（`style="--cols:N"` 决定列数，N 可取 1–12）> `.cell`
- `.cell`（`.wide` 跨全部列，`.half` 跨 2 列，`.span3 .span4 .span8` 跨指定列数）
- `.cell.ruler-title` / `.cell.bitnum`（刻度行）
- 语义底色：`.f-session .f-chunk .f-len .f-flags .f-payload .f-crc .f-frame .f-type .f-body .f-ext .f-muted`
- `.legend` + `.swatch`（图例）、`.caption`（等宽小字说明）
- 复杂图形（如状态机）可用**内联 SVG**：放在 `.diagram` 内，宽度用 `viewBox` + `width:100%`

## 3. 页面结构模板（照抄 `_template.html` 的骨架）

```html
<nav class="topnav">
  <a href="index.html">目录</a>
  <a href="PREV.html">◀ PREV_TITLE</a>
  <a href="NEXT.html">NEXT_TITLE ▶</a>
  <a href="../spec/NN-source.md">规范源文</a>
</nav>
<h1>…</h1>
<div class="note blue"><strong>本章要点</strong>：…</div>
…正文…
<footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/NN-source.md">docs/spec/NN-source.md</a></footer>
```

「规范源文」链接的文件名必须是真实存在的源文文件名。

## 4. 内容组织建议

- **表格优先**：源文里的表格原样转成 HTML `<table>`（列名可精炼，但单元格内容不得丢关键信息）。
- **规范性措辞**：源文的 **必须 / 应当 / 可以 / 不得 / MUST** 等用 `<strong>` 标出；
  字段名、消息名、常量、代码值用 `<code>` 标出。
- **图示**：源文有状态机 / 分层 / 流程 / 位图 / 数值关系时，尽量画成
  `.diagram` + `.fields` 的条带图或内联 SVG（不要只写文字描述）。
- **长度**：覆盖整章，但不要逐段照抄散文；表格保持完整，散文提炼为要点。
- 页面末尾可加一条 `.note` 总结「本章与其它章的关系 / 常见实现陷阱」（必须源自源文内容）。

## 5. 自检

生成后逐项确认：
- [ ] 顶部导航 4 个链接的文件都存在（06 / 08 / 24 页面已存在）
- [ ] footer 的源文链接指向真实文件
- [ ] 表格列数与行数与源文一致，没有漏行
- [ ] 没有引入外部资源
- [ ] 无 `**` 星号残留（必须转成 `<strong>`）
