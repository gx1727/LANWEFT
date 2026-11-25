#!/usr/bin/env python3
"""LANWEFT 规范一致性自检（Spec Consistency Checker）

规范处于 0.x 设计阶段，线路格式尚未冻结，版本号不承载兼容承诺 ——
因此「章与章之间对不上」是主要风险。本脚本把跨章不变量固化为可执行检查：

  * 帧头常量（长度、magic、CRC 变体）在各章与站点页面之间一致
  * 消息体定长记录长度在 06 章与 13 章之间一致
  * 错误码集合闭合（引用了但没定义 / 定义了但没引用）
  * 规范默认值（max_frame_len / window / chunk_size / 心跳 / 裁决周期）全章统一
  * 交叉引用的章节存在且未被删除的章节不再被引用
  * 站点 HTML 与规范源文的关键常量同步
  * 站点 HTML 与规范源文的**内容级**同步（每章的消息 / 错误码 / 规范常量覆盖）

用法：
    python3 scripts/check-spec-consistency.py            # 打印报告，失败时退出码 1
    python3 scripts/check-spec-consistency.py --quiet    # 只输出失败与告警
    python3 scripts/check-spec-consistency.py --warn-as-error

退出码：0 = 全部通过（可能有 WARN）；1 = 存在 FAIL。
"""

from __future__ import annotations

import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "docs", "spec")
SITE = os.path.join(ROOT, "docs", "site")

# ---------------------------------------------------------------- 基础工具

class Result:
    def __init__(self) -> None:
        self.checks: list[tuple[str, str, str, list[str]]] = []

    def ok(self, cid: str, name: str, detail: str = "") -> None:
        self.checks.append(("PASS", cid, name, [detail] if detail else []))

    def fail(self, cid: str, name: str, details: list[str]) -> None:
        self.checks.append(("FAIL", cid, name, details))

    def warn(self, cid: str, name: str, details: list[str]) -> None:
        self.checks.append(("WARN", cid, name, details))

    def counts(self) -> tuple[int, int, int]:
        p = sum(1 for c in self.checks if c[0] == "PASS")
        f = sum(1 for c in self.checks if c[0] == "FAIL")
        w = sum(1 for c in self.checks if c[0] == "WARN")
        return p, f, w


def load_spec() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in sorted(os.listdir(SPEC)):
        if name.endswith(".md"):
            with open(os.path.join(SPEC, name), encoding="utf-8") as fh:
                out[name[:2]] = fh.read()
    return out


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def chap_files() -> list[str]:
    return sorted(f for f in os.listdir(SPEC) if f.endswith(".md"))


# ---------------------------------------------------------------- 各类检查

def check_frame_header(spec: dict[str, str], res: Result) -> None:
    """帧头长度、magic、CRC 变体在全仓一致。"""
    # 1) 控制面 / 数据面帧头长度
    ctrl = re.search(r"FRAME_HEADER_SIZE`?\s*=\s*\*\*(\d+)\s*字节\*\*", spec.get("06", ""))
    data = re.search(r"FRAME_HEADER_SIZE\s*=.*?=\s*(\d+)\s*字节", spec.get("07", ""))
    if not ctrl or not data:
        res.fail("FRAME-SIZE", "帧头长度声明",
                 ["06/07 章未找到 FRAME_HEADER_SIZE 声明"])
        return
    ctrl_n = int(ctrl.group(1))
    data_n = int(data.group(1))
    if ctrl_n != 16:
        res.fail("FRAME-SIZE", "控制面帧头长度 = 16",
                 [f"06 章声明为 {ctrl_n}，期望 16"])
    else:
        res.ok("FRAME-SIZE", "控制面帧头长度 = 16")

    if data_n != 28:
        res.fail("FRAME-SIZE", "数据面 TCP 帧头长度 = 28",
                 [f"07 章声明为 {data_n}，期望 28"])
    else:
        res.ok("FRAME-SIZE", "数据面 TCP 帧头长度 = 28")

    # 2) 帧长下界与 body 长度表达式必须等于帧头长度
    bad: list[str] = []
    for chap, hdr in (("06", ctrl_n), ("07", data_n)):
        text = spec.get(chap, "")
        for pat, desc in (
            (r"frame_len`?\s*\*\*必须\*\*\s*≥\s*\*\*(\d+)\*\*", "frame_len 下界"),
            (r"frame_len − (\d+)", "frame_len − N"),
            (r"frame_len = (\d+) \+ payload_len", "frame_len = N + payload_len"),
            (r"帧内偏移 (\d+)", "帧内偏移"),
        ):
            for m in re.finditer(pat, text):
                got = int(m.group(1))
                if got != hdr:
                    bad.append(f"{chap} 章 {desc} = {got}，期望 {hdr}")
    if bad:
        res.fail("FRAME-SIZE", "帧长表达式与帧头长度一致", bad)
    else:
        res.ok("FRAME-SIZE", "帧长表达式与帧头长度一致")

    # 3) magic 常量
    stale = []
    for chap, text in spec.items():
        if "0x4C415357" in text:
            stale.append(f"{chap} 章仍含陈旧 magic 0x4C415357")
    if stale:
        res.fail("MAGIC", "magic 常量唯一", stale)
    else:
        res.ok("MAGIC", "magic 常量唯一（0x574E414C）")

    missing = [c for c in ("06", "07")
               if "0x574E414C" not in spec.get(c, "")
               or "4C 41 4E 57" not in spec.get(c, "")]
    if missing:
        res.fail("MAGIC", "magic 的数值与线上字节序均已声明",
                 [f"{c} 章缺少 0x574E414C 或 4C 41 4E 57" for c in missing])
    else:
        res.ok("MAGIC", "magic 的数值与线上字节序均已声明")

    # 4) CRC 变体唯一：CRC-32C 只允许出现在 08 章的历史说明里
    bad = []
    for chap, text in spec.items():
        if "CRC-32C" in text and chap != "08":
            bad.append(f"{chap} 章出现第二个 CRC 变体 CRC-32C")
    if bad:
        res.fail("CRC-VARIANT", "CRC32 变体唯一", bad)
    else:
        res.ok("CRC-VARIANT", "CRC32 变体唯一（CRC-32/ISO-HDLC）")


