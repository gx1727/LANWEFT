<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>10 Session 状态机 — LANWEFT</title>
<link rel="stylesheet" href="style.css">
<style>
  .sm-svg{display:block;width:100%;height:auto}
  .sm-box{fill:#fff;stroke:#c7d2e0;stroke-width:1.6}
  .sm-box.rx{fill:#eefaf1;stroke:#9fd8b0}
  .sm-box.pa{fill:#fdf6e3;stroke:#e6cf92}
  .sm-box.ab{fill:#fdeeed;stroke:#efb0ad}
  .sm-name{font-family:var(--mono);font-size:13.5px;font-weight:700;fill:var(--ink)}
  .sm-sub{font-family:var(--sans);font-size:10.5px;fill:var(--ink-2)}
  .sm-edge{stroke:#5b6478;stroke-width:1.7;fill:none}
  .sm-edge.sp{stroke:#a855f7;stroke-width:1.6;stroke-dasharray:6 5;fill:none}
  .sm-edge.ab{stroke:#dc2626;stroke-width:1.6;stroke-dasharray:3 4;fill:none}
  .sm-lbl{font-family:var(--mono);font-size:11.5px;fill:var(--ink)}
  .sm-lbl.sp{fill:#7e22ce}
  .sm-lbl.ab{fill:#b91c1c}
  .sm-hd{fill:#334155}
</style>
</head>
<body>
<div class="wrap">

  <nav class="topnav">
    <a href="index.html">目录</a>
    <a href="09-session-model.html">◀ 09 会话模型</a>
    <a href="11-flow-control.html">11 流控 ▶</a>
    <a href="../spec/10-state-machine.md">规范源文</a>
  </nav>

  <h1>10 Session 状态机</h1>

  <!-- ============ 本章要点（导读文案，手写片段） ============ -->
  {{PART:summary}}

  <!-- ============ 状态机图（SVG，节点与转移边） ============ -->
  {{PART:states}}

  <!-- ============ 规范正文（源文自动渲染） ============ -->
  {{RENDER:body}}

  <!-- ============ 与其它章的关系 ============ -->
  {{PART:notes}}

  <footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/10-state-machine.md">docs/spec/10-state-machine.md</a></footer>
</div>
</body>
</html>
