#!/usr/bin/env bash
#
# 确保仓库的 GitHub Pages 源为「GitHub Actions」
#
#   用法：
#     GITHUB_TOKEN=<PAT 或 GITHUB_TOKEN> scripts/ensure-pages-source.sh [owner/repo]
#
# 背景：Pages 的 Source 一旦被改成「Deploy from a branch」，GitHub 会启用内置的
# Jekyll 构建（dynamic/pages/pages-build-deployment）来发布**仓库根目录**，
# 于是 .github/workflows/pages.yml 里的部署虽然显示 success，线上却始终是
# Jekyll 站点，spec 页面全部 404。本脚本把 Source 改回「GitHub Actions」。
#
# 需要的权限：
#   - 仓库管理员（Pages 站点配置属于 Administration 权限）
#   - 在 Actions 里可用 GITHUB_TOKEN 调用（此时权限来自工作流的 permissions 段）
#
set -uo pipefail

REPO="${1:-gx1727/LANWEFT}"
API="https://api.github.com/repos/${REPO}"
TOKEN="${GITHUB_TOKEN:-${MY_PAT:-}}"

if [ -z "$TOKEN" ]; then
  echo "缺少访问令牌。请这样调用："
  echo "  GITHUB_TOKEN=<你的 PAT> scripts/ensure-pages-source.sh ${REPO}"
  exit 1
fi

AUTH=(-H "Authorization: Bearer ${TOKEN}"
      -H "X-GitHub-Api-Version: 2022-11-18"
      -H "Accept: application/vnd.github+json"
      -H "Content-Type: application/json")

json_get() {  # json_get <file> <python表达式>
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print($2)" "$1" 2>/dev/null
}

show() { head -c 400 "$1" 2>/dev/null; echo; }

echo "==> 1/3 查询现有 Pages 站点"
code=$(curl -s -o /tmp/pages-site.json -w '%{http_code}' "${AUTH[@]}" "${API}/pages")
if [ "$code" != "200" ]; then
  echo "    查询失败（HTTP ${code}）："
  show /tmp/pages-site.json
  echo "==> 2/3 直接创建（build_type = workflow）"
  curl -s -X POST "${AUTH[@]}" "${API}/pages" \
       -d '{"build_type":"workflow"}' -o /tmp/pages-create.json -w "    POST HTTP %{http_code}\n"
  show /tmp/pages-create.json
  echo "==> 3/3 完成"
  exit 0
fi

BT=$(json_get /tmp/pages-site.json "d.get('build_type','')")
SRC=$(json_get /tmp/pages-site.json "(d.get('source') or {}).get('branch','') + ':' + (d.get('source') or {}).get('path','')")
URL=$(json_get /tmp/pages-site.json "d.get('html_url','')")
echo "    当前：build_type=${BT} source=${SRC:-<无>} url=${URL}"

if [ "$BT" = "workflow" ]; then
  echo "==> 已是「GitHub Actions」源，无需改动"
  exit 0
fi

echo "==> 2/3 尝试直接 PATCH 为 workflow"
code=$(curl -s -o /tmp/pages-patch.json -w '%{http_code}' -X PATCH "${AUTH[@]}" "${API}/pages" \
      -d '{"build_type":"workflow"}')
echo "    PATCH HTTP ${code}"
if [ "$code" != "200" ] && [ "$code" != "204" ]; then
  show /tmp/pages-patch.json
  echo "==> PATCH 不可用，改为重建站点（DELETE → POST build_type=workflow）"
  dcode=$(curl -s -o /tmp/pages-del.json -w '%{http_code}' -X DELETE "${AUTH[@]}" "${API}/pages")
  echo "    DELETE HTTP ${dcode}"
  for i in 1 2 3 4 5 6 7 8 9 10; do
    ccode=$(curl -s -o /tmp/pages-create.json -w '%{http_code}' -X POST "${AUTH[@]}" "${API}/pages" \
            -d '{"build_type":"workflow"}')
    echo "    POST HTTP ${ccode}"
    if [ "$ccode" = "201" ] || [ "$ccode" = "200" ]; then
      break
    fi
    show /tmp/pages-create.json
    sleep 6
  done
else
  show /tmp/pages-patch.json
fi

echo "==> 3/3 复核"
code=$(curl -s -o /tmp/pages-site2.json -w '%{http_code}' "${AUTH[@]}" "${API}/pages")
if [ "$code" = "200" ]; then
  BT2=$(json_get /tmp/pages-site2.json "d.get('build_type','')")
  URL2=$(json_get /tmp/pages-site2.json "d.get('html_url','')")
  echo "    现在：build_type=${BT2} url=${URL2}"
  [ "$BT2" = "workflow" ] || { echo "    仍未切换成功，请到 Settings → Pages 手动改 Source"; exit 1; }
else
  echo "    复核失败（HTTP ${code}）"
  exit 1
fi