def check_record_sizes(spec: dict[str, str], res: Result) -> None:
    """06 章与 13 章对同一定长记录的长度声明必须一致。"""
    pairs = [
        ("login.resume[] 记录",
         r"resume\[\]`?：`resume_count` 条记录，每条 \*\*(\d+) 字节定长\*\*",
         r"`resume_count` 条 \*\*(\d+) 字节定长\*\*记录"),
        ("login_ack 快照记录",
         r"每条 = \*\*(\d+) 字节定长\*\*",
         r"每条 =\s*\*\*(\d+) 字节定长\*\*"),
    ]
    bad: list[str] = []
    for name, pat06, pat13 in pairs:
        a = re.search(pat06, spec.get("06", ""))
        b = re.search(pat13, spec.get("13", ""))
        if not a or not b:
            bad.append(f"{name}：06 或 13 章未找到长度声明")
            continue
        if a.group(1) != b.group(1):
            bad.append(f"{name}：06 章 = {a.group(1)}，13 章 = {b.group(1)}")
    if bad:
        res.fail("RECORD-SIZE", "定长记录长度跨章一致", bad)
    else:
        res.ok("RECORD-SIZE", "定长记录长度跨章一致")


# 非错误码的大写标识符：状态名、状态机状态、标志位、系统常量
NON_ERROR_TOKENS = {
    # 会话状态
    "INIT", "NEGOTIATING", "TRANSFERRING", "PAUSED", "VERIFY",
    "COMMIT", "COMPLETED", "ABORTED",
    # 接收状态机
    "SYNC", "RESYNC", "CLOSED",
    # 标志位
    "FLAG_DATA", "FLAG_RESEND", "FLAG_LAST_CHUNK", "FLAG_PROBE", "FLAG_BIND",
    "FLAG_PEER_PROBE",
    # 其它系统常量
    "FRAME_HEADER_SIZE", "TRAILER_SIZE", "KDF", "TCP_NODELAY", "ENOSPC", "EROFS",
    "UDP_PROBE", "UDP_PROBE_ACK", "UDP_HELLO",
}


def check_error_codes(spec: dict[str, str], res: Result) -> None:
    """错误码集合闭合。"""
    defined = set(re.findall(r"^- `([A-Z][A-Z0-9_]+)`", spec.get("19", ""), re.M))
    if not defined:
        res.fail("ERRCODE-CLOSE", "错误码定义集合非空", ["19 章未解析出任何错误码"])
        return

    used: dict[str, set[str]] = {}
    for chap, text in spec.items():
        # 19 章是定义处；26 章是过程性章节（修订记录 / 待定议题），
        # 其中的历史标识符不构成协议引用
        if chap in ("19", "26"):
            continue
        for tok in set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", text)):
            used.setdefault(tok, set()).add(chap)
        # 正文也可能不带反引号地提到错误码（如「按 UDP_UNAVAILABLE 降级」）
        for tok in defined:
            if re.search(rf"(?<![A-Z0-9_]){tok}(?![A-Z0-9_])", text):
                used.setdefault(tok, set()).add(chap)

    unknown = sorted(t for t in used if t not in defined and t not in NON_ERROR_TOKENS)
    if unknown:
        res.fail("ERRCODE-CLOSE", "被引用的大写标识符均已在 19 章定义",
                 [f"{t}（出现于 {', '.join(sorted(used[t]))} 章）" for t in unknown])
    else:
        res.ok("ERRCODE-CLOSE", "被引用的大写标识符均已在 19 章定义")

    # 定义了但正文从未引用 → 提示（可能是遗漏上线路）
    unused = sorted(t for t in defined
                     if t not in used and t != "UNKNOWN_ERROR")
    if unused:
        res.warn("ERRCODE-USE", "已定义但正文未引用的错误码",
                 [f"{t}" for t in unused])


def check_defaults(spec: dict[str, str], res: Result) -> None:
    """规范默认值全章统一。"""
    bad: list[str] = []

    # max_frame_len
    for chap in ("02", "06", "07", "18"):
        for m in re.finditer(r"max_frame_len`?[^\n]{0,12}?(\d+)\s*(MiB|KiB)",
                             spec.get(chap, "")):
            if m.group(0).strip().startswith("max_frame_len`") and \
                    m.group(1) != "1":
                bad.append(f"{chap} 章 max_frame_len = {m.group(1)} {m.group(2)}，期望 1 MiB")

    # window / connection_window 默认值
    for chap in ("06", "11"):
        for line in spec.get(chap, "").split("\n"):
            if "规范默认" not in line:
                continue
            nums = re.findall(r"(\d{3,5})", line)
            if not nums:
                continue
            if "connection_window" in line:
                if nums[0] != "16384":
                    bad.append(f"{chap} 章 connection_window 默认 = {nums[0]}，期望 16384")
            elif "window" in line:
                if nums[0] != "8192":
                    bad.append(f"{chap} 章 window 默认 = {nums[0]}，期望 8192")

    # chunk_size 上限与推荐范围（仅统计确实提到 chunk_size 的行）
    for chap in ("02", "08", "09", "11", "99"):
        for line in spec.get(chap, "").split("\n"):
            if "chunk_size" not in line:
                continue
            for m in re.finditer(r"上限 \*?\*?(\d{3,4})", line):
                if m.group(1) != "1400":
                    bad.append(f"{chap} 章 chunk_size 上限 = {m.group(1)}，期望 1400")

    if bad:
        res.fail("DEFAULTS", "规范默认值全章统一", bad)
    else:
        res.ok("DEFAULTS", "规范默认值全章统一")

    # 09 章的 chunk_size 取值范围表述与 08 章口径差异 → WARN
    if re.search(r"取值范围为 1024[–-]1400", spec.get("09", "")):
        res.warn("DEFAULTS", "chunk_size 范围表述口径",
                 ["09 章写作「取值范围为 1024–1400」，08 章写作「建议 1024–1350，上限 1400」；"
                  "建议统一措辞，避免被读成两种上限"])


def check_cross_refs(spec: dict[str, str], res: Result) -> None:
    """交叉引用的章节必须存在；已删除的章节不得再被引用。"""
    files = {f[:2] for f in chap_files()}
    deleted = {"22"}  # 22 章「MQTT Topic 规范」已整章删除
    bad: list[str] = []
    for chap, text in spec.items():
        # 规范性引用（见 NN 章 / 按 NN 章）不得指向已删除章节；
        # 26 章「变更摘要 / 修订记录」中的历史提及不算引用。
        for m in re.finditer(r"(见|按|依|据)\s*([0-9]{2}(?:、[0-9]{2})*)\s*章", text):
            for num in m.group(2).split("、"):
                if num in deleted:
                    bad.append(f"{chap} 章规范性引用了已删除的 {num} 章")
                elif num not in files:
                    bad.append(f"{chap} 章引用了不存在的 {num} 章")
        # 任意位置的章节号都不得指向不存在的章节
        for m in re.finditer(r"([0-9]{2}(?:、[0-9]{2})*)\s*章", text):
            for num in m.group(1).split("、"):
                if num not in files and num not in deleted:
                    bad.append(f"{chap} 章引用了不存在的 {num} 章")
    if bad:
        res.fail("XREF", "章节交叉引用有效", bad)
    else:
        res.ok("XREF", "章节交叉引用有效")

    # 章节文件齐备（00–26，缺 22）
    missing = [f"{n:02d}" for n in range(0, 27)
               if f"{n:02d}" not in files and f"{n:02d}" not in deleted]
    if missing:
        res.fail("CHAPTERS", "章节文件齐备", [f"缺少 {', '.join(missing)}"])
    else:
        res.ok("CHAPTERS", "章节文件齐备（00–26，22 已删除）")


