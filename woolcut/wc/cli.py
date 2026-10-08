"""Cong chay TRONG Blender headless. Goi qua run.py, khong goi truc tiep:
  blender -b --factory-startup --python wc/cli.py -- <lenh> [tham so]"""
import sys, os, argparse, json, traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy
from wc import prep, render, bl, plan as planmod, export


def cmd_prep(a):
    out = os.path.join(HERE, "work", a.name)
    opts = {}
    if a.colors:
        opts["colors"] = a.colors
    opts["surface"] = "remesh" if a.remesh else "keep"
    opts["bumps"] = False if a.no_bumps else (True if a.bumps else "auto")
    opts["tilt"] = a.tilt
    tms, names, meta = prep.run(a.input, a.name, out, turn=a.turn, opts=opts)
    if len(names) <= 1:
        # model khong co mau (vd Tripo xuat "parts" khong texture): to moi khoi roi mot mau pastel de Claude nhin ro
        print("[mau] MODEL KHONG CO MAU - anh ke hoach to moi khoi mot mau de nhin; chi tach duoc theo hinh")
        cols = render.id_colors(len(tms), seed=3)
        objs = [bl.object_from_tm(t, "K%02d" % i, names, mat=bl.flat_material("_k%d" % i, cols[i]))
                for i, t in enumerate(tms)]
    else:
        objs = [bl.object_from_tm(t, "K%02d" % i, names) for i, t in enumerate(tms)]
    paths = render.plan_views(objs, out)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "prep.blend"), compress=True)
    for p in paths:
        print("[anh]", p)
    print("PREP_READY:", out)


FACING_TURNS = {"A": 0, "B": 90, "C": 180, "D": -90}
FACING_TILTS = {"E": 90, "F": -90}      # E: dinh model quay ra camera (lat tu tren xuong); F: day model (tu duoi len)


def cmd_facing(a):
    """Anh facing.png: model xoay 4 goc ung vien quanh Z (A 0, B +90, C 180, D -90), camera dung yen nhin tu -Y
    (huong mat truoc chuan) hoi cao. O nao model quay mat ve nguoi xem = goc xoay dung (Claude chon o run.py)."""
    import numpy as np, math
    from mathutils import Matrix, Vector
    from wc import load
    out = os.path.join(HERE, "work", a.name)
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = load.load(a.input, 0.0)
    W = np.concatenate([np.array([v.co[:] for v in o.data.vertices]) for o in objs if len(o.data.vertices)])
    lo, hi = W.min(0), W.max(0)
    c = (lo + hi) / 2
    piv = bpy.data.objects.new("_piv", None)
    bpy.context.scene.collection.objects.link(piv)
    for o in objs:
        o.data.transform(Matrix.Translation(Vector((-c).tolist())))
        o.parent = piv
    ext = hi - lo
    span = max(float(np.hypot(ext[0], ext[1])), float(ext[2])) * 1.08
    cam = render.setup(420)
    # Kieu viewport Solid (Workbench): xam + hoc toi (cavity) + vien - model trang khong mau van thay ro mat mui
    # (EEVEE + den manh: chuot / rai ca trang loa, Claude chon nham lung - lan thu dau 2026-10-02)
    sc = bpy.context.scene
    try:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        textured = any(n.type == "TEX_IMAGE" and n.image for m in bpy.data.materials if m.node_tree
                       for n in m.node_tree.nodes)
        sh.color_type = "TEXTURE" if textured else "SINGLE"
        sh.single_color = (0.62, 0.6, 0.57)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.cavity_ridge_factor = sh.cavity_valley_factor = 1.6
        sh.show_object_outline = True
        sh.show_shadows = True
        sc.world.color = (0.93, 0.93, 0.95)
    except (TypeError, AttributeError) as e:
        print("[mat truoc] Workbench loi, dung EEVEE: %s" % e)
    d = Vector((0, -1, 0.3)).normalized()
    cam.location = d * span * 4
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = span
    cam.data.clip_end = span * 20
    tiles = []
    keys = list(FACING_TURNS) + list(FACING_TILTS)
    for k in keys:
        if k in FACING_TURNS:
            piv.rotation_euler = (0, 0, math.radians(FACING_TURNS[k]))
        else:
            piv.rotation_euler = (math.radians(FACING_TILTS[k]), 0, 0)
        p = os.path.join(out, "_facing_%s.png" % k)
        bpy.context.scene.render.filepath = p
        bpy.ops.render.render(write_still=True)
        tiles.append(p)
    labels = [k if k in FACING_TURNS else ("E (lật: đỉnh ra trước)" if k == "E" else "F (lật: đáy ra trước)")
              for k in keys]
    path = render.compose(tiles, labels, os.path.join(out, "facing.png"), cols=3, tile=400)
    for p in tiles:
        os.remove(p)
    print("FACING_IMG:", path)


