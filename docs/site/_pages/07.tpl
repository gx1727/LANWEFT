<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>07 数据面（UDP / TCP Fallback） — LANWEFT</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="wrap">

  <nav class="topnav">
    <a href="index.html">目录</a>
    <a href="06-control-plane-tcp.html">◀ 06 控制面</a>
    <a href="08-packet-format.html">08 数据包格式 ▶</a>
    <a href="../spec/07-data-plane-udp.md">规范源文</a>
  </nav>

  <h1>07 数据面（UDP / TCP Fallback）</h1>

  <!-- ============ 本章要点（导读文案，手写片段） ============ -->
  {{PART:summary}}

  <!-- ============ UDP 数据包结构（位域图） ============ -->
  {{PART:udp-packet}}

  <!-- ============ 两条通道的对比 ============ -->
  {{PART:channel-compare}}

  <!-- ============ UDP 可用性探测（交互流程图） ============ -->
  {{PART:probe}}

  <!-- ============ TCP 数据面帧结构（位域图） ============ -->
  {{PART:tcp-frame}}

  <!-- ============ 规范正文（源文自动渲染） ============ -->
  {{RENDER:body}}

  <!-- ============ 本章与其它章的关系 ============ -->
  {{PART:notes}}

  <footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/07-data-plane-udp.md">docs/spec/07-data-plane-udp.md</a></footer>
</div>
</body>
</html>