def check_site_sync(spec: dict[str, str], res: Result) -> None:
    """站点 HTML 与规范源文的关键常量同步。"""
    expect = {
        "06-control-plane-tcp.html": ["0x574E414C", "4C 41 4E 57", "frame_len − 16",
                                      "16 字节", "MAGIC_MISMATCH", "HEADER_CRC_INVALID",
                                      "FRAME_LEN_INVALID", "TIMEOUT_HEARTBEAT",
                                      "CONNECTION_FAILED", "CONNECTION_CLOSED"],
        "00-overview.html": ["u32 magic", "u32 header_crc32"],
        "02-terminology.html": ["16 字节定长帧头", "失步"],
        "19-error-codes.html": ["MAGIC_MISMATCH", "HEADER_CRC_INVALID", "FRAME_LEN_INVALID"],
        "26-roadmap.html": ["0x574E414C"],
        # 站点页面与规范源文的数值漂移防护（曾出现 PROBE 载荷长度 4/5 与规范 8/9 不符）
        "07-data-plane-udp.html": ["载荷长度", "PROBE_ACK", "8", "9"],
        "08-packet-format.html": ["CHUNK_ALREADY_RECEIVED"],
        "12-reliability-model.html": ["NETWORK_ERROR", "TIMEOUT_HEARTBEAT"],
        "17-memory-and-disk-model.html": ["DATABASE_ERROR"],
    }
    bad: list[str] = []
    for fname, tokens in expect.items():
        text = read(os.path.join(SITE, fname))
        if not text:
            bad.append(f"{fname} 不存在")
            continue
        for tok in tokens:
            if tok not in text:
                bad.append(f"{fname} 缺少 {tok!r}")
    if bad:
        res.fail("SITE-SYNC", "站点页面与规范源文同步", bad)
    else:
        res.ok("SITE-SYNC", "站点页面与规范源文同步")

    # 站点不得残留陈旧常量
    stale = []
    for fname in os.listdir(SITE):
        if fname.endswith(".html") and "0x4C415357" in read(os.path.join(SITE, fname)):
            stale.append(fname)
    if stale:
        res.fail("SITE-SYNC", "站点无陈旧 magic 常量", stale)
    else:
        res.ok("SITE-SYNC", "站点无陈旧 magic 常量")


# ---------------------------------------------------------------- 站点内容级同步

# 未做可视化页面的章节（显式豁免，避免默默漏页）
SITE_PAGE_EXEMPT: dict[str, str] = {
    "99": "术语速查表：内容与 02 章重复，未单独做可视化页面",
}

# 已登记但**尚未迁移到分层渲染**的章节（页面仍为手写镜像）。
#
# 迁移一章的流程见 docs/_web-guide.md「迁移一章到分层渲染」：
#   视觉片段 → docs/site/_parts/NN-*.html
#   骨架     → docs/site/_pages/NN.tpl（含 {{RENDER:body}}）
#
# 登记在此的章：
#   * 「每章都有渲染模板」检查降级为 WARN —— 不再阻断 Pages 部署；
#   * 内容级同步检查（SITE-SYNC / SITE-CONTENT）照常生效 —— 手写镜像若与源文
#     漂移（缺消息 / 缺错误码 / 常量不一致）仍会被 FAIL 拦下；
#   * 迁移完一章就从这里删掉该章，检查自动恢复为严格模式。
SITE_RENDER_EXEMPT: dict[str, str] = {
    # 当前为空：全部章节均已迁移到分层渲染（页面由 _pages/NN.tpl + 源文渲染产出）。
    # 若将来新增章节来不及迁移，在此登记「章号: 原因」，
    # 该章的「每章都有渲染模板」检查会降级为 WARN（不阻断 Pages 部署），
    # 但内容级同步检查（SITE-SYNC / SITE-CONTENT）仍然生效。
}

# 每章必须出现在站点页面中的**规范常量**（数值 / 固定短语）。
# 双向校验：既要在该章规范中出现（防止清单过期），也要在站点页面中出现（防止漂移）。
SITE_NUM_TOKENS: dict[str, list[str]] = {
    "06": ["16 字节", "1 MiB", "0x574E414C", "4C 41 4E 57", "64"],
    "07": ["28 字节", "0x574E414C", "4C 41 4E 57"],
    "08": ["1200", "1220", "64800", "0x04C11DB7", "0xCBF43926"],
    "09": ["64", "2³² − 1", "4 TiB"],
    "11": ["8192", "16384", "50 ms", "1000 ms", "K_nofrag", "K_cap"],
    "12": ["50 ms", "1000 ms", "2⁻³²"],
    "13": ["20 字节", "42 字节"],
    "18": ["4096"],
    "19": ["终止类", "过程类"],
}

# 规范用语 —— 出现在含这些词的行上的标识符，才算该章的「实质内容」
NORM_WORDS = ("必须", "不得", "应当")


def site_page_text(path: str) -> str:
    """站点 HTML → 纯文本（去掉标签、脚本与样式），用于内容比对。"""
    raw = read(path)
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", raw)


def is_substantive(text: str, token: str) -> bool:
    """token 在该章是否属实质内容：出现在规范性行中，或全章出现 >= 2 次。

    只出现一次的跨章引用（如「见 06 章」）不算实质内容 ——
    否则站点页面会被要求复述它并未承载的内容。
    """
    hits = 0
    pat = re.compile(rf"\b{re.escape(token)}\b")
    for line in text.split("\n"):
        if pat.search(line):
            hits += 1
            if any(w in line for w in NORM_WORDS):
                return True
    return hits >= 2


