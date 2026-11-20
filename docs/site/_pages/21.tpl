<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>21 认证与访问控制（Authentication &amp; Authorization） — LANWEFT</title>
<link rel="stylesheet" href="style.css">
<style>
  .acl-layer{font-size:13px;font-weight:700}
  .acl-sub{font-size:12px;font-weight:400;color:var(--ink-2)}
</style>
</head>
<body>
<div class="wrap">

  <nav class="topnav">
    <a href="index.html">目录</a>
    <a href="20-security-model.html">◀ 20 安全模型</a>
    <a href="23-client-identity.html">23 客户端身份 ▶</a>
    <a href="../spec/21-acl-and-auth.md">规范源文</a>
  </nav>

  <h1>21 认证与访问控制（Authentication &amp; Authorization）</h1>

  <!-- ============ 本章要点（导读文案，手写片段） ============ -->
  {{PART:summary}}

  <!-- ============ 握手认证流程（搬自原页面） ============ -->
  {{PART:auth}}

  <!-- ============ 四层访问控制（按源文四层重绘） ============ -->
  {{PART:acl}}

  <!-- ============ 规范正文（源文自动渲染） ============ -->
  {{RENDER:body}}

  <!-- ============ 导读提示：常见陷阱（原页面导读，不与源文冲突） ============ -->
  {{PART:traps}}

  <footer>LANWEFT · 规范文档可视化 · 对应 <a href="../spec/21-acl-and-auth.md">docs/spec/21-acl-and-auth.md</a></footer>
</div>
</body>
</html>
