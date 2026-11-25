#!/usr/bin/env python3
"""数据面安全等级与 PROBE token 的最小逻辑验证（纯内存，无网络）。

覆盖：
  * lv1/lv2/lv3 协商：默认 lv1、Client 能力、Server min/default/max/suites
  * 低于 min 拒绝、lv3 套件不交集时降级到 lv2、C↔C 双方能力取交集
  * 配置变更只影响新会话（已建立会话等级不变）
  * PROBE token：lv1 直接使用根秘密；lv2/lv3 派生且不暴露根秘密
  * 错误 token / 错误源地址不绑定
  * 重连换 link_token：旧 token 失效、新 token 可重新绑定
  * lv1 CRC32 / lv2 keyed MAC / lv3 AEAD 的封装、长度保持、坏 tag 拒绝
  * K > 1（含 K = 54）时整数据报一个 tag
  * 快照 security 字节编解码、K_nofrag 随等级变化

注意：脚本用 HMAC-SHA256 / SHAKE256 作为 BLAKE3 keyed MAC / AEAD 的
**逻辑替身**；规范要求 BLAKE3 keyed 模式 / AES-256-GCM / ChaCha20-Poly1305。
这里验证的是协商、长度、绑定与失败路径，不是密码学实现本身。

运行：python3 scripts/verify-security.py
"""

import hashlib
import hmac
import os
import struct
import zlib

SYMBOL = 1200
S_FULL = 54
EP = ("10.0.0.1", 5001)
EP2 = ("10.0.0.1", 5002)

LEVELS = {1: "lv1", 2: "lv2", 3: "lv3"}
SUITES = {0: "none", 1: "aes-256-gcm", 2: "chacha20-poly1305"}


def cd(a, b):
    return (a + b - 1) // b


def kdf(root: bytes, label: bytes, n: int = 32) -> bytes:
    """规范要求 BLAKE3；此处用 HMAC-SHA256 做逻辑替身。"""
    return hmac.new(root, b"LANWEFT/" + label, hashlib.sha256).digest()[:n]


def probe_token(root: bytes, level: int) -> bytes:
    if level == 1:
        return root
    return kdf(root, b"probe", 16)


def traffic_key(root: bytes, session_id: int, direction: str) -> bytes:
    return kdf(root, b"data:" + struct.pack("<Q", session_id) + direction.encode(), 32)


def mac(key: bytes, data: bytes, n: int = 16) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()[:n]


def crc32(data: bytes) -> bytes:
    return struct.pack("<I", zlib.crc32(data) & 0xFFFFFFFF)


def nonce(generation: int, chunk_id: int, chunk_symbol: int, k: int) -> bytes:
    return struct.pack("<BIHH", generation, chunk_id, chunk_symbol, k)


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def keystream(key: bytes, nc: bytes, n: int) -> bytes:
    return hashlib.shake_256(key + nc).digest(n)


def header(session_id: int, chunk_id: int, chunk_symbol: int, flags: int = 0x0001) -> bytes:
    return struct.pack("<QIHH", session_id, chunk_id, chunk_symbol, flags)


def seal(level: int, key: bytes | None, hdr: bytes, payload: bytes, nc: bytes):
    """返回线上的 (payload_or_ciphertext, trailer)。"""
    if level == 1:
        return payload, crc32(hdr + payload)
    if level == 2:
        if key is None:
            raise ValueError("lv2 requires key")
        return payload, mac(key, hdr + payload)
    if level == 3:
        if key is None:
            raise ValueError("lv3 requires key")
        ct = xor_bytes(payload, keystream(key, nc, len(payload)))
        return ct, mac(key, hdr + ct)
    raise ValueError("bad level")


def open_packet(level: int, key: bytes | None, hdr: bytes, body: bytes, nc: bytes):
    """body = payload_or_ciphertext ‖ trailer。返回 (plaintext, error)。"""
    tsize = 4 if level == 1 else 16
    if len(body) < tsize:
        return None, "INVALID_PACKET"
    data, trailer = body[:-tsize], body[-tsize:]
    if level == 1:
        if crc32(hdr + data) != trailer:
            return None, "CRC32_INVALID"
        return data, None
    if key is None:
        return None, "AUTH_TAG_INVALID"
    if level == 2:
        if mac(key, hdr + data) != trailer:
            return None, "AUTH_TAG_INVALID"
        return data, None
    if level == 3:
        if mac(key, hdr + data) != trailer:
            return None, "AUTH_TAG_INVALID"
        return xor_bytes(data, keystream(key, nc, len(data))), None
    return None, "INVALID_PACKET"


def negotiate(client_max, client_mask, cfg, other=None):
    """返回 (level, suite, error)。other 为 C↔C 对端 (max, mask)。"""
    if other is not None:
        client_max = min(client_max, other[0])
        client_mask &= other[1]
    cap = min(client_max, cfg["max"])
    if cap < cfg["min"]:
        return None, None, "SECURITY_LEVEL_UNSUPPORTED"
    level = min(max(cfg["default"], cfg["min"]), cap)
    if level < 3:
        return level, 0, None
    available = [s for s in cfg["suites"] if client_mask & (1 << (s - 1))]
    if available:
        return 3, available[0], None
    if cfg["min"] <= 2:
        return 2, 0, None
    return None, None, "SECURITY_LEVEL_UNSUPPORTED"