def check_site_content(spec: dict[str, str], res: Result) -> None:
    """站点页面与规范源文的**内容级**同步。

    仅比对常量字符串是不够的：站点页面是规范的可视化改写，
    规范新增一整节机制（如主动投递、共享清单、摘要对帐）而站点页面未跟进时，
    常量抽查依然会全部通过。本检查改为按章比对「协议实体」：

      1. 每章都要有对应的站点页面（豁免须显式登记）；
      2. 该章规范中**实质**出现的控制面消息名，站点页面必须覆盖；
      3. 该章规范中**实质**出现的错误码，站点页面必须覆盖；
      4. 每章的规范常量清单（见 SITE_NUM_TOKENS）双向校验。
    """
    # 1) 页面齐备
    missing_pages: list[str] = []
    for chap in sorted(spec):
        if chap in SITE_PAGE_EXEMPT:
            continue
        if not any(f.startswith(chap + "-") and f.endswith(".html")
                   for f in os.listdir(SITE)):
            missing_pages.append(f"{chap} 章缺少站点页面")
    if missing_pages:
        res.fail("SITE-CONTENT", "站点页面齐备", missing_pages)
    else:
        res.ok("SITE-CONTENT", "站点页面齐备"
               + (f"（豁免：{', '.join(sorted(SITE_PAGE_EXEMPT))}）" if SITE_PAGE_EXEMPT else ""))

    # 2) / 3) 消息名与错误码覆盖
    msgs = sorted({m[1] for m in re.findall(
        r"\|\s*`(0x[0-9A-F]{2})`\s*\|\s*([a-z_]+)\s*\|", spec.get("06", ""))})
    codes = sorted(set(re.findall(r"^- `([A-Z][A-Z0-9_]+)`", spec.get("19", ""), re.M)))

    miss_msg: list[str] = []
    miss_code: list[str] = []
    for chap, text in sorted(spec.items()):
        # 26 章是修订记录 / 待定议题，其中的历史标识符不构成协议引用
        if chap == "26" or chap in SITE_PAGE_EXEMPT:
            continue
        page = next((f for f in os.listdir(SITE)
                     if f.startswith(chap + "-") and f.endswith(".html")), None)
        if not page:
            continue
        st = site_page_text(os.path.join(SITE, page))
        for m in msgs:
            if m not in st and is_substantive(text, m):
                miss_msg.append(f"{chap} 章规范涉及 `{m}`，站点页面 {page} 未覆盖")
        for c in codes:
            if c not in st and is_substantive(text, c):
                miss_code.append(f"{chap} 章规范涉及 `{c}`，站点页面 {page} 未覆盖")

    if miss_msg:
        res.fail("SITE-CONTENT", "站点页面覆盖该章的消息", miss_msg)
    else:
        res.ok("SITE-CONTENT", "站点页面覆盖该章的消息")

    if miss_code:
        res.fail("SITE-CONTENT", "站点页面覆盖该章的错误码", miss_code)
    else:
        res.ok("SITE-CONTENT", "站点页面覆盖该章的错误码")

    # 4) 规范常量清单：双向校验
    stale: list[str] = []
    drifted: list[str] = []
    for chap, tokens in sorted(SITE_NUM_TOKENS.items()):
        text = spec.get(chap, "")
        page = next((f for f in os.listdir(SITE)
                     if f.startswith(chap + "-") and f.endswith(".html")), None)
        if not page:
            continue
        st = site_page_text(os.path.join(SITE, page))
        for tok in tokens:
            # 比对时忽略空白差异：规范写「50ms」、站点写「50 ms」视为同一常量
            needle = re.sub(r"\s+", "", tok)
            if needle not in re.sub(r"\s+", "", text):
                stale.append(f"{chap} 章常量清单中的 {tok!r} 已不在规范中（清单需更新）")
            if needle not in re.sub(r"\s+", "", st):
                drifted.append(f"{chap} 章常量 {tok!r} 未出现在站点页面 {page}")
    if stale:
        res.fail("SITE-CONTENT", "规范常量清单未过期", stale)
    else:
        res.ok("SITE-CONTENT", "规范常量清单未过期")

    if drifted:
        res.fail("SITE-CONTENT", "站点页面保留规范常量", drifted)
    else:
        res.ok("SITE-CONTENT", "站点页面保留规范常量")

    # 5) 26 章的修订记录必须镜像到站点页面 —— 修订历史也要跟着站点走
    spec26 = spec.get("26", "")
    site26 = next((f for f in os.listdir(SITE)
                   if f.startswith("26-") and f.endswith(".html")), None)
    missing_log: list[str] = []
    if site26:
        tbl = spec26.split("## 修订记录", 1)[-1]
        # 「已从正文移除的历史条目」是存档表，不属于修订记录
        tbl = tbl.split("### 已从正文移除的历史条目", 1)[0]
        st26 = site_page_text(os.path.join(SITE, site26))
        for line in tbl.split("\n"):
            if not line.startswith("|") or line.startswith("|---") or "日期" in line:
                continue
            idents = re.findall(r"`([^`]+)`", line)
            dates = re.findall(r"\d{4}-\d{2}-\d{2}", line)
            for tok in (idents[:2] or dates[:1]):
                if tok and tok not in st26:
                    missing_log.append(
                        f"26 章修订记录条目「{tok}」未镜像到站点页面 {site26}")
    if missing_log:
        res.fail("SITE-CONTENT", "站点页面镜像 26 章修订记录", missing_log)
    else:
        res.ok("SITE-CONTENT", "站点页面镜像 26 章修订记录")


