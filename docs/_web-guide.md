# 站点渲染规范（docs/site/）

> **定位（规范性）**：站点是规范的**可视化导读**，**规范源文（`docs/spec/*.md`）才是唯一真源**。
> 站点页面**不得**成为规范事实的来源；站点与源文不一致时，**以源文为准**。
> 站点的价值在于**易读与可视化**（位域图、状态机、时序图），不在于「信息可得」——
> 源文随站点一起发布（`_site/spec/`），读者随时可读原文。

## 0. 分层渲染（为什么不再手抄）

早期站点页是「照着源文手写一遍」的产物，规范一改就漂移，且漂移无人发现
（`SITE-SYNC` 只抽查常量）。现在改为**分层渲染**：

```
docs/spec/NN-*.md          规范真源（唯一）
        │
        ├─ 正文 ──────────► 自动渲染（章节 / 表格 / 列表 / 代码块）
        │                  → 改 spec 即改 site，不再手工转抄
        │
        └─ 数据 ──────────► 可视化片段中的数据从源文抽取
                           （位域图、错误码总表等：不手敲偏移、不手抄错误码）

docs/site/_pages/NN.tpl     页面模板：骨架 + 占位顺序
docs/site/_parts/NN-*.html  可视化片段：位域图 / 状态机 / 时序图 / 本章要点
docs/site/_vars.json        变量声明：正则 → 命名变量（供片段引用）
        │
        └─► scripts/render-site.py ──► docs/site/NN-*.html（渲染产物，随站点发布）
```

**改规范的流程**：改 `docs/spec/*.md` → 跑 `python3 scripts/render-site.py` → 提交。
CI（`.github/workflows/pages.yml`）会跑 `render-site.py --check`，产物与源文不同步即**构建失败**。

## 1. 目录与文件名

| 路径 | 作用 |
|---|---|
| `docs/spec/NN-<slug>.md` | 规范源文（真源） |
| `docs/site/_pages/NN.tpl` | 第 NN 章的页面模板（`NN` = 章号） |
| `docs/site/_parts/NN-<name>.html` | 第 NN 章的片段，模板里用 `{{PART:<name>}}` 引用 |
| `docs/site/_vars.json` | 变量声明 |
| `docs/site/NN-<slug>.html` | **渲染产物**（由脚本生成，不要手改） |
| `docs/site/style.css` | 全站样式 |

章号 → 页面文件名映射见 `scripts/render-site.py` 的 `CHAP_FILES`。

## 2. 模板占位符

| 占位符 | 含义 |
|---|---|
| `{{RENDER:body}}` | 渲染该章源文正文（自动去掉 H1） |
| `{{RENDER:section:<小节标题>}}` | 只渲染指定小节（标题精确匹配或前缀匹配） |
| `{{PART:<name>}}` | 插入 `docs/site/_parts/<章号>-<name>.html` |
| `{{VAR:<name>}}` | 插入 `_vars.json` 声明的变量值 |
| `{{DIAGRAM:bitfield:<章号>:<表序号>}}` | 由源文字段表生成位域图 |
| `{{DIAGRAM:errcodes:<章号>}}` | 由源文错误码清单生成总表 |

**片段里不得手敲规范数值**：偏移、帧长、错误码、常量一律走 `{{VAR:}}` 或数据驱动图形，
否则源文一改，图就漂了。

## 3. 变量声明（`_vars.json`）

```json
{
  "magic":   {"chapter": "06", "pattern": "`(0x574E414C)`"},
  "crc_poly": {"chapter": "08", "pattern": "\\| 多项式 \\| (0x[0-9A-F]+) \\|"}
}
```

- `chapter`：源文所在章号；`pattern`：在源文中匹配的正则；`group`：取第几个捕获组（默认 1）。
- 变量在**源文与片段两侧都做空白无关比对**，因此规范写 `50ms`、页面写 `50 ms` 不算漂移。

## 4. 可用 class 速查（`style.css`）

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

## 5. 页面结构模板（照抄 `_web-template.html` 的骨架）

```html
<nav class="topnav">
  <a href="index.html">目录</a>
  <a href="PREV.html">◀ PREV_TITLE</a>
  <a href="NEXT.html">NEXT_TITLE ▶</a>
  <a href="../spec/NN-source.md">规范源文</a>
</nav>
<h1>…</h1>
{{PART:summary}}          <!-- 本章要点（导读文案） -->
{{DIAGRAM:...}}           <!-- 数据驱动图形 -->
{{RENDER:body}}           <!-- 规范正文 -->
<footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/NN-source.md">docs/spec/NN-source.md</a></footer>
```

「规范源文」链接的文件名必须是真实存在的源文文件名。

## 6. 迁移一章到分层渲染

1. 把现有页面里**有视觉价值**的部分（`.diagram` / 内联 SVG / 时序图 / 本章要点）剪到
   `docs/site/_parts/<章号>-<name>.html`；
2. 新建 `docs/site/_pages/<章号>.tpl`：骨架 + `{{PART:...}}` + `{{RENDER:body}}`；
3. 跑 `python3 scripts/render-site.py --chapter <章号>` 生成产物；
4. **比对**：确认源文里的表格行、字段、数值都在产物里（源文是真源，产物不得少于源文）；
5. 跑 `python3 scripts/check-spec-consistency.py` —— 站点页与源文的内容级校验必须通过。

## 7. 自检

生成后逐项确认：
- [ ] 顶部导航 4 个链接的文件都存在
- [ ] footer 的源文链接指向真实文件
- [ ] 表格列数与行数与源文一致，没有漏行
- [ ] 没有引入外部资源
- [ ] 无 `**` 星号残留（必须转成 `<strong>`）
- [ ] 片段里没有手敲的规范数值（偏移 / 长度 / 错误码）

## 8. 待迁移章节登记

迁移到分层渲染之前，个别图示密集的章节仍是**手写镜像**页面。
这类章节登记在 `scripts/check-spec-consistency.py` 的 `SITE_RENDER_EXEMPT`：

| 章 | 页面 | 待迁移部分 |
| --- | --- | --- |
| 06 | 控制帧结构 | 位域图 / 接收状态机 |
| 07 | 数据面 | UDP 包结构 / 通道对比图 |
| 09 | 会话模型 | 会话生命周期图 |
| 10 | 状态机 | 状态转移图 |

登记的效果：

- 「每章都有渲染模板」检查降级为 **WARN**，不再阻断 Pages 部署；
- 内容级同步检查（`SITE-SYNC` / `SITE-CONTENT`）**照常生效** ——
  手写镜像若与源文漂移（缺消息 / 缺错误码 / 常量不一致）仍会被 FAIL 拦下；
- 迁移完一章（按上一节流程生成 `_pages/NN.tpl` 与 `_parts/NN-*.html`），
  就把该章从 `SITE_RENDER_EXEMPT` 里删掉，检查自动恢复为严格模式。
