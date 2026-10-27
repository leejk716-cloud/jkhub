#!/usr/bin/env bash
# SolidCraft CLI(MCP 서버 포함)를 sudo 없이 ~/.local/bin 에 설치한다.
# 사용: bash solidcraft-mcp/scripts/install_linux.sh [버전태그, 기본 latest]
set -euo pipefail
TAG="${1:-latest}"
if [ "$TAG" = "latest" ]; then
  URL="https://github.com/tangency-labs/solidcraft/releases/latest/download/solidcraft-linux-x86_64.deb"
else
  URL="https://github.com/tangency-labs/solidcraft/releases/download/${TAG}/solidcraft-linux-x86_64.deb"
fi
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "[1/3] 다운로드: $URL"
curl -fsSL -o "$WORK/sc.deb" "$URL"
echo "[2/3] 압축 해제 (dpkg 설치 없이)"
dpkg-deb -x "$WORK/sc.deb" "$WORK/root"
mkdir -p "$HOME/.local/bin"
install -m 0755 "$WORK/root/usr/bin/solidcraft-cli" "$HOME/.local/bin/solidcraft-cli"
echo "[3/3] 설치 완료: $HOME/.local/bin/solidcraft-cli"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "※ PATH에 ~/.local/bin 을 추가하세요: export PATH=\"\$HOME/.local/bin:\$PATH\"";; esac
