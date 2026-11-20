#!/usr/bin/env bash
#
# 构建 GitHub Pages 站点（静态站点 → _site/）
#
#   用法： scripts/build-site.sh [输出目录]
#          默认输出目录为仓库根下的 _site/
#
# 做三件事：
#   1. 把 docs/site/ 下的页面与 style.css 复制到输出目录（输出目录即站点根）
#   2. 把 docs/spec/*.md 复制到输出目录的 spec/ —— 让页面里的「规范源文」链接在站点内可用
#   3. 把站内链接 ../spec/ 改写为 spec/（源码里保持 ../spec/，便于在仓库内直接浏览）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/_site}"

echo "==> 输出目录: $OUT"

# 先渲染：由规范源文生成站点页面（正文自动渲染 + 可视化片段注入）
python3 "$ROOT/scripts/render-site.py"

rm -rf "$OUT"
mkdir -p "$OUT/spec"

echo "==> 复制页面"
cp "$ROOT"/docs/site/*.html "$OUT"/
cp "$ROOT"/docs/site/style.css "$OUT"/

echo "==> 复制规范源文到 spec/"
cp "$ROOT"/docs/spec/*.md "$OUT"/spec/

echo "==> 改写站内链接 (../spec/ → spec/)"
sed -i 's|\.\./spec/|spec/|g' "$OUT"/*.html

echo "==> 生成 404 兜底页（复用目录页）"
cp "$OUT"/index.html "$OUT"/404.html

echo "==> 关闭 Jekyll 处理"
: > "$OUT"/.nojekyll

echo "==> 完成："
ls -1 "$OUT" | sed 's/^/    /'