def cmd_trace(a):
    """Chay thu plan.json (chi hinh hoc) -> work/<Ten>/plan_trace.npz: manh + mat phang that cua tung nhat."""
    import numpy as np
    out = os.path.join(HERE, "work", a.name)
    plan = json.load(open(os.path.join(out, "plan.json"), encoding="utf-8"))
    tr = planmod.dry_run(out, plan)
    arr, idx = {}, []
    k = 0
    for i in sorted(tr):
        for planes, t in tr[i]:
            arr["V%d" % k], arr["F%d" % k] = t.V.astype(np.float32), t.F.astype(np.int32)
            arr["P%d" % k] = np.array([np.concatenate([c, n]) for c, n in planes], dtype=np.float32).reshape(-1, 6)
            idx.append(i)
            k += 1
    arr["idx"] = np.array(idx, dtype=np.int32)
    path = os.path.join(out, "plan_trace.npz")
    np.savez_compressed(path, **arr)
    print("TRACE_READY:", path)


def cmd_decor_lib(a):
    from wc import decor
    decor.build_library()
    print("DECOR_LIB_READY:", decor.LIB_BLEND)


def cmd_piece_views(a):
    """Anh luoi toa do cua MOT manh (piece_*.png) + ca model voi manh do to do (context_iso.png)."""
    out = os.path.join(HERE, "work", a.name)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(a.input, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith("_")]
    objs = [o for o in dst.objects if o is not None and o.type == "MESH"]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    tgt = [o for o in objs if o.name == a.piece]
    if not tgt:
        raise SystemExit("khong thay manh %s" % a.piece)
    gray = bl.flat_material("_g", (0.72, 0.72, 0.75))
    red = bl.flat_material("_r", (0.95, 0.15, 0.2))
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(red if o in tgt else gray)
    cam = render.setup(900)
    lo, hi = render.bounds(objs)
    render.shoot(cam, "iso", lo, hi, os.path.join(out, "context_iso.png"))
    for o in objs:
        if o not in tgt:
            bpy.data.objects.remove(o, do_unlink=True)
    tgt[0].data.materials.clear()
    tgt[0].data.materials.append(bl.flat_material("_y", (0.95, 0.8, 0.45)))
    render.plan_views(tgt, out, prefix="piece")
    print("PIECE_VIEWS:", out)


def cmd_refine_views(a):
    """TACH SAU: anh tung manh (du cac phia) + ung vien cat theo nep -> work/<Ten>/refine/ (Claude chon o run.py)."""
    from wc import refine
    pieces = [x for x in a.pieces.split("|") if x.strip()]
    out = os.path.join(HERE, "work", a.name, "refine")
    idx = refine.run(a.input, a.name, pieces, out)
    print("REFINE_VIEWS:", len(idx))


def cmd_struct_views(a):
    """XEM CA MODEL: anh 6 goc moi manh mot mau + ma manh, bang manh -> work/<Ten>/struct/ (Claude xem o run.py)."""
    from wc import structure
    rows = structure.run(a.input, os.path.join(HERE, "work", a.name, "struct"))
    print("STRUCT_VIEWS:", len(rows))


def cmd_decor_custom(a):
    from wc import decor
    decor.build_custom()
    print("DECOR_CUSTOM_READY:", decor.CUSTOM_BLEND)


