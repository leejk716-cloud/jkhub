#!/usr/bin/env python3
"""WNRF 플랜지 조립체: 플랜지 2개 + 스파이럴 운드 가스켓 + 스터드 볼트·헤비 헥스 너트.

좌표: 가스켓 하면 Z=0. 플랜지 A는 RF 면 Z=0에서 허브가 -Z, 플랜지 B는 RF 면 Z=g에서 허브가 +Z.
사용: python3 solidcraft-mcp/examples/flange_assembly.py [--size 2in-150]
"""
import argparse
import base64
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tests"))
from flange_wnrf import IN, OUT, SIZES, define_parameters, profile_sketch  # noqa: E402
from smoke_test import McpClient, text_json  # noqa: E402

# ASME B16.20 스파이럴 운드 가스켓 (inch, 직경) / B16.5 볼팅 / ASME B18.2.2 헤비 헥스 너트
GASKETS = {
    "2in-150": dict(inner_id=2.19, winding_id=2.75, winding_od=3.75, outer_od=4.12, ring_t=0.125),
}
BOLTING = {
    "2in-150": dict(dia=0.625, stud_len=3.25, nut_af=1.0625, nut_h=0.609),
}

COLORS = {
    "flange": "#8a929c",        # 탄소강 단조 (A105)
    "inner_ring": "#c9ced4",    # SS316 내륜
    "winding": "#3b3f44",       # SS316 + 그라파이트 권선
    "outer_ring": "#d8a53a",    # 탄소강 외륜 (도장 식별색)
    "bolting": "#5a4632",       # A193 B7 / A194 2H
}


def revolve_body(c, pts_sketch, name):
    """XZ 평면 단면을 Z축 회전해 새 바디를 만든다. pts_sketch: [(r, y)] (월드 Z = -y)."""
    b = text_json(c.call("batch", {"commands": [
        {"command": "sketch.create", "params": {"plane": "XZ", "name": f"{name}_profile"}},
        {"command": "sketch.line", "params": {"points": [list(p) for p in pts_sketch], "closed": True}},
        {"command": "sketch.finish"},
        {"command": "solid.revolve", "params": {"axis": "y", "operation": "new", "name": name, "body_name": name}},
    ]}))
    if not b.get("ok"):
        raise RuntimeError(f"{name}: {json.dumps(b, ensure_ascii=False)[:600]}")


def ring(r0, r1, z0, z1):
    return [(r0, -z0), (r1, -z0), (r1, -z1), (r0, -z1)]


