"""XEM CA MODEL (nguoi dung 2026-10-07, gau di xe Tripo 24 part: "phai tao hinh dung dau con gau, tach dau va than; tay
nen tach tay va ban tay; sua de dung duoc voi cac model khac"). Part Tripo khong khop bo phan that: "dau" chi la vo mu
trum co tai, MAT dinh vao THAN, canh tay lien ban tay. Xem tung manh rieng (wc/refine.py) khong thay duoc "manh nay
phai GHEP voi manh kia" -> buoc nay chup CA model, moi manh mot mau + MA MANH in tren manh, de Claude doi chieu voi bo
phan chuan va de xuat tach / ghep / doi ten (planner.structure). Chay trong Blender (headless) -> work/<Ten>/struct/
  views.png    6 goc, moi manh mot mau, ma manh (P06, P01.3) in ngay tren phan nhin thay cua manh
  sheet.png    tung manh rieng + ma + ten
  excess.png   manh co PHAN DU (wc/trim.excess_voxel): phan tool se cat to DO - Claude duyet "trim" / bo qua
  pieces.json  [{name, short, label, kind, faces, frac, lo, hi, excess}]"""
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
    try:
        ex = excess_sheet(main, objs, os.path.join(out, "excess.png"), log)
    except Exception as e:                          # anh phu - loi thi Claude van xem duoc views / sheet
        log("[xem ca model] loi do phan du: %s" % e)
        ex = {}
    for r in rows:
        if r["name"] in ex:
            r["excess"] = round(ex[r["name"]], 3)
    with open(os.path.join(out, "pieces.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    log("[xem ca model] %d manh (%d M/S) -> %s" % (len(objs), len(main), out))
    return rows


EXCESS_SHOW = 0.03        # manh co >= 3% dien tich la phan du (do bang phep mo voxel) -> dua vao excess.png cho Claude


def excess_sheet(main, objs, path, log=print, tile=260, cols=5):
    """Ung vien PHAN DU (nguoi dung 2026-10-08: "tool tu detect cac part xau va sua lai hoac an di"): phep mo voxel tim
    vat / kim / gai mong hon han than chinh - nhung cung bat nham tay cam, qua bong, vanh mat (mong hon than ma la chi
    tiet that) -> chi VE ra (phan se cat to DO) de Claude quyet "trim". -> {ten manh: ti le dien tich du}."""
    from . import trim
    if os.path.exists(path):
        os.remove(path)
    found = []
    for o in main:
        t = bl.tm_from_mesh(o.data, o.matrix_world)
        kill, info = trim.excess_voxel(t)
        if kill is None:
            continue
        A = t.face_areas()
        ex = float(A[kill].sum() / max(A.sum(), 1e-12))
        if EXCESS_SHOW <= ex <= trim.EX_MAX:
            found.append((o, t, kill, ex))
    if not found:
        return {}
    sc = bpy.context.scene
    cam = render.setup(tile)
    restore = render._workbench(sc, by_object=False)
    hide = {o.name: o.hide_render for o in objs}
    for o in objs:
        o.hide_render = True
    mg = bpy.data.materials.new("_giu")
    mg.diffuse_color = (0.72, 0.74, 0.78, 1.0)
    mr = bpy.data.materials.new("_du")
    mr.diffuse_color = (0.92, 0.12, 0.08, 1.0)
    tiles, labels = [], []
    try:
        for o, t, kill, ex in found:
            ob = bl.object_from_tm(t, "_du_view", per_face=False)
            ob.data.materials.clear()
            ob.data.materials.append(mg)
            ob.data.materials.append(mr)
            ob.data.polygons.foreach_set("material_index", np.asarray(kill, np.int32))
            lo, hi = t.bbox()
            c = (lo + hi) / 2
            diag = float(np.linalg.norm(hi - lo)) or 1.0
            d = np.array((0.75, -1.0, 0.65))
            d /= np.linalg.norm(d)
            cam.location = Vector((c + d * diag * 3).tolist())
            cam.rotation_euler = Vector((-d).tolist()).to_track_quat("-Z", "Y").to_euler()
            cam.data.ortho_scale = diag * 1.1
            cam.data.clip_start, cam.data.clip_end = diag * 0.01, diag * 20
            p = os.path.join(os.path.dirname(path), "_du%d.png" % len(tiles))
            sc.render.filepath = p
            bpy.ops.render.render(write_still=True)
            tiles.append(p)
            labels.append("%s · đỏ %.0f%%" % (short(o.name), 100 * ex))
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            bpy.data.meshes.remove(me)
        render.compose(tiles, labels, path, cols=min(cols, len(tiles)), tile=tile)
    finally:
        for p in tiles:
            if os.path.exists(p):
                os.remove(p)
        for o in objs:
            o.hide_render = hide[o.name]
        bpy.data.materials.remove(mg)
        bpy.data.materials.remove(mr)
        restore()
    log("[xem ca model] %d manh co phan du (to do) -> %s" % (len(found), path))
    return {o.name: ex for o, t, kill, ex in found}