def check_site_layered(spec: dict[str, str], res: Result) -> None:
    """站点必须处于「分层渲染」状态 —— 这是站点不再落后于源文的**结构保证**。

    只要某章还在「手写镜像」，它就会随源文修订而漂移，且内容级校验只能事后发现。
    因此把分层渲染本身固化为检查：

      1. 每章都要有 `docs/site/_pages/NN.tpl` 模板（豁免须显式登记：
         SITE_RENDER_EXEMPT 里登记「待迁移」的章降级为 WARN，不阻断部署）；
      2. 模板必须包含 `{{RENDER:body}}` 或 `{{RENDER:section:...}}` ——
         正文必须来自源文渲染，而不是手抄；
      3. 渲染产物必须与源文同步（等价于 `render-site.py --check`；
         模板或源文改动后忘记重渲染即失败）；
      4. 渲染产物不得残留 markdown 标记（`**` / 裸 `|` 表格）。
    """
    pages_dir = os.path.join(SITE, "_pages")
    renderer = os.path.join(ROOT, "scripts", "render-site.py")

    # 0) 渲染器必须存在
    if not os.path.exists(renderer):
        res.fail("RENDER", "站点渲染器存在",
                 ["缺少 scripts/render-site.py —— 站点未处于分层渲染模式"])
        return

    # 1) / 2) 模板齐备且正文由源文渲染
    no_tpl: list[str] = []
    no_render: list[str] = []
    pending: list[str] = []
    for chap in sorted(spec):
        if chap in SITE_PAGE_EXEMPT:
            continue
        tpl = os.path.join(pages_dir, f"{chap}.tpl")
        if not os.path.exists(tpl):
            if chap in SITE_RENDER_EXEMPT:
                # 已登记待迁移：降级为 WARN，不阻断部署（内容级校验仍然生效）
                pending.append(f"{chap} 章：{SITE_RENDER_EXEMPT[chap]}")
                continue
            no_tpl.append(f"{chap} 章缺少 _pages/{chap}.tpl（仍为手写镜像）")
            continue
        body = read(tpl)
        if "{{RENDER:body}}" not in body and "{{RENDER:section:" not in body:
            no_render.append(f"{chap}.tpl 未使用 {{{{RENDER:...}}}}，正文仍是手抄")
    if no_tpl:
        res.fail("RENDER", "每章都有渲染模板", no_tpl)
    else:
        res.ok("RENDER", "每章都有渲染模板")
    if no_render:
        res.fail("RENDER", "正文由源文渲染", no_render)
    else:
        res.ok("RENDER", "正文由源文渲染")
    if pending:
        res.warn("RENDER", "待迁移到分层渲染的章节（已登记）", pending)

    # 3) 产物与源文同步
    import subprocess
    proc = subprocess.run([sys.executable, renderer, "--check"],
                          capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        detail = [l.strip() for l in
                  (proc.stdout + proc.stderr).split("\n")
                  if l.strip() and not l.startswith("[render-site]")]
        res.fail("RENDER", "渲染产物与源文同步",
                 detail or ["render-site.py --check 失败"])
    else:
        res.ok("RENDER", "渲染产物与源文同步")

    # 4) 产物无 markdown 残留
    residue: list[str] = []
    for fname in sorted(os.listdir(SITE)):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(SITE, fname)
        raw = read(path)
        # 只检查「正文文本」：代码块、脚本与样式里的 ** 是合法内容
        # （源文的围栏代码块本就保留字面量；页面脚本可能把 ** 当作自身的标记语法）。
        raw = re.sub(r"(?is)<(script|style|pre|code)\b.*?</\1>", " ", raw)
        raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
        plain = re.sub(r"<[^>]+>", "", raw)
        if "**" in plain:
            residue.append(f"{fname} 残留 markdown 粗体标记 **（行内标记未转 HTML）")
    if residue:
        res.fail("RENDER", "渲染产物无 markdown 残留", residue)
    else:
        res.ok("RENDER", "渲染产物无 markdown 残留")


def check_links(spec: dict[str, str], res: Result) -> None:
    """README 与规范正文中的本地链接必须可达。"""
    bad: list[str] = []
    for base, rel in ((ROOT, "README.md"), (SPEC, "06-control-plane-tcp.md")):
        text = read(os.path.join(base, rel))
        for m in re.finditer(r"\]\((?!https?://|#)([^)]+)\)", text):
            target = m.group(1).split("#")[0]
            if not target:
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, target))):
                bad.append(f"{rel}: {target}")
    if bad:
        res.fail("LINKS", "本地链接可达", bad)
    else:
        res.ok("LINKS", "本地链接可达")


# ---------------------------------------------------------------- 字段表校验

TYPE_WIDTH = {"u8": 1, "u16": 2, "u32": 4, "u64": 8,
              "enum8": 1, "bool": 1, "hash32": 32}


def _parse_offset(cell: str) -> tuple[int | None, bool]:
    """解析偏移单元格 → (起始偏移, 是否定长)。

    支持 '0-3' / '12' / '16..' / '16+N'。
    """
    c = cell.strip().replace("`", "")
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", c)
    if m:
        return int(m.group(1)), True
    m = re.match(r"^(\d+)\s*\.\.", c)
    if m:
        return int(m.group(1)), False
    m = re.match(r"^(\d+)\s*\+\s*N$", c)
    if m:
        return int(m.group(1)), False
    m = re.match(r"^(\d+)$", c)
    if m:
        return int(m.group(1)), True
    return None, False


def _field_tables(lines: list[str]) -> list[tuple[int, list[list[str]], int, int]]:
    """找出所有「字段布局表」，返回 (起始行号, 行, 偏移列, 大小列)。"""
    out = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            head = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            if "偏移" in head and "大小" in head:
                oi = head.index("偏移")
                si = head.index("大小")
                j = i + 2
                rows = []
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                    if len(cells) == len(head):
                        rows.append(cells)
                    j += 1
                out.append((i + 1, rows, oi, si))
                i = j
                continue
        i += 1
    return out