def cmd_decor_views(a):
    """Anh luoi toa do cua cac manh HIEN TAI (parts_edit.blend) cho Claude chon cho gan decor + parts list."""
    out = os.path.join(HERE, "work", a.name)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(a.input, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith("_")]
    objs = [o for o in dst.objects if o is not None and o.type == "MESH"]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    import numpy as np
    cols = render.id_colors(len(objs), seed=5)
    rows = []
    for i, o in enumerate(objs):
        W = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
        lo, hi = W.min(0), W.max(0)
        kind = o.get("wc_kind") or o.get("wc_kind_auto", "M")
        rows.append(dict(name=o.name, kind=kind, color=o.get("wc_color", ""), decor=o.get("wc_decor", ""),
                         lo=[round(float(x), 2) for x in lo], hi=[round(float(x), 2) for x in hi]))
        o.data.materials.clear()
        o.data.materials.append(bl.flat_material("_d%d" % i, cols[i]))
    with open(os.path.join(out, "decor_parts.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    render.plan_views(objs, out, prefix="decor")
    print("DECOR_VIEWS:", out)


def _paint_rows(objs):
    """Hang cho Claude to mau: ten, loai, mau hien tai, co (so voi model), tam, diem neo tren be mat (tam mat lon nhat
    - giong panel _piece_anchor, de thao tac color trong plan.json chon dung manh khi cat lai)."""
    import numpy as np
    from wc import std
    W = [np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in objs]
    lo = np.min([w.min(0) for w in W], 0)
    hi = np.max([w.max(0) for w in W], 0)
    size = float((hi - lo).max()) or 1.0
    rows = []
    for o, w in zip(objs, W):
        kind = o.get("wc_kind") or o.get("wc_kind_auto") or "S"
        mat = o.data.materials[0].name if o.data.materials and o.data.materials[0] else ""
        col = (std.canonical(mat) if kind != "D" else None) or o.get("wc_color") or mat
        best = max(o.data.polygons, key=lambda f: f.area)
        rows.append(dict(name=o.name, kind=kind, color=col, size=round(float((w.max(0) - w.min(0)).max()) / size, 3),
                         center=[round(float(x), 2) for x in w.mean(0)],
                         anchor=[float(x) for x in (o.matrix_world @ best.center)]))
    try:            # neo xa manh khac: tam mat lon nhat hay nam dung mat tiep xuc -> lenh to mau chon nham manh (2026-10-08)
        from wc import overlap
        tms = [bl.tm_from_mesh(o.data, o.matrix_world) for o in objs]
        for r, a in zip(rows, overlap.far_anchors(tms, size)):
            r["anchor"] = a
    except Exception as e:
        print("[diem neo] loi: %s" % e)
    return rows


def _paint_images(objs, out, prefix, rows):
    imgs = render.result_views(objs, out, prefix=prefix)
    imgs.append(render.sheet(objs, os.path.join(out, "%s_sheet.png" % prefix),
                             ["%s %s %s" % (r["name"], r["kind"], r["color"].replace("Color_", "").replace("_mat", "")
                                            .split("_", 1)[-1]) for r in rows]))
    return imgs


def cmd_paint_views(a):
    """To mau tu panel: CHUP anh cac manh DANG CO trong canh (gom ca manh tach tay) - khong cat lai (2026-10-07:
    truoc day nut to mau chay lai ca ke hoach cat chi de co anh)."""
    out = os.path.join(HERE, "work", a.name)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(a.input, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith("_")]
    objs = sorted((o for o in dst.objects if o is not None and o.type == "MESH" and len(o.data.polygons)),
                  key=lambda o: o.name)
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    rows = _paint_rows(objs)
    with open(os.path.join(out, "paint_parts.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(parts=rows), fh, ensure_ascii=False, indent=1)
    _paint_images(objs, out, "paint", rows)
    render.plan_views(objs, out, prefix="paint_plan", views=("front",), fast=True)
    print("PAINT_VIEWS:", out)


def cmd_paint_apply(a):
    """Tach (split --paint / hang doi): gan mau paint.json THANG vao parts.blend + cap nhat parts.json va anh - thay
    cho viec cat lai ca model (mau khong doi hinh hoc)."""
    from wc import look
    out = os.path.join(HERE, "work", a.name)
    blend = os.path.join(out, "parts.blend")
    d = json.load(open(os.path.join(out, "paint.json"), encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=blend)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("_")]
    n = 0
    for o in objs:
        mn = d.get("apply", {}).get(o.name)
        if mn:
            look.apply_piece(o, o.get("wc_kind") or o.get("wc_kind_auto") or "S", mn, unwrap=False)
            n += 1
    pj = os.path.join(out, "parts.json")
    res = json.load(open(pj, encoding="utf-8"))
    for r in res["parts"]:
        r["color"] = d.get("apply", {}).get(r["name"], r["color"])
    with open(pj, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    objs.sort(key=lambda o: o.name)
    by = {r["name"]: r for r in res["parts"]}
    _paint_images(objs, out, "parts", [by.get(o.name) or dict(name=o.name, kind="S", color="") for o in objs])
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    print("[to mau] gan %d manh thang vao parts.blend (khong cat lai)" % n)
    print("PAINT_APPLIED:", blend)


def cmd_chain(a):
    """Hang doi chay tron (2026-10-07): register addon trong Blender nen roi chay chuoi cua panel (xem ca model + tach
    sau -> to mau -> decor) bang woolcut.headless_chain; ghi blend ket qua cho buoc xuat nhap."""
    root = os.path.dirname(HERE)
    if root not in sys.path:
        sys.path.insert(0, root)
    import woolcut
    woolcut.register()
    steps = [s for s in (a.steps or "").split(",") if s]
    out = woolcut.headless_chain(a.name, steps=steps, rounds=a.rounds)
    print("CHAIN_READY:", out)


def cmd_cut(a):
    out = os.path.join(HERE, "work", a.name)
    plan_path = a.plan or os.path.join(out, "plan.json")
    res = planmod.execute(out, plan_path, nmin=a.min, nmax=a.max, verbose=True, bevel=a.bevel, tiny=a.tiny)
    print("CUT_READY:", res)


def cmd_export(a):
    src = a.input or os.path.join(HERE, "work", a.name, "parts.blend")
    out = os.path.abspath(a.out) if a.out else os.path.join(HERE, "out")   # tuong doi -> anh render lac cho
    fbx = export.run(src, a.name, out, size=a.size, pivot=a.pivot, kind=a.kind, optimize=a.optimize, uv=a.uv)
    print("EXPORT_READY:", fbx)


def cmd_knit_front(a):
    """Anh mat truoc texture len cho Telegram: --in FBX nhap hoac .blend cac manh -> --out PNG."""
    src = os.path.abspath(a.input)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if src.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=src)
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    else:
        with bpy.data.libraries.load(src, link=False) as (s, d):
            d.objects = [n for n in s.objects if not n.startswith("_")]
        objs = [o for o in d.objects if o is not None and o.type == "MESH" and not o.get("wc_hidden")]
        for o in objs:
            bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    if not objs:
        print("KNIT_FAIL: khong co manh")
        return
    out = render.knit_front(objs, os.path.abspath(a.out), res=a.res)
    print("KNIT_READY:", out)


def main(argv):
    ap = argparse.ArgumentParser(prog="woolcut")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("prep")
    p.add_argument("--in", dest="input", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--turn", type=float, default=0.0)
    p.add_argument("--tilt", type=float, default=0.0, help="lat quanh X (do): model nam ngua / up")
    p.add_argument("--colors", type=int, default=0)
    p.add_argument("--remesh", action="store_true", help="dung lai luoi voxel + lam min (mac dinh giu luoi Tripo)")
    p.add_argument("--no-bumps", action="store_true", help="khong tu tach u nho (mat, mui, tai...) truoc khi cat")
    p.add_argument("--bumps", action="store_true", help="ep tach u nho (model lien khoi)")
    p.set_defaults(fn=cmd_prep)
    p = sub.add_parser("facing")
    p.add_argument("--in", dest="input", required=True)
    p.add_argument("--name", required=True)
    p.set_defaults(fn=cmd_facing)
    p = sub.add_parser("decor-lib")
    p.set_defaults(fn=cmd_decor_lib)
    p = sub.add_parser("piece-views")
    p.add_argument("--name", required=True)
    p.add_argument("--in", dest="input", required=True)
    p.add_argument("--piece", required=True)
    p.set_defaults(fn=cmd_piece_views)
    p = sub.add_parser("refine-views")
    p.add_argument("--name", required=True)
    p.add_argument("--in", dest="input", required=True)
    p.add_argument("--pieces", required=True, help="ten manh, cach nhau bang |")
    p.set_defaults(fn=cmd_refine_views)
    p = sub.add_parser("struct-views")
    p.add_argument("--name", required=True)
    p.add_argument("--in", dest="input", required=True)
    p.set_defaults(fn=cmd_struct_views)
    p = sub.add_parser("decor-custom")
    p.set_defaults(fn=cmd_decor_custom)
    p = sub.add_parser("decor-views")
    p.add_argument("--name", required=True)
    p.add_argument("--in", dest="input", required=True)
    p.set_defaults(fn=cmd_decor_views)
    p = sub.add_parser("paint-views")
    p.add_argument("--name", required=True)
    p.add_argument("--in", dest="input", required=True)
    p.set_defaults(fn=cmd_paint_views)
    p = sub.add_parser("paint-apply")
    p.add_argument("--name", required=True)
    p.set_defaults(fn=cmd_paint_apply)
    p = sub.add_parser("chain")
    p.add_argument("--name", required=True)
    p.add_argument("--steps", default="refine,paint,decor", help="cac buoc, cach nhau dau phay")
    p.add_argument("--rounds", type=int, default=2, help="so vong xem ca model / tach sau")
    p.set_defaults(fn=cmd_chain)
    p = sub.add_parser("trace")
    p.add_argument("--name", required=True)
    p.set_defaults(fn=cmd_trace)
    p = sub.add_parser("cut")
    p.add_argument("--name", required=True)
    p.add_argument("--plan")
    p.add_argument("--min", type=int, default=15)
    p.add_argument("--max", type=int, default=35)
    p.add_argument("--tiny", type=float, default=None, help="xoa manh < ti le nay cua co model (0 = tat; mac dinh 0.025)")
    p.add_argument("--bevel", type=float, default=None, help="ban kinh bo cong mep cat (0 = tat; mac dinh 0.075)")
    p.set_defaults(fn=cmd_cut)
    p = sub.add_parser("knit-front")
    p.add_argument("--in", dest="input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--res", type=int, default=1000)
    p.set_defaults(fn=cmd_knit_front)
    p = sub.add_parser("export")
    p.add_argument("--name", required=True)
    p.add_argument("--in", dest="input")
    p.add_argument("--size", type=float, default=export.EXPORT_SIZE, help="canh dai nhat (BearArt 8.2, trung vi bo goc 6.1)")
    p.add_argument("--pivot", choices=("center", "origin"), default="center",
                   help="tam manh: giua manh (mac dinh) | goc model (nhu BearArt)")
    p.add_argument("--out", default="", help="thu muc xuat (mac dinh woolcut/out; hang doi: work/<Ten>/draft)")
    p.add_argument("--kind", default="char", help="dang model de cham diem so voi mau (char/object/food/scene/plant)")
    p.add_argument("--optimize", type=float, default=0.0,
                   help="giam mat co kiem sai so: lech toi da (ti le co model, vd 0.002 = 0.2%%); 0 = khong")
    p.add_argument("--uv", choices=("v1", "v2"), default="v1", help="v2 = UV kieu moi (2-6 dao, do meo)")
    p.set_defaults(fn=cmd_export)
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 2
    a.fn(a)
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    try:
        rc = main(argv)
    except SystemExit as e:
        rc = e.code or 0
    except Exception:
        traceback.print_exc()
        rc = 1
    sys.stdout.flush()
    os._exit(rc)
