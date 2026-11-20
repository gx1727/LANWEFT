<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>17 存储与内存模型 — LANWEFT</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="wrap">

  <nav class="topnav">
    <a href="index.html">目录</a>
    <a href="16-mobile-background-limits.html">◀ 16 移动端限制</a>
    <a href="18-bitmap-and-chunk-map.html">18 位图与块图 ▶</a>
    <a href="../spec/17-memory-and-disk-model.md">规范源文</a>
  </nav>

  <h1>17 存储与内存模型</h1>

  <!-- ============ 本章要点（导读文案，手写片段） ============ -->
  {{PART:summary}}

  <!-- ============ 乱序写盘：偏移映射（搬自原页面） ============ -->
  {{PART:offset}}

  <!-- ============ 写入顺序（由源文「写入语义」绘成） ============ -->
  {{PART:writeorder}}

  <!-- ============ 内存与文件大小解耦（搬自原页面） ============ -->
  {{PART:memory}}

  <!-- ============ 完成与提交流程（搬自原页面） ============ -->
  {{PART:commit}}

  <!-- ============ 规范正文（源文自动渲染） ============ -->
  {{RENDER:body}}

  <footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/17-memory-and-disk-model.md">docs/spec/17-memory-and-disk-model.md</a></footer>
</div>
</body>
</html>
