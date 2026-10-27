#!/usr/bin/env python3
"""ASME B16.5 Weld Neck Raised Face 플랜지를 SolidCraft MCP로 모델링한다.

형상: 단면(반경 r, 축방향 z)을 XZ 평면에 그려 Z축 360° 회전 → 볼트 구멍 원형 4~n개 관통 컷.
단면은 RF(가스켓) 면 기준으로 그리며, 결과 바디는 RF 면이 Z=0, 허브가 -Z 방향(Z=-63.5)이다.
사용: python3 solidcraft-mcp/examples/flange_wnrf.py [--size 2in-150]
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tests"))
from smoke_test import McpClient, text_json  # noqa: E402

OUT = os.path.abspath(os.path.join(HERE, "..", "out"))
IN = 25.4

# ASME B16.5 치수 (inch). tf 는 RF 1/16" 포함 (Class 150/300 관례)
SIZES = {
    "2in-150": dict(
        O=6.00,     # 플랜지 외경
        tf=0.75,    # 플랜지 두께 (RF 포함)
        R=3.62,     # RF 외경
        rf=0.06,    # RF 높이
        X=3.06,     # 허브 기부 외경
        A=2.375,    # 용접단 외경 (= 2" 배관 OD)
        Y=2.50,     # 허브 포함 전장
        B=2.067,    # 보어 (Sch 40)
        W=4.75,     # 볼트 원 직경 (PCD)
        hole=0.75,  # 볼트 구멍 직경
        n=4,        # 볼트 수 (5/8" UNC)
    ),
}


def profile_mm(d):
    """단면 꼭짓점 [(r, z)] mm, RF 면 z=0 기준."""
    r = lambda v: v * IN / 2  # 직경(inch) → 반경(mm)
    z = lambda v: v * IN
    return [
        (r(d["B"]), 0.0),
        (r(d["R"]), 0.0),
        (r(d["R"]), z(d["rf"])),
        (r(d["O"]), z(d["rf"])),
        (r(d["O"]), z(d["tf"])),
        (r(d["X"]), z(d["tf"])),
        (r(d["A"]), z(d["Y"])),
        (r(d["B"]), z(d["Y"])),
    ]


def expected_volume(d, pts):
    """파푸스 정리(단면적 × 도심 회전 경로)로 회전체 체적, 볼트 구멍 차감."""
    a = cx = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
    a /= 2
    cx /= 6 * a
    rev = 2 * math.pi * cx * abs(a)
    holes = d["n"] * math.pi * (d["hole"] * IN / 2) ** 2 * (d["tf"] - d["rf"]) * IN
    return rev - holes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="2in-150", choices=SIZES)
    ap.add_argument("--cli", default=os.path.expanduser("~/.local/bin/solidcraft-cli"))
    args = ap.parse_args()
    d = SIZES[args.size]
    pts = profile_mm(d)
    pcd_r = d["W"] * IN / 2
    first = math.radians(180 / d["n"])  # 볼트 구멍은 중심선을 걸침(straddle)

    os.makedirs(OUT, exist_ok=True)
    c = McpClient([args.cli, "mcp", "--headless", "--allow-path", OUT])
    try:
        c.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "flange", "version": "1"}})
        c.notify("notifications/initialized")
        c.call("new_design", {"name": f"WNRF-{args.size}"})

        b = text_json(c.call("batch", {"commands": [
            {"command": "sketch.create", "params": {"plane": "XZ", "name": "profile"}},
            {"command": "sketch.line", "params": {"points": [list(p) for p in pts], "closed": True}},
            {"command": "sketch.finish"},
            {"command": "solid.revolve", "params": {"axis": "y", "name": "flange", "body_name": "flange"}},
        ]}))
        print("revolve:", "ok" if b.get("ok") else json.dumps(b, ensure_ascii=False)[:800])

        # 회전 결과의 Z 범위를 보고 볼트 구멍 컷 범위를 잡는다 (스케치 축 방향 확인용)
        m = text_json(c.call("measure"))
        print("bbox:", json.dumps(m["bodies"][0].get("bbox") if m.get("bodies") else m, ensure_ascii=False)[:300])

        # 패턴에 원의 curve id가 필요하므로 단계별 실행
        hx, hy = pcd_r * math.cos(first), pcd_r * math.sin(first)
        c.call("execute", {"command": "sketch.create", "params": {"plane": "XY", "name": "bolt_holes"}})
        circ = text_json(c.call("execute", {"command": "sketch.circle.center",
                                            "params": {"center": [hx, hy], "radius": d["hole"] * IN / 2}}))
        curve_ids = circ["created"]["curves"]
        c.call("execute", {"command": "sketch.pattern.circular",
                           "params": {"entities": curve_ids, "center": [0, 0], "count": d["n"]}})
        c.call("execute", {"command": "sketch.finish"})
        c.call("execute", {"command": "solid.extrude",
                           "params": {"distance": 4 * d["Y"] * IN, "direction": "symmetric",
                                      "operation": "cut", "name": "bolt_holes_cut"}})

        m = text_json(c.call("measure"))
        vol = m["total"]["volume_mm3"]
        exp = expected_volume(d, pts)
        print(f"volume: {vol:.1f} mm³ / 해석해 {exp:.1f} mm³ (오차 {abs(vol - exp) / exp * 100:.3f}%)")
        print("mass:", m["total"].get("mass_g") or m["total"].get("mass"))
        print("bbox:", json.dumps(m["bodies"][0].get("bbox"), ensure_ascii=False))

        base = os.path.join(OUT, f"flange_wnrf_{args.size}")
        c.call("save", {"path": base + ".solidcraft"})
        c.call("export", {"path": base + ".step", "format": "step"})
        c.call("export", {"path": base + ".stl", "format": "stl"})
        for view in ("iso", "front"):
            import base64
            shot = c.call("screenshot", {"view": view, "width": 1000, "height": 750, "grid": False})
            img = next(x for x in shot["content"] if x["type"] == "image")
            with open(f"{base}_{view}.png", "wb") as f:
                f.write(base64.b64decode(img["data"]))
        print("saved:", base + ".{solidcraft,step,stl}", "+ png")
    finally:
        c.close()


if __name__ == "__main__":
    main()
