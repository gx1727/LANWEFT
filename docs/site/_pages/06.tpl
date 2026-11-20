<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>06 控制面（TCP） — LANWEFT</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="wrap">

  <nav class="topnav">
    <a href="index.html">目录</a>
    <a href="05-protocol-stack.html">◀ 05 协议栈</a>
    <a href="07-data-plane-udp.html">07 数据面 ▶</a>
    <a href="../spec/06-control-plane-tcp.md">规范源文</a>
  </nav>

  <h1>06 控制面（TCP）</h1>

  <!-- ============ 本章要点（导读文案，手写片段） ============ -->
  {{PART:summary}}

  <!-- ============ 控制帧帧头（位域图，偏移与大小由源文表格抽取） ============ -->
  {{PART:frame}}

  <!-- ============ 消息体布局示例（位域图） ============ -->
  {{PART:messages}}

  <!-- ============ 消息类型编号总表 ============ -->
  {{PART:msgtable}}

  <!-- ============ 本章引用的错误码 ============ -->
  {{PART:errors}}

  <!-- ============ 规范正文（源文自动渲染） ============ -->
  {{RENDER:body}}

  <footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/06-control-plane-tcp.md">docs/spec/06-control-plane-tcp.md</a></footer>
</div>
</body>
</html>
