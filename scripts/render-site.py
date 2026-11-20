#!/usr/bin/env python3
"""站点渲染器 —— 规范源文（docs/spec/*.md）→ 站点页面（docs/site/*.html）

设计要点（见 docs/_web-guide.md「分层渲染」）：

  * **规范正文自动渲染**：源文 md 的章节、表格、列表、代码块直接渲染成 HTML。
    改 spec 即改 site，正文不再手工转抄 —— 这是「site 跟不上 spec」的根治办法。
  * **可视化是片段**：位域图、状态机图、时序图等有视觉价值的内容放在
    `docs/site/_parts/NN-*.html`，由页面模板用 `{{PART:name}}` 注入。
  * **图里的数据不手敲**：结构性数据（字段偏移、帧长、常量）由源文表格
    抽取后生成 —— `{{DIAGRAM:bitfield:08}}` 直接从 08 章的字段表画出位域图；
    `{{VAR:name}}` 取自 `docs/site/_vars.json` 声明的正则抽取。
  * **页面是模板**：`docs/site/_pages/NN.tpl` 定义骨架与占位顺序，
    渲染产物写回 `docs/site/NN-*.html`（Pages 直接使用该产物）。

用法：
    python3 scripts/render-site.py              # 渲染所有有模板的章节
    python3 scripts/render-site.py --chapter 08 # 只渲染某一章
    python3 scripts/render-site.py --check      # 只校验产物与源文是否同步（CI 门禁）

退出码：0 = 一致；1 = 存在差异（--check 时）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "docs", "spec")
SITE = os.path.join(ROOT, "docs", "site")
PAGES = os.path.join(SITE, "_pages")
PARTS = os.path.join(SITE, "_parts")
VARS = os.path.join(SITE, "_vars.json")

# 章节号 → 页面文件名（与 00 章 / 99 章的章节索引一致）
CHAP_FILES = {
    "00": "00-overview", "01": "01-architecture", "02": "02-terminology",
    "03": "03-design-goals", "04": "04-non-goals", "05": "05-protocol-stack",
    "06": "06-control-plane-tcp", "07": "07-data-plane-udp",
    "08": "08-packet-format", "09": "09-session-model",
    "10": "10-state-machine", "11": "11-flow-control",
    "12": "12-reliability-model", "13": "13-resume-and-recovery",
    "14": "14-download-flow", "15": "15-nat-and-network-limits",
    "16": "16-mobile-background-limits", "17": "17-memory-and-disk-model",
    "18": "18-bitmap-and-chunk-map", "19": "19-error-codes",
    "20": "20-security-model", "21": "21-acl-and-auth",
    "23": "23-client-identity", "24": "24-sequence-diagrams",
    "25": "25-normative-marking", "26": "26-roadmap",
}


# ---------------------------------------------------------------- 源文解析

def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def spec_files() -> dict[str, str]:
    """章号 → 源文全文。"""
    out: dict[str, str] = {}
    for name in sorted(os.listdir(SPEC)):
        if name.endswith(".md"):
            out[name[:2]] = read(os.path.join(SPEC, name))
    return out


def split_sections(text: str) -> list[tuple[int, str, list[str]]]:
    """把 md 切成 (标题级别, 标题, 行列表)；正文（首个 H1 之前）级别记为 0。"""
    out: list[tuple[int, str, list[str]]] = []
    level, title, buf = 0, "", []
    for line in text.split("\n"):
        m = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if m:
            if title or buf:
                out.append((level, title, buf))
            level, title, buf = len(m.group(1)), m.group(2).strip(), []
        else:
            buf.append(line)
    if title or buf:
        out.append((level, title, buf))
    return out


def find_section(text: str, selector: str) -> str | None:
    """按标题取小节正文；selector 可为精确标题或标题前缀。"""
    for level, title, buf in split_sections(text):
        if level and (title == selector or title.startswith(selector)):
            return "\n".join(buf).strip("\n")
    return None


def find_tables(text: str) -> list[list[list[str]]]:
    """抽出所有 md 表格：返回 [[行][列][单元格]]，行 0 为表头。"""
    tables: list[list[list[str]]] = []
    cur: list[list[str]] = []
    for line in text.split("\n"):
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") and c for c in cells):
                continue  # 对齐行
            cur.append(cells)
        else:
            if len(cur) >= 2:
                tables.append(cur)
            cur = []
    if len(cur) >= 2:
        tables.append(cur)
    return tables


def pick_table(text: str, index: int, must: tuple[str, ...] = ()) -> list[list[str]] | None:
    """取第 index 张表；must 非空时要求表头包含这些列名。"""
    tables = find_tables(text)
    if index >= len(tables):
        return None
    tbl = tables[index]
    if must and not all(any(m in c for c in tbl[0]) for m in must):
        return None
    return tbl


# ---------------------------------------------------------------- md → HTML

def md_to_html(text: str) -> str:
    """md → HTML（表格包 .card，代码块用 .codeblock）。"""
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    html = md.convert(text)
    html = html.replace("<table>", '<div class="card"><table>')
    html = html.replace("</table>", "</table></div>")
    html = html.replace("<pre>", '<pre class="codeblock">')
    return html


def render_section(spec: dict[str, str], chap: str, selector: str) -> str:
    body = find_section(spec.get(chap, ""), selector)
    if body is None:
        raise SystemExit(f"[render-site] {chap} 章找不到小节「{selector}」")
    return md_to_html(body)


# ---------------------------------------------------------------- 变量抽取

def load_vars() -> dict:
    if not os.path.exists(VARS):
        return {}
    return json.loads(read(VARS))


def build_vars(spec: dict[str, str]) -> dict[str, str]:
    """按 _vars.json 的正则声明，从源文抽取命名变量。"""
    out: dict[str, str] = {}
    for name, rule in load_vars().items():
        chap = rule.get("chapter")
        text = spec.get(chap, "")
        m = re.search(rule["pattern"], text, re.S)
        if not m:
            continue
        out[name] = m.group(rule.get("group", 1))
    return out


# ---------------------------------------------------------------- 位域图生成

def bitfield_diagram(spec: dict[str, str], chap: str, table_index: int) -> str:
    """由源文的字段表生成位域图 —— 图里的偏移不手敲。

    源文表需含「字段 / 偏移 / 大小」三列；每列网格代表 4 字节。
    """
    tbl = pick_table(spec.get(chap, ""), table_index, must=("字段", "偏移"))
    if not tbl:
        raise SystemExit(f"[render-site] {chap} 章第 {table_index} 张表不是字段表")

    head = tbl[0]
    col_field = next(i for i, c in enumerate(head) if "字段" in c)
    col_off = next(i for i, c in enumerate(head) if "偏移" in c)
    col_size = next((i for i, c in enumerate(head) if "大小" in c or "字节" in c), None)
    col_desc = next((i for i, c in enumerate(head) if "说明" in c), None)

    fields: list[tuple[str, int | None, int | None, str]] = []
    for row in tbl[1:]:
        name = row[col_field].strip()
        off = row[col_off].strip()
        if re.match(r"^\d+\s*-\s*\d+$", off):
            lo, hi = off.split("-", 1)
            start, end = int(lo), int(hi)
        elif re.match(r"^\d+$", off):
            start = end = int(off)
        else:
            start = end = None  # 变长字段（如 16.. / 16+N）
        desc = row[col_desc].strip() if col_desc and len(row) > col_desc else ""
        fields.append((name, start, end, desc))

    fixed = [(n, s, e, d) for n, s, e, d in fields if s is not None]
    var = [(n, d) for n, s, e, d in fields if s is None]

    UNIT = 4  # 每格 4 字节
    header_bytes = (max(e for _, _, e, _ in fixed) + 1) if fixed else 0
    cols = max(1, -(-header_bytes // UNIT))

    def span(size: int) -> int:
        return max(1, -(-size // UNIT))

    def cls(name: str) -> str:
        key = name.lower()
        for token, c in (("session", "f-session"), ("chunk", "f-chunk"),
                         ("len", "f-len"), ("flags", "f-flags"),
                         ("payload", "f-payload"), ("crc", "f-crc"),
                         ("frame", "f-frame"), ("type", "f-type")):
            if token in key:
                return c
        return "f-body"

    ruler = "".join(
        f'<div class="cell bitnum">{i * UNIT}-{min((i + 1) * UNIT, header_bytes) - 1}</div>'
        for i in range(cols))
    cells = []
    for name, start, end, desc in fixed:
        size = end - start + 1
        s = span(size)
        cells.append(
            f'<div class="cell {cls(name)}" style="grid-column:span {s}">'
            f'{name}<br><span class="mono">{start}-{end}</span></div>')
    for name, desc in var:
        cells.append(
            f'<div class="cell {cls(name)} wide">{name}'
            f'<br><span class="mono">变长</span></div>')
    legend = "".join(
        f'<span><i class="swatch" style="background:var(--b-{c[2:]})"></i>{name}</span>'
        for name, _, _, _ in fields for c in [cls(name)])

    return (
        '<div class="diagram">\n'
        f'  <div class="fields" style="--cols:{cols}">\n'
        '    <div class="cell ruler-title">字段布局（每格 4 字节；偏移取自源文表格）</div>\n'
        f'    {ruler}\n'
        + "\n".join(f"    {c}" for c in cells) + "\n"
        '  </div>\n'
        '</div>\n'
        f'<div class="legend">{legend}</div>\n'
        f'<div class="caption">头部共 {header_bytes} 字节；'
        '字段偏移与大小由源文表格抽取，图与表同源。</div>'
    )


# ---------------------------------------------------------------- 占位符展开

def errcode_table(spec: dict[str, str], chap: str) -> str:
    """由源文的错误码清单生成汇总表 —— 分类、说明与「可否作为终止原因」都从源文来。

    源文结构：`### <分类>` 小节下的 `- \\`CODE\\`：说明` 条目；
    「终止类错误码清单」与「其余错误码一律为过程类」两段决定终止性。
    """
    text = spec.get(chap, "")
    sections = split_sections(text)

    # 终止类 / 过程类
    terminal: set[str] = set()
    m = re.search(r"\*\*终止类错误码清单（规范性）\*\*：(.+?)。\n", text, re.S)
    if m:
        terminal = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", m.group(1)))

    rows: list[tuple[str, str, str, bool]] = []
    cur_cat = ""
    for level, title, buf in sections:
        if level != 3:
            continue
        name = title.strip()
        if name in {"SESSION", "TRANSPORT", "INTEGRITY", "AUTH", "TIMEOUT",
                    "STORAGE", "PROTOCOL"}:
            cur_cat = name
        if not cur_cat:
            continue
        for line in buf:
            mm = re.match(r"^- `([A-Z][A-Z0-9_]+)`[：:]\s*(.+?)\s*$", line.strip())
            if mm:
                rows.append((mm.group(1), cur_cat, mm.group(2), mm.group(1) in terminal))

    def inline(text: str) -> str:
        """把 md 行内标记（**x** / `x`）转成 HTML，避免星号残留。"""
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        return text

    body = "".join(
        f"<tr><td class=\"mono\">{code}</td><td>{cat}</td><td>{inline(desc)}</td>"
        f"<td>{'是' if term else '否'}</td></tr>"
        for code, cat, desc, term in rows)
    return (
        '<div class="card">\n<table>\n'
        '<thead><tr><th>错误码</th><th>分类</th><th>说明</th>'
        '<th>可作终止原因</th></tr></thead>\n'
        f"<tbody>\n{body}\n</tbody>\n</table>\n</div>\n"
        '<div class="caption">错误码、分类、说明与终止性均由源文清单抽取；'
        '「可作终止原因」按源文「终止类 / 过程类」两分得出。</div>'
    )


PLACEHOLDER = re.compile(r"\{\{(PART|RENDER|DIAGRAM|VAR):([^}]+)\}\}")

def expand(text: str, chap: str, spec: dict[str, str], variables: dict[str, str]) -> str:
    """展开模板中的占位符。"""
    def sub(m: re.Match) -> str:
        kind, arg = m.group(1), m.group(2).strip()
        if kind == "PART":
            path = os.path.join(PARTS, f"{chap}-{arg}.html")
            if not os.path.exists(path):
                raise SystemExit(f"[render-site] 缺少片段 {path}")
            return read(path)
        if kind == "VAR":
            if arg not in variables:
                raise SystemExit(f"[render-site] 未定义的变量 {arg}")
            return variables[arg]
        if kind == "DIAGRAM":
            parts = arg.split(":")
            if parts[0] == "bitfield":
                return bitfield_diagram(spec, parts[1], int(parts[2]))
            if parts[0] == "errcodes":
                return errcode_table(spec, parts[1])
            raise SystemExit(f"[render-site] 未知图形 {arg}")
        if kind == "RENDER":
            sub_arg = arg.split(":")
            if sub_arg[0] == "body":
                body = spec[chap]
                # 去掉 H1 与首个 H1 之前的导语
                m = re.search(r"^#\s+.*$", body, re.M)
                body = body[m.end():] if m else body
                return md_to_html(body).strip()
            if sub_arg[0] == "section":
                return render_section(spec, chap, sub_arg[2]).strip()
        raise SystemExit(f"[render-site] 无法解析的占位符 {m.group(0)}")

    prev = None
    while prev != text:
        prev = text
        text = PLACEHOLDER.sub(sub, text)
    return text


# ---------------------------------------------------------------- 渲染主流程

def render_all(only: str | None = None) -> dict[str, str]:
    """渲染所有（或指定）章节，返回 {页面文件名: 产物内容}。"""
    spec = spec_files()
    variables = build_vars(spec)
    out: dict[str, str] = {}
    if not os.path.isdir(PAGES):
        return out
    for tpl_name in sorted(os.listdir(PAGES)):
        if not tpl_name.endswith(".tpl"):
            continue
        chap = tpl_name[:2]
        if only and chap != only:
            continue
        target = CHAP_FILES.get(chap)
        if not target:
            raise SystemExit(f"[render-site] 未知章号 {chap}")
        tpl = read(os.path.join(PAGES, tpl_name))
        out[target + ".html"] = expand(tpl, chap, spec, variables)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="从规范源文渲染站点页面")
    ap.add_argument("--check", action="store_true",
                    help="只校验产物是否与源文同步，不写文件")
    ap.add_argument("--chapter", help="只处理某一章（如 08）")
    args = ap.parse_args()

    rendered = render_all(args.chapter)
    if not rendered:
        print("[render-site] 没有可渲染的页面（docs/site/_pages/ 为空）")
        return 0

    if args.check:
        bad = []
        for name, content in sorted(rendered.items()):
            path = os.path.join(SITE, name)
            if not os.path.exists(path):
                bad.append(f"{name} 尚未生成")
            elif read(path) != content:
                bad.append(f"{name} 与源文不同步（请运行 scripts/render-site.py）")
        if bad:
            for b in bad:
                print(f"  - {b}")
            print(f"[render-site] {len(bad)} 个页面未同步")
            return 1
        print(f"[render-site] {len(rendered)} 个页面与源文同步")
        return 0

    for name, content in sorted(rendered.items()):
        path = os.path.join(SITE, name)
        old = read(path) if os.path.exists(path) else None
        if old != content:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            print(f"  写入 {name}")
    print(f"[render-site] 渲染 {len(rendered)} 个页面")
    return 0


if __name__ == "__main__":
    sys.exit(main())