def check_field_tables(spec: dict[str, str], res: Result) -> None:
    """消息体 / 帧头的字段表：偏移连续、字段总长与声明一致、类型宽度与大小一致。"""
    problems: list[str] = []
    width_checked = 0

    for chap in ("06", "07", "08"):
        text = spec.get(chap, "")
        if not text:
            continue
        lines = text.split("\n")
        tables = _field_tables(lines)

        # 章节声明的头部长度（07/08 的帧头 / 包头）
        declared_header = None
        m = re.search(r"(?:FRAME_)?HEADER_SIZE\s*=[^\n]*?=\s*(\d+)\s*字节", text)
        if m:
            declared_header = int(m.group(1))

        for ln, rows, oi, si in tables:
            name = rows[0][2] if (rows and len(rows[0]) > 2) else "?"
            # 1) 偏移连续 + 范围与大小自洽
            cursor = 0
            fixed_total = 0
            has_variable = False
            for cells in rows:
                off, fixed = _parse_offset(cells[oi])
                size_txt = cells[si].strip().replace("`", "")
                size_num = int(size_txt) if size_txt.isdigit() else None
                if off is None:
                    problems.append(f"{chap} 章 line {ln}: 偏移 {cells[oi]!r} 无法解析")
                    continue
                if off != cursor:
                    problems.append(
                        f"{chap} 章 line {ln}: 字段 {cells[2]} 偏移 {off} != 期望 {cursor}")
                if fixed and size_num is not None:
                    # 'a-b' 形式：大小必须等于区间长度
                    m2 = re.match(r"^(\d+)\s*-\s*(\d+)$", cells[oi].strip().replace("`", ""))
                    if m2 and int(m2.group(2)) - int(m2.group(1)) + 1 != size_num:
                        problems.append(
                            f"{chap} 章 line {ln}: 字段 {cells[2]} 偏移区间 "
                            f"{cells[oi]} 与大小 {size_num} 不符")
                    fixed_total += size_num
                    cursor = off + size_num
                else:
                    has_variable = True
                    cursor = off

            # 2) 字段总长 vs 声明
            if not has_variable:
                # 06 章的消息体表：向上找尺寸声明
                ctx = lines[max(0, ln - 16):ln - 1]
                decl = None
                for k in range(len(ctx) - 1, -1, -1):
                    mm = re.search(r"(\d+) 字节定长", ctx[k]) or \
                        re.search(r"定长区（(\d+) 字节）", ctx[k])
                    if mm:
                        decl = int(mm.group(1))
                        break
                if decl is None and declared_header is not None:
                    decl = declared_header
                if decl is not None and fixed_total != decl:
                    problems.append(
                        f"{chap} 章 line {ln}（{name}…）: 字段总长 {fixed_total} != 声明 {decl}")
            elif declared_header is not None and fixed_total != declared_header:
                problems.append(
                    f"{chap} 章 line {ln}: 定长部分合计 {fixed_total} != 声明头长 {declared_header}")

            # 3) 类型宽度与大小一致
            for cells in rows:
                if len(cells) < 4:
                    continue
                typ = cells[3].strip().replace("`", "")
                size_txt = cells[si].strip().replace("`", "")
                if typ in TYPE_WIDTH and size_txt.isdigit():
                    width_checked += 1
                    if TYPE_WIDTH[typ] != int(size_txt):
                        problems.append(
                            f"{chap} 章 line {ln}: 字段 {cells[2]} 类型 {typ} 应为 "
                            f"{TYPE_WIDTH[typ]} 字节，表里写 {size_txt}")

    if problems:
        res.fail("LAYOUT", "字段表：偏移连续 / 长度自洽 / 类型宽度一致", problems)
    else:
        res.ok("LAYOUT", f"字段表：偏移连续 / 长度自洽 / 类型宽度一致"
                        f"（已校验 {width_checked} 个定宽字段）")

# ---------------------------------------------------------------- 状态机校验

STATE_ENUM_RE = re.compile(r"`(\d)`\s*([A-Z][A-Z_]+)")


