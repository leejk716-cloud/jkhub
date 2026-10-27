# SolidCraft × MCP 연동

[SolidCraft](https://github.com/tangency-labs/solidcraft)(오픈소스 파라메트릭 3D CAD, Rust)의
내장 MCP 서버(`solidcraft-cli mcp`)를 Claude Code에 연결하는 설정과 검증 스크립트.

## 구성

| 파일 | 역할 |
|---|---|
| `../.mcp.json` | 프로젝트 범위 MCP 등록 (`solidcraft` 서버, 파일 접근은 `solidcraft-mcp/out`로 제한) |
| `scripts/install_linux.sh` | Linux: `.deb`에서 `solidcraft-cli`만 추출해 `~/.local/bin`에 설치 (sudo 불필요) |
| `tests/smoke_test.py` | stdio JSON-RPC 스모크 테스트 (외부 패키지 불필요) |
| `out/` | 테스트 산출물 (STEP, PNG) — git 제외 |

## 설치

| OS | 방법 |
|---|---|
| Windows | [MSI 설치](https://github.com/tangency-labs/solidcraft/releases/latest/download/solidcraft-windows-x64.msi) → `C:\Program Files\SolidCraft\solidcraft-cli.exe` |
| macOS | [DMG](https://github.com/tangency-labs/solidcraft/releases/latest/download/solidcraft-macos-universal.dmg) 설치 후 앱 1회 실행 (CLI 자동 링크) |
| Linux | `bash solidcraft-mcp/scripts/install_linux.sh` |

## Claude Code 연결

- 이 저장소에서 실행하면 `.mcp.json`이 자동 인식됨 (최초 1회 승인).
- 전역 등록: `claude mcp add solidcraft -- solidcraft-cli mcp`
- 또는 앱 메뉴 **Help > Connect AI assistants…** / `solidcraft-cli mcp setup --client claude-code`
- Windows에서 PATH 미등록 시 `command`를 `C:\\Program Files\\SolidCraft\\solidcraft-cli.exe`로 변경.

동작 모드:

- **Headless**: 앱 없이 서버 자체 세션에서 모델링.
- **Bridged**: 데스크톱 앱이 실행 중이면 자동 연결(기본 포트 `127.0.0.1:27878`) → 모델링 과정을 화면으로 확인.

## 테스트

```sh
python3 solidcraft-mcp/tests/smoke_test.py            # 전체
python3 solidcraft-mcp/tests/smoke_test.py --no-screenshot
```

검증 항목: `initialize` → `tools/list` → `batch`(40×30×20 박스 − Ø10 관통홀)
→ `measure` 체적 vs 이론값 22,429.2 mm³ (허용 0.5%) → STEP export → iso 스크린샷.