def hex_points(cx, cy, phi, af):
    """중심 (cx, cy), 축 방향(phi+180°)으로 평평한 면이 향하는 정육각형."""
    rc = af / 2 / math.cos(math.radians(30))
    return [[cx + rc * math.cos(phi + math.radians(30 + 60 * k)),
             cy + rc * math.sin(phi + math.radians(30 + 60 * k))] for k in range(6)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="2in-150", choices=SIZES)
    ap.add_argument("--cli", default=os.path.expanduser("~/.local/bin/solidcraft-cli"))
    args = ap.parse_args()
    d, gk, bt = SIZES[args.size], GASKETS[args.size], BOLTING[args.size]

    g = gk["ring_t"] * IN          # 체결 후 플랜지 간격 = 링 두께 (권선은 링 두께까지 압축)
    tf = d["tf"] * IN
    pcd_r = d["W"] * IN / 2
    bolt_r = bt["dia"] * IN / 2
    stud_len = bt["stud_len"] * IN
    nut_h = bt["nut_h"] * IN
    angles = [math.radians(180 / d["n"] + 360 / d["n"] * k) for k in range(d["n"])]  # 중심선 straddle
    centers = [(pcd_r * math.cos(a), pcd_r * math.sin(a)) for a in angles]

    os.makedirs(OUT, exist_ok=True)
    c = McpClient([args.cli, "mcp", "--headless", "--allow-path", OUT])
    ex = lambda cmd, **p: text_json(c.call("execute", {"command": cmd, "params": p}))
    try:
        c.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "flange-assy", "version": "1"}})
        c.notify("notifications/initialized")
        c.call("new_design", {"name": f"WNRF-ASSY-{args.size}"})

        # 1) 플랜지 A (허브 -Z), 플랜지 B (RF 면 Z=g, 허브 +Z) + 허브 필릿
        #    두 플랜지가 같은 베벨 파라미터(bevel_angle, root_face)를 참조한다
        define_parameters(c, d)
        revolve_body(c, profile_sketch(d), "flange_A")
        revolve_body(c, profile_sketch(d, lambda z: f"-({g:.4f} + {z})" if isinstance(z, str) else -(g + z)),
                     "flange_B")
        ex("solid.fillet", edges=[[d["X"] * IN / 2, 0, -tf]], radius=d["r_hub"] * IN, body="flange_A")
        ex("solid.fillet", edges=[[d["X"] * IN / 2, 0, g + tf]], radius=d["r_hub"] * IN, body="flange_B")

        # 2) 볼트 구멍: 두 플랜지만 관통 (가스켓·볼트 생성 전)
        ex("sketch.create", plane="XY", name="bolt_holes")
        for cx, cy in centers:
            ex("sketch.circle.center", center=[cx, cy], radius=d["hole"] * IN / 2)
        ex("sketch.finish")
        ex("solid.extrude", distance=4 * d["Y"] * IN, direction="symmetric", operation="cut",
           targets=["flange_A", "flange_B"], name="bolt_holes_cut")

        # 3) 스파이럴 운드 가스켓 (B16.20): 내륜 / 권선 / 외륜
        r = lambda dia: dia * IN / 2
        revolve_body(c, ring(r(gk["inner_id"]), r(gk["winding_id"]), 0, g), "gasket_inner_ring")
        revolve_body(c, ring(r(gk["winding_id"]), r(gk["winding_od"]), 0, g), "gasket_winding")
        revolve_body(c, ring(r(gk["winding_od"]), r(gk["outer_od"]), 0, g), "gasket_outer_ring")

        # 4) 스터드 볼트: 조립체 중심(Z=g/2) 기준 대칭
        ex("sketch.create", plane="XY", offset=g / 2 - stud_len / 2, name="studs")
        for cx, cy in centers:
            ex("sketch.circle.center", center=[cx, cy], radius=bolt_r)
        ex("sketch.finish")
        ex("solid.extrude", distance=stud_len, operation="new", name="studs", body_name="stud")

        # 5) 헤비 헥스 너트: 플랜지 뒷면에 안착 (A측 Z=-tf 아래, B측 Z=g+tf 위)
        for side, z0 in (("A", -tf - nut_h), ("B", g + tf)):
            ex("sketch.create", plane="XY", offset=z0, name=f"nuts_{side}")
            for (cx, cy), a in zip(centers, angles):
                ex("sketch.line", points=hex_points(cx, cy, a, bt["nut_af"] * IN), closed=True)
                ex("sketch.circle.center", center=[cx, cy], radius=bolt_r)
            ex("sketch.finish")
            ex("solid.extrude", distance=nut_h, operation="new", profiles=[{"point": [
                cx + (bolt_r + 2) * math.cos(a), cy + (bolt_r + 2) * math.sin(a)]} for (cx, cy), a in zip(centers, angles)],
               exact_regions=True, name=f"nuts_{side}", body_name=f"nut_{side}")

        # 6) 색상
        m = text_json(c.call("measure"))
        names = [b["name"] for b in m["bodies"]]
        groups = {
            "flange": [n for n in names if n.startswith("flange")],
            "inner_ring": ["gasket_inner_ring"], "winding": ["gasket_winding"], "outer_ring": ["gasket_outer_ring"],
            "bolting": [n for n in names if n.startswith(("stud", "nut"))],
        }
        for key, bodies in groups.items():
            ex("appearance.assign", bodies=bodies, color=COLORS[key])

        # 7) 검증: 간섭, 바디 목록, 볼트 돌출 길이
        inter = ex("inspect.interference")
        print("bodies:", len(names), names)
        print("interference:", json.dumps({k: inter.get(k) for k in ("count", "checked")}, ensure_ascii=False),
              json.dumps(inter.get("interferences"), ensure_ascii=False)[:800])
        protrude = stud_len / 2 - (g / 2 + tf + nut_h)
        print(f"stud protrusion beyond nut: {protrude:.1f} mm each side")
        for b in m["bodies"]:
            print(f"  {b['name']:<22} vol {b.get('volume_mm3') or 0:>10.1f} mm³")

        base = os.path.join(OUT, f"flange_assy_{args.size}")
        c.call("save", {"path": base + ".solidcraft"})
        c.call("export", {"path": base + ".step", "format": "step"})

        def shot(tag, **kw):
            s = c.call("screenshot", {"width": 1100, "height": 800, "grid": False, "axes": False, **kw})
            img = next(x for x in s["content"] if x["type"] == "image")
            with open(f"{base}_{tag}.png", "wb") as f:
                f.write(base64.b64decode(img["data"]))

        shot("iso", view="iso")
        # 45° 단면: 볼트 2개를 지나도록
        a = angles[0]
        ex("inspect.section", plane={"origin": [0, 0, 0], "normal": [-math.sin(a), math.cos(a), 0]})
        shot("section", camera={"target": [0, 0, g / 2], "yaw": a + math.pi / 2, "pitch": 0.3, "distance": 300})
        print("saved:", base + ".{solidcraft,step}", "+ png")
    finally:
        c.close()


if __name__ == "__main__":
    main()