def _tables_of(lines: list[str], header_contains: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """找出表头包含指定关键字的所有表格，返回 (表头, 数据行)。"""
    out = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            head = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            if all(any(h in c for c in head) for h in header_contains):
                j = i + 2
                rows = []
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                    if len(cells) == len(head):
                        rows.append(cells)
                    j += 1
                out.append((head, rows))
                i = j
                continue
        i += 1
    return out


def check_state_machine(spec: dict[str, str], res: Result) -> None:
    """10 章状态机与 06 章枚举 / 消息发布方的覆盖度校验。"""
    ten = spec.get("10", "")
    six = spec.get("06", "")
    problems: list[str] = []
    warnings: list[str] = []

    if not ten or not six:
        res.fail("STATE", "状态机章节存在", ["10 或 06 章缺失"])
        return

    # --- 1) 状态集合：10 章定义表 vs 10 章编码说明 vs 06 章枚举 ---
    state_tables = _tables_of(ten.split("\n"), ["状态", "说明"])
    states10: list[str] = []
    for head, rows in state_tables:
        if head[0] == "状态":
            states10 = [r[0].strip("`") for r in rows]
            break
    if not states10:
        res.fail("STATE", "状态集合可解析", ["10 章未找到状态定义表"])
        return

    m = re.search(r"\*\*状态的编码表示\*\*.*?取值(.+?)（见 06 章", ten, re.S)
    enum10 = dict((b, int(a)) for a, b in STATE_ENUM_RE.findall(m.group(1))) if m else {}
    m2 = re.search(r"\| `state` \|([^|]+)\|", six)
    enum06 = dict((b, int(a)) for a, b in STATE_ENUM_RE.findall(m2.group(1))) if m2 else {}

    if set(enum10) != set(states10):
        problems.append(f"10 章编码表示的状态 {sorted(enum10)} != 状态定义表 {sorted(states10)}")
    if set(enum06) != set(states10):
        problems.append(f"06 章 state 枚举 {sorted(enum06)} != 10 章状态定义 {sorted(states10)}")
    if enum10 and enum06 and enum10 != enum06:
        problems.append(f"10 章与 06 章的状态编号不一致：{enum10} vs {enum06}")
    if enum10 and sorted(enum10.values()) != list(range(len(enum10))):
        problems.append(f"状态编号不是从 0 连续递增：{enum10}")
    if not problems:
        res.ok("STATE", f"状态集合三处一致（{len(states10)} 个状态，编号 0–{len(states10) - 1}）")

    # --- 2) 视角状态集 ---
    vm = re.search(r"\*\*接收侧\*\*使用全部状态（([^）]+)）", ten)
    sm = re.search(r"\*\*发送侧\*\*只使用 ([^—]+?) ——", ten)
    recv_states = set(re.findall(r"[A-Z][A-Z_]+", vm.group(1))) if vm else set()
    send_states = set(re.findall(r"[A-Z][A-Z_]+", sm.group(1))) if sm else set()
    if not recv_states or not send_states:
        warnings.append("未能从 10 章「视角定义」解析出视角状态集")
    else:
        if not recv_states.issubset(set(states10)):
            problems.append(f"接收侧状态集含未知状态 {sorted(recv_states - set(states10))}")
        if not send_states.issubset(set(states10)):
            problems.append(f"发送侧状态集含未知状态 {sorted(send_states - set(states10))}")
        if not send_states.issubset(recv_states):
            problems.append(f"发送侧状态集 {sorted(send_states)} 不是接收侧状态集的子集，"
                            f"与 10 章「接收侧使用全部状态」矛盾")

    # --- 3) 合法转移表 ---
    trans_tables = _tables_of(ten.split("\n"), ["从状态", "到状态", "视角"])
    trans: list[tuple[str, str, str, str]] = []
    for head, rows in trans_tables:
        for r in rows:
            if len(r) >= 4:
                trans.append((r[0].strip("`"), r[1].strip("`"), r[2], r[3]))
    if not trans:
        problems.append("10 章未找到合法状态转移表")
    else:
        # 3a) 状态必须在定义集合内
        for f, t, view, trig in trans:
            if f not in states10:
                problems.append(f"转移表出现未知状态 {f}")
            if t not in states10:
                problems.append(f"转移表出现未知状态 {t}")
            # 3b) 视角与状态集一致
            if view == "发送侧" and f in states10 and f not in send_states:
                problems.append(f"转移 {f}→{t} 标为「发送侧」，但发送侧不使用状态 {f}")
            if view == "接收侧" and f in states10 and f not in recv_states:
                problems.append(f"转移 {f}→{t} 标为「接收侧」，但接收侧不使用状态 {f}")
            if view == "发送侧" and t in states10 and t not in send_states:
                problems.append(f"转移 {f}→{t} 标为「发送侧」，但目标状态 {t} 不属于发送侧")
            if view == "接收侧" and t in states10 and t not in recv_states:
                problems.append(f"转移 {f}→{t} 标为「接收侧」，但目标状态 {t} 不属于接收侧")

        # 3c) ABORTED 是终态：不得有出边
        for f, t, view, trig in trans:
            if f == "ABORTED":
                problems.append(f"ABORTED 存在出边 {f}→{t}（10 章声明其为终态）")

        # 3d) 每个视角的每个**非终态**都至少有一条出边
        #     终态（COMPLETED / ABORTED）按 10 章声明没有出边
        terminals = {"COMPLETED", "ABORTED"}
        for view, allowed in (("发送侧", send_states), ("接收侧", recv_states)):
            for st in sorted(allowed - terminals):
                outs = [x for x in trans if x[0] == st and x[2] in (view, "双方")]
                if not outs:
                    problems.append(f"{view}视角下状态 {st} 没有任何合法出边"
                                    f"（10 章声明「每个状态对每个视角都要有合法转移」）")

        # 3e) 全部状态从 INIT 可达
        adj: dict[str, set[str]] = {st: set() for st in states10}
        for f, t, view, trig in trans:
            adj.setdefault(f, set()).add(t)
        seen = {"INIT"}
        stack = ["INIT"]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        unreachable = sorted(set(states10) - seen)
        if unreachable:
            problems.append(f"从 INIT 不可达的状态：{unreachable}")

        # 3f) 触发列的消息名必须存在于 06 章消息表
        msg_tables = _tables_of(six.split("\n"), ["编号", "消息", "方向"])
        msg_names: set[str] = set()
        direction: dict[str, str] = {}
        for head, rows in msg_tables:
            for r in rows:
                if len(r) >= 3 and r[0].strip("`").startswith("0x"):
                    name = r[1].strip("`")
                    if name in ("—", "-", ""):
                        continue  # 保留编号行
                    msg_names.add(name)
                    direction[name] = r[2]
        # 触发列是散文，允许字段名与消息名的简称；其余疑似消息名须真实存在
        field_words = {"accept", "reason", "code", "result", "flags", "state",
                       "session_id", "file_hash", "file_exists", "mode", "seq",
                       "ts", "bool", "chunk_count", "chunk_size"}
        for f, t, view, trig in trans:
            for tok in re.findall(r"\b[a-z][a-z0-9_]{3,}\b", trig):
                if tok in field_words or tok in msg_names:
                    continue
                if any(tok in name for name in msg_names):
                    continue  # 简称（如 accept → upload_accept）
                warnings.append(f"转移 {f}→{t} 的触发列出现未知标识符 {tok!r}"
                                f"（06 章消息表中无此消息）")

    # --- 4) 消息发布方方向：06 章消息表 vs 正文「恒由 X 发布」 ---
    if msg_names:
        for name in sorted(msg_names):
            who = None
            # (a) 同句式：「`msg` 恒由 **Server** 发布」
            m4 = re.search(rf"`{re.escape(name)}`[^\n]{{0,80}}恒由\s*\*{{0,2}}(Server|Client)\*{{0,2}}",
                           six)
            if m4:
                who = m4.group(1)
            # (b) 消息节内：「**发布方恒为 Server**」
            if who is None:
                m3 = re.search(rf"^### {re.escape(name)}（`0x[0-9A-F]+`）$(.*?)(?=^### |\Z)",
                               six, re.S | re.M)
                if m3:
                    m5 = re.search(r"(?:发布方恒为|恒由|恒为)\s*\*{0,2}(Server|Client)\*{0,2}\s*发布",
                                   m3.group(1))
                    if m5:
                        who = m5.group(1)
            if who is None:
                continue
            d = direction.get(name, "")
            if d == "双向":
                problems.append(f"{name}：正文声明「恒由 {who} 发布」，但消息表方向为「双向」")
            elif "→" in d:
                src = d.split("→")[0].strip()
                if src != who:
                    problems.append(f"{name}：正文声明「恒由 {who} 发布」，"
                                    f"但消息表方向为「{d}」")

    # --- 5) 状态名孤儿：全规范中出现但不在状态集合内的大写词 ---
    known_non_state = (NON_ERROR_TOKENS | {"FRAME_HEADER_SIZE", "TCP_NODELAY"}
                       | set(re.findall(r"^- `([A-Z][A-Z0-9_]+)`", spec.get("19", ""), re.M)))
    for chap, text in spec.items():
        if chap in ("19", "26"):
            continue
        for tok in set(re.findall(r"`([A-Z][A-Z_]{3,})`", text)):
            if tok in known_non_state or tok in states10:
                continue
            warnings.append(f"{chap} 章出现疑似状态名 {tok!r}，但 10 章状态集合中无此状态")

    if problems:
        res.fail("STATE", "状态机覆盖度", problems)
    else:
        res.ok("STATE", f"状态机覆盖度（{len(trans)} 条转移、{len(msg_names)} 个消息）")

    if warnings:
        res.warn("STATE", "状态机覆盖度（需人工判读）", warnings)

# ---------------------------------------------------------------- 走查结论回归

def check_walkthrough_rules(spec: dict[str, str], res: Result) -> None:
    """端到端走查得出的语义结论，必须保持在规范里（防止被改回去）。"""
    thirteen = spec.get("13", "")
    ten = spec.get("10", "")
    nineteen = spec.get("19", "")
    problems: list[str] = []

    # 1) 13 章必须有「待恢复会话的判定」表，且 PAUSED 保持 PAUSED
    if "待恢复会话的判定" not in thirteen:
        problems.append("13 章缺少「待恢复会话的判定」表")
    else:
        # PAUSED 行（在判定表内）必须写明「保持 PAUSED」
        paused_rows = [ln for ln in thirteen.split("\n")
                       if "`PAUSED`" in ln and "**是**" in ln]
        if not paused_rows:
            problems.append("13 章判定表中未找到 PAUSED 行（待恢复 = 是）")
        elif not any("保持" in ln for ln in paused_rows):
            problems.append("13 章判定表的 PAUSED 行未写明「保持 PAUSED」"
                            "（断线不得解除显式暂停）")
        for st in ("INIT", "COMPLETED", "ABORTED"):
            if not re.search(rf"`{st}`[^\n]*\*\*否\*\*", thirteen):
                problems.append(f"13 章判定表中 {st} 未标记为「不恢复」")

    # 2) 恢复后的状态表述：断线重连语境下不得无条件写「双方回到 TRANSFERRING」
    for chap in ("13", "24"):
        for i, line in enumerate(spec.get(chap, "").split("\n"), 1):
            if "双方回到 TRANSFERRING" in line and "暂停" not in line:
                problems.append(f"{chap} 章第 {i} 行无条件写「双方回到 TRANSFERRING」；"
                                f"恢复后应按「各视角各自回到断线前状态」表述")
    for f in os.listdir(SITE):
        # 26 章是修订记录/变更摘要，其中的历史表述不属于现行规范
        if not f.endswith(".html") or f.startswith("26-"):
            continue
        for i, line in enumerate(read(os.path.join(SITE, f)).split("\n"), 1):
            if "双方回到 TRANSFERRING" in line and "暂停" not in line:
                problems.append(f"site/{f} 第 {i} 行无条件写「双方回到 TRANSFERRING」")

    # 3) 10 章秒传必须限定方向
    if "仅适用于上传方向" not in ten:
        problems.append("10 章秒传小节未声明「仅适用于上传方向」")

    # 4) 19 章终止类 / 过程类必须两分且覆盖全部已定义错误码
    m = re.search(r"\*\*终止类错误码清单（规范性）\*\*：(.+?)。\n", nineteen, re.S)
    m2 = re.search(r"\*\*其余错误码一律为过程类\*\*(.+?)。\n", nineteen, re.S)
    defined = set(re.findall(r"^- `([A-Z][A-Z0-9_]+)`", nineteen, re.M))
    if not m or not m2:
        problems.append("19 章缺少「终止类 / 过程类」分类清单")
    else:
        term = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", m.group(1)))
        proc = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", m2.group(1)))
        if term & proc:
            problems.append(f"19 章终止类与过程类重叠：{sorted(term & proc)}")
        if term | proc != defined:
            missing = sorted(defined - (term | proc))
            extra = sorted((term | proc) - defined)
            if missing:
                problems.append(f"19 章未分类的错误码：{missing}")
            if extra:
                problems.append(f"19 章分类中不存在的错误码：{extra}")

    if problems:
        res.fail("WALKTHROUGH", "端到端走查结论保持有效", problems)
    else:
        res.ok("WALKTHROUGH", "端到端走查结论保持有效"
                            "（恢复判定 / 暂停不被解除 / 秒传方向 / 错误码两分）")

def check_session_cap(spec: dict[str, str], res: Result) -> None:
    """单连接并发会话数上限必须全章一致，且快照体积始终可编码。"""
    bad: list[str] = []
    cap = None
    for chap in ("06", "09", "13"):
        for m in re.finditer(r"max_sessions_per_connection`?[^\n]{0,24}?(\d+)", spec.get(chap, "")):
            v = int(m.group(1))
            if cap is None:
                cap = v
            elif v != cap:
                bad.append(f"{chap} 章的 max_sessions_per_connection = {v}，与 {cap} 不一致")
    if cap is None:
        bad.append("未在任何章节找到 max_sessions_per_connection 的定义")
    elif cap != 64:
        bad.append(f"max_sessions_per_connection = {cap}，期望 64")

    # 快照体积必须小于 max_frame_len
    if cap:
        snapshot_bytes = cap * 42
        if snapshot_bytes >= 1024 * 1024:
            bad.append(f"{cap} 条快照（{snapshot_bytes} 字节）超过 max_frame_len 1 MiB")
        resume_bytes = cap * 20
        if resume_bytes >= 1024 * 1024:
            bad.append(f"{cap} 条 resume（{resume_bytes} 字节）超过 max_frame_len 1 MiB")
        # u16 的值域本身超出帧长 —— 必须由规范上界把有效范围压到帧长之内。
        # 因此要求 06/13 章显式把两个计数器绑定到该上界。
        if 65535 * 42 >= 1024 * 1024:
            if not re.search(r"sessions_count[^\n]*max_sessions_per_connection",
                             spec.get("06", "")):
                bad.append("06 章的 sessions_count 未绑定 max_sessions_per_connection，"
                           "其 u16 值域将超出 max_frame_len")
            if not (re.search(r"resume_count[^\n]*max_sessions_per_connection",
                              spec.get("06", ""))
                    or re.search(r"resume_count[^\n]*max_sessions_per_connection",
                                 spec.get("13", ""))):
                bad.append("resume_count 未绑定 max_sessions_per_connection，"
                           "其 u16 值域将超出 max_frame_len")

    if "TOO_MANY_SESSIONS" not in spec.get("19", ""):
        bad.append("19 章缺少 TOO_MANY_SESSIONS（并发会话数超限的终止原因）")
    if "TOO_MANY_SESSIONS" not in spec.get("09", ""):
        bad.append("09 章未引用 TOO_MANY_SESSIONS（超限时的拒绝方式）")

    if bad:
        res.fail("SESSION-CAP", "单连接并发会话数上限一致且快照可编码", bad)
    else:
        res.ok("SESSION-CAP", f"单连接并发会话数上限 = {cap}"
                             f"（快照 {cap * 42} B / 恢复列表 {cap * 20} B « 1 MiB）")

# ---------------------------------------------------------------- 主流程

def main() -> int:
    quiet = "--quiet" in sys.argv
    warn_as_error = "--warn-as-error" in sys.argv

    spec = load_spec()
    res = Result()

    check_frame_header(spec, res)
    check_record_sizes(spec, res)
    check_error_codes(spec, res)
    check_defaults(spec, res)
    check_cross_refs(spec, res)
    check_field_tables(spec, res)
    check_state_machine(spec, res)
    check_walkthrough_rules(spec, res)
    check_session_cap(spec, res)
    check_site_sync(spec, res)
    check_site_content(spec, res)
    check_site_layered(spec, res)
    check_links(spec, res)

    p, f, w = res.counts()
    for status, cid, name, details in res.checks:
        if quiet and status == "PASS":
            continue
        print(f"[{status}] {cid:<14} {name}")
        for d in details:
            print(f"         - {d}")

    print(f"\n合计：PASS {p} · FAIL {f} · WARN {w}")
    if f:
        print("结果：存在 FAIL —— 规范内部不一致，需修正。")
        return 1
    if w and warn_as_error:
        print("结果：存在 WARN（--warn-as-error）。")
        return 1
    print("结果：规范内部一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
