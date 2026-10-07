"""XEM CA MODEL (nguoi dung 2026-10-07, gau di xe Tripo 24 part: "phai tao hinh dung dau con gau, tach dau va than; tay
nen tach tay va ban tay; sua de dung duoc voi cac model khac"). Part Tripo khong khop bo phan that: "dau" chi la vo mu
trum co tai, MAT dinh vao THAN, canh tay lien ban tay. Xem tung manh rieng (wc/refine.py) khong thay duoc "manh nay
phai GHEP voi manh kia" -> buoc nay chup CA model, moi manh mot mau + MA MANH in tren manh, de Claude doi chieu voi bo
phan chuan va de xuat tach / ghep / doi ten (planner.structure). Chay trong Blender (headless) -> work/<Ten>/struct/
  views.png    6 goc, moi manh mot mau, ma manh (P06, P01.3) in ngay tren phan nhin thay cua manh
  sheet.png    tung manh rieng + ma + ten
  pieces.json  [{name, short, label, kind, faces, frac, lo, hi}]"""
import os, json
import numpy as np
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from . import bl, render

VIEWS = (("trước", (0, -1, 0.25)), ("sau", (0, 1, 0.25)), ("trái", (-1, -0.15, 0.25)), ("phải", (1, -0.15, 0.25)),
         ("trên", (0.0, -0.3, 1.0)), ("iso", (0.75, -1, 0.65)))


def short(name):
    return name.split(" ")[0]


def _bvh(o):
    me = o.data
    me.calc_loop_triangles()
    V = [o.matrix_world @ v.co for v in me.vertices]
    F = [tuple(t.vertices) for t in me.loop_triangles]
    return BVHTree.FromPolygons(V, F, all_triangles=True)


def _tag_point(o, objs, bvhs, d, diag, rnd):
    """Diem NHIN THAY cua manh o tu huong d (tia tu phia camera trung manh o truoc tien) -> noi in ma manh; None neu bi che."""
    W = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
    if not len(W):
        return None
    c = W.mean(0)
    cands = [c] + [W[i] for i in rnd.choice(len(W), min(40, len(W)), replace=False)]
    cands.sort(key=lambda p: float(np.linalg.norm((p - c) - d * ((p - c) @ d))))     # gan truc qua tam truoc
    me = objs.index(o)
    for p in cands:
        org = Vector((p + d * diag * 2).tolist())
        best = None
        for k, bv in enumerate(bvhs):
            hit = bv.ray_cast(org, Vector((-d).tolist()))
            if hit[0] is not None and (best is None or hit[3] < best[1]):
                best = (k, hit[3], hit[0])
        if best is not None and best[0] == me:
            return np.array(best[2][:]) + d * 0.01 * diag
    return None


def run(blend, out, log=print):
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(blend, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith("_")]
    objs = [o for o in dst.objects if o is not None and o.type == "MESH"]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    rows, vols = [], {}
    for o in objs:
        t = bl.tm_from_mesh(o.data, o.matrix_world)
        vols[o.name] = abs(t.volume())
    tot = sum(vols.values()) or 1e-9
    main = [o for o in objs if (o.get("wc_kind") or o.get("wc_kind_auto", "M")) != "D"]
    cols = render.id_colors(len(main), seed=11)
    for i, o in enumerate(main):
        o.color = (*cols[i], 1.0)
    for o in objs:
        if o not in main:
            o.color = (0.85, 0.85, 0.85, 1.0)
        W = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
        rows.append(dict(name=o.name, short=short(o.name), label=o.get("wc_label", ""),
                         kind=o.get("wc_kind") or o.get("wc_kind_auto", "M"), faces=len(o.data.polygons),
                         frac=round(vols[o.name] / tot, 4), lo=np.round(W.min(0), 2).tolist(),
                         hi=np.round(W.max(0), 2).tolist()))
    bvhs = [_bvh(o) for o in objs]
    lo, hi = render.bounds(objs)
    cen = (lo + hi) / 2
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    sc = bpy.context.scene
    tiles = []
    rnd = np.random.RandomState(4)
    for k, (vn, d) in enumerate(VIEWS):
        d = np.asarray(d, float)
        d /= np.linalg.norm(d)
        cam = render.setup(700)
        render._workbench(sc, by_object=True)
        cam.location = Vector((cen + d * diag * 3).tolist())
        cam.rotation_euler = Vector((-d).tolist()).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = diag * 1.05
        cam.data.clip_start, cam.data.clip_end = diag * 0.01, diag * 20
        texts = []
        rot = cam.rotation_euler.copy()
        for o in main:
            p = _tag_point(o, objs, bvhs, d, diag, rnd)
            if p is None:
                continue
            cu = bpy.data.curves.new("_tag", "FONT")
            cu.body = short(o.name)
            cu.size = 0.032 * diag
            cu.align_x, cu.align_y = "CENTER", "CENTER"
            tob = bpy.data.objects.new("_tag", cu)
            tob.location = Vector(p.tolist())
            tob.rotation_euler = rot
            tob.color = (0.02, 0.02, 0.05, 1.0)
            sc.collection.objects.link(tob)
            texts.append(tob)
        p = os.path.join(out, "_v%d.png" % k)
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        tiles.append(p)
        for tob in texts:
            cu = tob.data
            bpy.data.objects.remove(tob, do_unlink=True)
            bpy.data.curves.remove(cu)
    render.compose(tiles, [v for v, _ in VIEWS], os.path.join(out, "views.png"), cols=3, tile=600)
    for p in tiles:
        os.remove(p)
    render.sheet(main, os.path.join(out, "sheet.png"),
                 ["%s %s" % (short(o.name), o.get("wc_label", "")) for o in main], tile=200, cols=7)
    with open(os.path.join(out, "pieces.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    log("[xem ca model] %d manh (%d M/S) -> %s" % (len(objs), len(main), out))
    return rows
