<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>24 端到端时序（TCP + UDP） — LANWEFT</title>
<link rel="stylesheet" href="style.css">
<style>
  .seq-wrap{
    background:#fff;border:1px solid var(--line);border-radius:14px;
    padding:8px 10px 14px;overflow-x:auto;
    box-shadow:0 1px 2px rgba(16,24,40,.04),0 8px 24px rgba(16,24,40,.04);
  }
  .seq-wrap svg{display:block;width:100%;height:auto;min-width:880px}
  .toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 16px}
  .seg{display:inline-flex;background:#eceff4;border-radius:999px;padding:3px}
  .seg button{
    border:0;background:transparent;cursor:pointer;font:inherit;font-size:13.5px;
    color:var(--ink-2);padding:5px 16px;border-radius:999px;
  }
  .seg button.active{background:var(--ink);color:#fff}
  .toolbar label.chk{display:inline-flex;align-items:center;gap:6px;font-size:13.5px;color:var(--ink-2);cursor:pointer}
  .lane-title{font-weight:700;font-size:14px}
  .lane-sub{font-size:11.5px;fill:var(--ink-2)}
  .msg-t{font-size:12.5px;fill:var(--ink)}
  .msg-t.bold{font-weight:700}
  .note-t{font-size:12.5px;fill:#7a5a12}
  .chip-t{font-size:12px;fill:var(--ink-2)}
  .sep-t{font-size:12.5px;fill:var(--ink-2);font-weight:700;letter-spacing:.4px}
  .lifeline{stroke:var(--line-2);stroke-width:2;stroke-dasharray:5 6}
  .a-tcp{stroke:#4b5563;stroke-width:1.8;fill:none}
  .a-udp{stroke:#0d9488;stroke-width:1.8;stroke-dasharray:7 5;fill:none}
  .a-conn{stroke:#4338ca;stroke-width:2.2;fill:none}
  .arrow-tcp{fill:#4b5563}
  .arrow-udp{fill:#0d9488}
  .arrow-conn{fill:#4338ca}
  .bg-note{fill:#fffbeb;stroke:#f2e2b6}
  .bg-chip{fill:#f2f4f8;stroke:#e2e6ee}
  .hl{fill:#eef3ff;stroke:#cfdcfb}
  .phase-bg{fill:#fafbfc}
</style>
</head>
<body>
<div class="wrap">

  <nav class="topnav">
    <a href="index.html">目录</a>
    <a href="23-client-identity.html">◀ 23 客户端身份</a>
    <a href="25-normative-marking.html">25 标注规范 ▶</a>
    <a href="../spec/24-sequence-diagrams.md">规范源文</a>
  </nav>

  <h1>24 端到端时序（TCP + UDP）</h1>

  <!-- ============ 本章要点（导读文案，手写片段） ============ -->
  {{PART:summary}}

  <!-- ============ 主时序图：控制面 TCP + 数据面 UDP（搬自原页面） ============ -->
  {{PART:main}}

  <!-- ============ 补充时序：摘要对帐 / 复核轮 / 主动投递 / 共享清单 ============ -->
  {{PART:supplement}}

  <!-- ============ 导读性说明（搬自原页面） ============ -->
  {{PART:notes}}

  <!-- ============ 规范正文（源文自动渲染） ============ -->
  {{RENDER:body}}

  <footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/24-sequence-diagrams.md">docs/spec/24-sequence-diagrams.md</a></footer>
</div>
</body>
</html>