def encode_security(level: int, suite: int) -> int:
    return (level & 0x3) | ((suite & 0x3) << 2)


def decode_security(v: int):
    return v & 0x3, (v >> 2) & 0x3


def knofrag(level: int, mtu: int, ipv6: bool = False) -> int:
    trailer = 4 if level == 1 else 16
    overhead = 16 + trailer + 8 + (40 if ipv6 else 20)
    lmax = 65507 - 16 - trailer
    return min(S_FULL, min(mtu - overhead, lmax) // SYMBOL)


class Endpoint:
    """接收方端点绑定：token 校验通过才记录 PROBE 源地址。"""

    def __init__(self, sid: int, level: int, root: bytes):
        self.sid = sid
        self.level = level
        self.root = root
        self.bound = None

    def probe(self, sid: int, token: bytes, src):
        if sid != self.sid or token != probe_token(self.root, self.level):
            return "PEER_TOKEN_INVALID"
        self.bound = src
        return True

    def recv(self, src):
        if src != self.bound:
            return "source"
        return "ok"


def main() -> int:
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        mark = "✅" if cond else "❌"
        print(f"{mark} {name}" + (f" — {detail}" if detail else ""))
        return bool(cond)

    base = {"min": 1, "default": 1, "max": 3, "suites": [1, 2]}

    # [1] 默认 lv1
    lv, suite, err = negotiate(3, 0b11, base)
    check("[1] Server 默认 lv1：即使 Client 支持 lv3 也选 lv1", (lv, suite, err) == (1, 0, None),
          f"level={lv} suite={suite}")

    # [2] default / min / max
    cfg = dict(base, default=2)
    check("[2] default=2 → lv2", negotiate(3, 0b11, cfg)[:2] == (2, 0))
    cfg = dict(base, default=3)
    check("[2] default=3 + AES 能力 → lv3/AES", negotiate(3, 0b01, cfg)[:2] == (3, 1))
    check("[2] default=3 + ChaCha 能力 → lv3/ChaCha", negotiate(3, 0b10, cfg)[:2] == (3, 2))
    check("[2] max=2 夹紧 default=3", negotiate(3, 0b11, dict(cfg, max=2))[:2] == (2, 0))

    # [3] 低于 min 拒绝
    cfg = dict(base, min=3, default=3, max=3)
    lv, _, err = negotiate(2, 0b11, cfg)
    check("[3] Client 最高 lv2 < Server min lv3 → 拒绝", lv is None and err == "SECURITY_LEVEL_UNSUPPORTED",
          err or "")

    # [4] lv3 套件不交集：可降 lv2，否则拒绝
    cfg = dict(base, default=3, suites=[1])
    lv, suite, err = negotiate(3, 0b10, cfg)  # Client 只支持 ChaCha，Server 只允许 AES
    check("[4] lv3 套件无交集且 min≤2 → 降级 lv2", (lv, suite, err) == (2, 0, None),
          f"level={lv} suite={suite}")
    cfg = dict(base, min=3, default=3, max=3, suites=[1])
    lv, _, err = negotiate(3, 0b10, cfg)
    check("[4] lv3 套件无交集且 min=3 → 拒绝", lv is None and err == "SECURITY_LEVEL_UNSUPPORTED")

    # [5] C↔C 双方能力取交集
    cfg = dict(base, default=3)
    check("[5] C↔C：一方最高 lv2 → 取 lv2",
          negotiate(3, 0b11, cfg, other=(2, 0b11))[:2] == (2, 0))
    check("[5] C↔C：双方都支持 AES → lv3/AES",
          negotiate(3, 0b01, cfg, other=(3, 0b01))[:2] == (3, 1))
    check("[5] C↔C：套件交集为空 → 降级 lv2",
          negotiate(3, 0b01, cfg, other=(3, 0b10))[:2] == (2, 0))

    # [6] 配置切换只影响新会话
    cfg = dict(base)
    old_level = negotiate(3, 0b11, cfg)[0]
    cfg["default"] = 3
    new_level = negotiate(3, 0b11, cfg)[0]
    check("[6] 配置切换只影响新会话：旧会话仍 lv1，新会话 lv3",
          old_level == 1 and new_level == 3, f"old={old_level} new={new_level}")

    # [7] PROBE token：lv1 直接、lv2/lv3 派生
    root = os.urandom(16)
    t1 = probe_token(root, 1)
    t2 = probe_token(root, 2)
    t3 = probe_token(root, 3)
    check("[7] lv1 PROBE token 直接使用根秘密", t1 == root and len(t1) == 16)
    check("[7] lv2/lv3 PROBE token = KDF(root,\"probe\",16) 且不暴露根秘密",
          t2 == t3 == kdf(root, b"probe", 16) and t2 != root and len(t2) == 16)

    # [8] 错误 token 不绑定；正确 token 绑定；错误源地址丢弃
    ep = Endpoint(7, 2, root)
    check("[8] 错误 token 不绑定、不回 ACK", ep.probe(7, b"\x00" * 16, EP) == "PEER_TOKEN_INVALID" and ep.bound is None)
    check("[8] 正确 token 绑定 PROBE 源地址", ep.probe(7, t2, EP) is True and ep.bound == EP)
    check("[8] 绑定后错误源地址的数据包被丢弃", ep.recv(EP2) == "source" and ep.recv(EP) == "ok")

    # [9] 重连换 link_token：旧 token 失效、新 token 可重绑定
    root2 = os.urandom(16)
    ep2 = Endpoint(9, 2, root2)
    check("[9] 旧连接 token 对新连接无效", ep2.probe(9, t2, EP) == "PEER_TOKEN_INVALID")
    check("[9] 新 link_token 派生 token 可重新绑定",
          ep2.probe(9, probe_token(root2, 2), EP2) is True and ep2.bound == EP2)

    # [10] lv1/lv2/lv3 封装与坏 tag 拒绝
    sid = 0x1234
    hdr = header(sid, 5, 0, 0x0001)
    payload = os.urandom(SYMBOL)
    key = traffic_key(root, sid, "c2s")
    nc = nonce(0, 5, 0, 1)
    for level in (1, 2, 3):
        wire_payload, trailer = seal(level, None if level == 1 else key, hdr, payload, nc)
        tsize = 4 if level == 1 else 16
        check(f"[10] {LEVELS[level]} trailer = {tsize}B", len(trailer) == tsize)
        if level == 3:
            check("[10] lv3 密文长度 = 明文长度", len(wire_payload) == len(payload))
        plain, err = open_packet(level, None if level == 1 else key, hdr, wire_payload + trailer, nc)
        check(f"[10] {LEVELS[level]} 正常解包", plain == payload and err is None)
        bad = bytearray(wire_payload + trailer)
        bad[-1] ^= 0x01
        _, err = open_packet(level, None if level == 1 else key, hdr, bytes(bad), nc)
        want = "CRC32_INVALID" if level == 1 else "AUTH_TAG_INVALID"
        check(f"[10] {LEVELS[level]} 坏 tag → {want}", err == want, err or "")
        bad_hdr = bytearray(hdr)
        bad_hdr[-1] ^= 0x01
        _, err = open_packet(level, None if level == 1 else key, bytes(bad_hdr), wire_payload + trailer, nc)
        check(f"[10] {LEVELS[level]} 头部被篡改 → 拒绝", err == want, err or "")

    # [11] 错误密钥拒绝
    wrong_key = traffic_key(os.urandom(16), sid, "c2s")
    for level in (2, 3):
        wp, tr = seal(level, key, hdr, payload, nc)
        _, err = open_packet(level, wrong_key, hdr, wp + tr, nc)
        check(f"[11] {LEVELS[level]} 错误 traffic_key → AUTH_TAG_INVALID", err == "AUTH_TAG_INVALID")

    # [12] K > 1：整数据报一个 tag（含 K=54 / 64800B）
    for k in (2, S_FULL):
        data = os.urandom(k * SYMBOL)
        hdrk = header(sid, 3, 0)
        nck = nonce(0, 3, 0, k)
        for level in (2, 3):
            wp, tr = seal(level, key, hdrk, data, nck)
            check(f"[12] K={k} {LEVELS[level]}：只有一个 {len(tr)}B tag", len(tr) == 16)
            plain, err = open_packet(level, key, hdrk, wp + tr, nck)
            check(f"[12] K={k} {LEVELS[level]}：K 个 symbol 整体还原", plain == data and err is None)

    check("[13] nonce 随 K 变化，避免同起点不同长度复用",
          nonce(0, 3, 0, 1) != nonce(0, 3, 0, S_FULL))

    # [14] 快照 security 字节
    check("[14] security 字节编解码 lv1 / lv3+AES / lv3+ChaCha",
          decode_security(encode_security(1, 0)) == (1, 0)
          and decode_security(encode_security(3, 1)) == (3, 1)
          and decode_security(encode_security(3, 2)) == (3, 2))

    # [15] K_nofrag 随等级变化
    check("[15] K_nofrag：1500 lv1/lv2·lv3 = 1/1",
          knofrag(1, 1500) == 1 and knofrag(3, 1500) == 1)
    check("[15] K_nofrag：9000 lv1/lv2·lv3 = 7/7",
          knofrag(1, 9000) == 7 and knofrag(3, 9000) == 7)
    check("[15] K_nofrag：65536 lv3 = 54（受 S 约束）", knofrag(3, 65536) == S_FULL)
    check("[15] K_nofrag：1500 IPv6 lv3 = 1（overhead 80）", knofrag(3, 1500, ipv6=True) == 1)

    failed = [c for c in checks if not c[1]]
    print("\n" + "=" * 60)
    print(f"PASS {len(checks) - len(failed)} / FAIL {len(failed)}")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
        return 1
    print("结果：安全协商、PROBE token 绑定与 lv1/lv2/lv3 包级校验逻辑一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
