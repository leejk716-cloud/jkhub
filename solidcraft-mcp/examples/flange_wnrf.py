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
        r_hub=0.31,  # 허브-플랜지 뒷면 필릿 반경 (B16.5 r)
    ),
}

# 용접단 베벨 (ASME B16.25, 벽두께 22 mm 이하): 37.5°, 루트면 1.6 mm
BEVEL_DEG = 37.5
ROOT_FACE = 1.6


def profile_mm(d):
    """단면 꼭짓점 [(r, z)] mm, RF 면 z=0 기준. 용접단 베벨 포함."""
    r = lambda v: v * IN / 2  # 직경(inch) → 반경(mm)
    z = lambda v: v * IN
    land = r(d["B"]) + ROOT_FACE
    bevel_dz = (r(d["A"]) - land) * math.tan(math.radians(BEVEL_DEG))
    return [
        (r(d["B"]), 0.0),
        (r(d["R"]), 0.0),
        (r(d["R"]), z(d["rf"])),
        (r(d["O"]), z(d["rf"])),
        (r(d["O"]), z(d["tf"])),
        (r(d["X"]), z(d["tf"])),
        (r(d["A"]), z(d["Y"]) - bevel_dz),  # 허브 테이퍼 끝 = 베벨 시작
        (land, z(d["Y"])),                   # 베벨 끝 = 루트면 외측
        (r(d["B"]), z(d["Y"])),
    ]


def fillet_volume(d, pts):
    """허브-플랜지 뒷면 오목 모서리(꼭짓점 X) 필릿이 더하는 체적 (근사: 도심을 꼭짓점 근처로)."""
    rf = d["r_hub"] * IN
    (x0, y0), (x1, y1) = pts[5], pts[6]
    theta = math.pi / 2 + math.atan2(x0 - x1, y1 - y0)  # 뒷면(반경방향)과 허브면 사이 내각
    area = rf ** 2 * (1 / math.tan(theta / 2) - (math.pi - theta) / 2)
    return 2 * math.pi * (x0 + 0.25 * rf) * area


def expected_volume(d, pts):
    """파푸스 정리(단면적 × 도심 회전 경로)로 회전체 체적, 볼트 구멍 차감, 필릿 가산."""
    a = cx = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
    a /= 2
    cx /= 6 * a
    rev = 2 * math.pi * cx * abs(a)
    holes = d["n"] * math.pi * (d["hole"] * IN / 2) ** 2 * (d["tf"] - d["rf"]) * IN
    return rev - holes + fillet_volume(d, pts)


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

        # 허브-플랜지 뒷면 필릿: XZ 스케치의 +y 가 월드 -Z 로 회전되므로 뒷면은 Z = -tf
        hub_edge = [d["X"] * IN / 2, 0.0, -d["tf"] * IN]
        c.call("execute", {"command": "solid.fillet",
                           "params": {"edges": [hub_edge], "radius": d["r_hub"] * IN, "name": "hub_fillet"}})

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
