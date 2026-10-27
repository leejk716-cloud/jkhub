#!/usr/bin/env python3
"""SolidCraft MCP 서버 스모크 테스트 (stdio JSON-RPC, 외부 의존성 없음).

절차: initialize → tools/list → batch(박스 40x30x20 - 관통홀 R5) → measure(체적 검증)
      → export(STEP) → screenshot(선택, GPU 없으면 CPU 렌더)
사용: python3 solidcraft-mcp/tests/smoke_test.py [--cli PATH] [--no-screenshot]
"""
import argparse
import base64
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "out"))

# 해석해: 40*30*20 직육면체 - 반경 5, 높이 20 원통
EXPECTED_VOLUME = 40 * 30 * 20 - math.pi * 5**2 * 20  # ≈ 22429.2 mm³
TOLERANCE = 0.005  # 0.5 %


class McpClient:
    def __init__(self, cmd):
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True
        )
        self.next_id = 1

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        rid = self.next_id
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"서버가 응답 없이 종료됨 (method={method})")
            reply = json.loads(line)
            if reply.get("id") == rid:
                if "error" in reply:
                    raise RuntimeError(f"{method} 오류: {reply['error']}")
                return reply["result"]

    def call(self, name, arguments=None):
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        texts = [c["text"] for c in result["content"] if c["type"] == "text"]
        if result.get("isError"):
            raise RuntimeError(f"{name} 실패: {' '.join(texts)}")
        return result

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


def text_json(result):
    for c in result["content"]:
        if c["type"] == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                return c["text"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default=shutil.which("solidcraft-cli") or os.path.expanduser("~/.local/bin/solidcraft-cli"))
    ap.add_argument("--no-screenshot", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    client = McpClient([args.cli, "mcp", "--headless", "--allow-path", OUT])
    results = []

    def step(label, ok, detail=""):
        results.append((label, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {label} {detail}")

    try:
        init = client.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "jkhub-smoke-test", "version": "1"},
        })
        client.notify("notifications/initialized")
        info = init.get("serverInfo", {})
        step("initialize", True, f"{info.get('name')} {info.get('version')} / protocol {init.get('protocolVersion')}")

        tools = [t["name"] for t in client.request("tools/list")["tools"]]
        required = {"execute", "batch", "measure", "export", "inspect_design"}
        step("tools/list", required <= set(tools), f"{len(tools)}개 도구")

        batch = client.call("batch", {"commands": [
            {"command": "sketch.create", "params": {"plane": "XY"}},
            {"command": "sketch.rectangle.two_point", "params": {"p0": [0, 0], "p1": [40, 30]}},
            {"command": "sketch.finish"},
            {"command": "solid.extrude", "params": {"distance": 20}},
            {"command": "sketch.create", "params": {"plane": "XY"}},
            {"command": "sketch.circle.center", "params": {"center": [20, 15], "radius": 5}},
            {"command": "sketch.finish"},
            {"command": "solid.extrude", "params": {"distance": 20, "operation": "cut"}},
        ]})
        b = text_json(batch)
        step("batch 모델링 (박스+관통홀)", isinstance(b, dict) and b.get("ok") is True,
             f"completed={b.get('completed') if isinstance(b, dict) else b}")

        m = text_json(client.call("measure"))
        vol = m["total"]["volume_mm3"]
        err = abs(vol - EXPECTED_VOLUME) / EXPECTED_VOLUME
        step("measure 체적 검증", err <= TOLERANCE,
             f"측정 {vol:.1f} / 이론 {EXPECTED_VOLUME:.1f} mm³ (오차 {err * 100:.3f}%)")

        step_path = os.path.join(OUT, "smoke_part.step")
        client.call("export", {"path": step_path, "format": "step"})
        ok = os.path.isfile(step_path) and os.path.getsize(step_path) > 0
        step("export STEP", ok, f"{step_path} ({os.path.getsize(step_path) if ok else 0} bytes)")

        if not args.no_screenshot:
            try:
                shot = client.call("screenshot", {"view": "iso", "width": 800, "height": 600})
                img = next(c for c in shot["content"] if c["type"] == "image")
                png = os.path.join(OUT, "smoke_part.png")
                with open(png, "wb") as f:
                    f.write(base64.b64decode(img["data"]))
                meta = text_json(shot)
                renderer = meta.get("renderer") if isinstance(meta, dict) else "?"
                step("screenshot (iso)", True, f"{png} renderer={renderer}")
            except Exception as e:  # GPU/렌더러 부재는 연결 실패가 아니므로 경고만
                print(f"[WARN] screenshot 생략: {e}")
    finally:
        client.close()

    failed = [r for r in results if not r[1]]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} PASS")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
