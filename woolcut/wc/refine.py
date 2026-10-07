"""TACH SAU (nguoi dung 2026-10-06): sau khi tach bo phan, xem TUNG bo phan du cac phia + do NEP GAP -> Claude quyet dinh
tach tiep gi. Chay trong Blender (headless): moi manh -> work/<Ten>/refine/<manh>/
  context.png   ca model, manh nay to do (nhin truoc + iso)
  piece_*.png   rieng manh, luoi toa do that, 5 huong + iso
  cands.png     ban do nep (2 o) + ung vien cat theo nep (#1..#k, phan to mau = phan roi ra)
  cands.json    [{k, frac, cover, mode, op, tip, anchor}] - op ghi thang vao plan.json khi Claude chon"""
import os, re, json, time
import numpy as np
import bpy
from mathutils import Vector
from . import bl, render, crease

GRAY = (0.72, 0.72, 0.75)
RED = (0.95, 0.28, 0.22)


def folder_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "piece"


def _mesh_obj(t, name, rgb, vcol=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(t.V.tolist(), [], t.F.tolist())
    me.update()
    if vcol is not None:
        a = me.color_attributes.new("c", "FLOAT_COLOR", "POINT")
        a.data.foreach_set("color", np.asarray(vcol, np.float32).ravel())
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.color = (rgb[0], rgb[1], rgb[2], 1.0)
    return o


def _shoot(objs, d, path, res, color_type="OBJECT"):
    """Anh nhanh Workbench: camera truc giao nhin theo -d, khung vua cac object."""
    sc = bpy.context.scene
    cam = render.setup(res)
    render._workbench(sc, by_object=True)
    sc.display.shading.color_type = color_type
    lo, hi = render.bounds(objs)
    c = (lo + hi) / 2
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    cam.location = Vector(c + d * diag * 3)
    cam.rotation_euler = Vector(-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = diag * 1.1
    cam.data.clip_start, cam.data.clip_end = diag * 0.01, diag * 20
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def _only(objs):
    keep = set(o.name for o in objs)
    for o in bpy.context.scene.objects:
        if o.type in ("MESH", "FONT", "CURVE"):
            o.hide_render = o.name not in keep


def _pick(P, k, seed=0):
    P = np.asarray(P, float)
    if len(P) > k:
        P = P[np.random.RandomState(seed).choice(len(P), k, replace=False)]
    return np.round(P, 3).tolist()


def _samples(t, cd):
    """Diem mau hai phia cua ung vien: "pts" (sat bien phia phan tach - addon bo phieu xem manh nao mang ten nay) va
    "part_s" / "rest_s" (rai khap hai mien - planner doi nhat cat Claude tu chi diem sang ung vien trung khop)."""
    m = cd.get("mask")
    if m is not None:
        C = t.face_centers()
        ps, rs = C[m], C[~m]
    else:
        ps, rs = cd["part"].face_centers(), cd["rest"].face_centers()
    ring = cd["op"].get("part") or ps
    return dict(pts=_pick(ring, 12, 1), part_s=_pick(ps, 150, 2), rest_s=_pick(rs, 150, 3))


def piece(ob, all_objs, out, log=print):
    """Anh + ung vien cho mot manh. Tra ve dict tom tat."""
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    # --- ca model, manh nay to do
    keep_col = {o.name: tuple(o.color) for o in all_objs}
    for o in all_objs:
        o.color = (*(RED if o is ob else GRAY), 1.0)
    _only(all_objs)
    tiles = []
    for k, d in (("truoc", (0, -1, 0.3)), ("iso", (0.75, -1, 0.65))):
        p = os.path.join(out, "_ctx_%s.png" % k)
        _shoot(all_objs, d, p, 520)
        tiles.append(p)
    render.compose(tiles, ["cả model - nhìn trước", "cả model - iso"], os.path.join(out, "context.png"), cols=2, tile=520)
    for p in tiles:
        os.remove(p)
    for o in all_objs:
        o.color = keep_col[o.name]
    # --- rieng manh, luoi toa do
    _only([ob])
    mats = [s.material for s in ob.material_slots]
    ob.data.materials.clear()
    ob.data.materials.append(bl.flat_material("_refine_y", (0.95, 0.8, 0.45)))
    render.plan_views([ob], out, prefix="piece", res=700, fast=True)
    ob.data.materials.clear()
    for m in mats:
        ob.data.materials.append(m)
    # --- ung vien theo nep
    t = bl.tm_from_mesh(ob.data, ob.matrix_world)
    cands, heat = crease.candidates(t, log=log)
    _only([])
    tiles, labs = [], []
    x = np.clip(heat / 0.8, 0, 1)
    vcol = np.stack([0.78 + 0.22 * x, 0.76 * (1 - x), 0.78 * (1 - x), np.ones_like(x)], axis=1)
    h = _mesh_obj(t, "_heat", GRAY, vcol)
    for k, d in (("trước", (0.55, -1, 0.45)), ("sau", (-0.55, 1, 0.45))):
        p = os.path.join(out, "_heat_%d.png" % len(tiles))
        _shoot([h], d, p, 360, color_type="VERTEX")
        tiles.append(p)
        labs.append("nếp gấp (đỏ) - %s" % k)
    me = h.data
    bpy.data.objects.remove(h, do_unlink=True)
    bpy.data.meshes.remove(me)
    c0 = t.centroid()
    rows = []
    for i, cd in enumerate(cands):
        a = _mesh_obj(cd["rest"], "_rest", GRAY)
        b = _mesh_obj(cd["part"], "_part", RED)
        pc = cd["part"].centroid() - c0
        v = pc / (np.linalg.norm(pc) or 1.0) * 0.6 + np.array([0.0, -0.8, 0.45])
        p = os.path.join(out, "_cand_%02d.png" % (i + 1))
        _shoot([a, b], v, p, 360)
        tiles.append(p)
        labs.append("#%d  %.1f%%" % (i + 1, 100 * cd["frac"]))
        for o in (a, b):
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(me)
        rows.append(dict(k=i + 1, frac=round(float(cd["frac"]), 4), cover=round(float(cd["cover"]), 3),
                         mode=cd["mode"], op=cd["op"], tip=cd["tip"], anchor=cd["anchor"], **_samples(t, cd)))
    render.compose(tiles, labs, os.path.join(out, "cands.png"), cols=4, tile=360)
    for p in tiles:
        os.remove(p)
    with open(os.path.join(out, "cands.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False)
    _only(all_objs)
    log("[tach sau] %s: %d mat, %d ung vien theo nep (%.0fs)" % (ob.name, len(t.F), len(rows), time.time() - t0))
    return dict(name=ob.name, faces=int(len(t.F)), cands=len(rows), dir=out)


def run(blend, name, pieces, out_root, log=print):
    """Nap cac manh hien tai (blend) -> anh + ung vien cho tung manh trong `pieces` -> refine/index.json."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(blend, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith("_")]
    objs = [o for o in dst.objects if o is not None and o.type == "MESH"]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    vols = {}
    for o in objs:
        t = bl.tm_from_mesh(o.data, o.matrix_world)
        vols[o.name] = abs(t.volume())
    total = sum(vols.values()) or 1e-9
    os.makedirs(out_root, exist_ok=True)
    index = []
    for nm in pieces:
        ob = bpy.data.objects.get(nm)
        if ob is None:
            log("[tach sau] khong thay manh %s" % nm)
            continue
        info = piece(ob, objs, os.path.join(out_root, folder_name(nm)), log)
        info["model_frac"] = round(vols.get(nm, 0.0) / total, 4)
        info["label"] = ob.get("wc_label", "")
        index.append(info)
    with open(os.path.join(out_root, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    return index
