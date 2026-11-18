#!/usr/bin/env bash
#
# 启用 GitHub Pages（Source = GitHub Actions）并触发一次部署
#
#   用法：
#     GITHUB_TOKEN=<PAT> scripts/enable-pages.sh [owner/repo]
#
# PAT 需具备仓库管理员权限（创建 Pages 站点）：
#   - 经典 PAT：勾选 `repo` scope
#   - 细粒度 PAT：Repository permissions → Administration: Write
#
# 说明：GITHUB_TOKEN 环境变量名沿用 GitHub 惯例；若你更喜欢用别的变量名，
#      直接 export 后调用即可，例如：export MY_PAT=... ; MY_PAT=... scripts/enable-pages.sh
#
set -euo pipefail

REPO="${1:-gx1727/LANWEFT}"
TOKEN="${GITHUB_TOKEN:-${MY_PAT:-}}"

if [ -z "$TOKEN" ]; then
  echo "缺少访问令牌。请这样调用："
  echo "  GITHUB_TOKEN=<你的 PAT> scripts/enable-pages.sh ${REPO}"
  echo
  echo "创建 PAT：https://github.com/settings/personal-access-tokens/new"
  echo "  · 细粒度：Repository permissions → Administration: Write（或 Pages: Write）"
  exit 1
fi

API="https://api.github.com/repos/${REPO}"
AUTH=(-H "Authorization: Bearer ${TOKEN}"
      -H "X-GitHub-Api-Version: 2022-11-28"
      -H "Accept: application/vnd.github+json")

echo "==> 1/3 查询现有 Pages 站点"
code=$(curl -s -o /tmp/pages-site.json -w '%{http_code}' "${AUTH[@]}" "${API}/pages")
if [ "$code" = "404" ]; then
  echo "    未启用 Pages，正在创建（build_type = workflow）"
  echo "==> 2/3 创建 Pages 站点"
  curl -s -X POST "${AUTH[@]}" "${API}/pages" \
       -H "Content-Type: application/json" \
       -d '{"build_type":"workflow"}' -o /tmp/pages-create.json -w "    HTTP %{http_code}\n"
  head -c 500 /tmp/pages-create.json; echo
else
  echo "    已存在（HTTP ${code}）："
  head -c 300 /tmp/pages-site.json; echo
  echo "==> 2/3 跳过创建"
fi

echo "==> 3/3 触发部署工作流"
code=$(curl -s -o /tmp/pages-dispatch.json -w '%{http_code}' -X POST "${AUTH[@]}" \
      "${API}/actions/workflows/pages.yml/dispatches" \
      -H "Content-Type: application/json" \
      -d '{"ref":"main"}')
echo "    HTTP ${code}"
[ "$code" = "204" ] || head -c 400 /tmp/pages-dispatch.json; echo

echo
echo "完成。请查看部署进度：https://github.com/${REPO}/actions"
echo "站点地址（通常）：https://$(echo "${REPO}" | tr '[:upper:]' '[:lower:]' | tr '/' '.').github.io/${REPO#*/}/"
