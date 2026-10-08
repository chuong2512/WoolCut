"""TOI UU LUOI khi "Xuat FBX toi uu" (2026-10-08, nguoi dung: "xuat fbx nhung optimize lai mesh cho do policount, van
giu chat luong"). Moi manh: Decimate COLLAPSE (quadric) voi ti le nho nhat ma
  - luoi van KIN (manh M co lai trong game - phai dac),
  - sai lech hai chieu giua luoi moi va luoi cu <= tol = min(tol_rel x co model, 3% co manh) (manh nho nhu mat, nut
    khong bi vo thanh khoi go ghe).
Do thu tren SnowBearChef (28k tam giac): tol 0.1% -> -27%, 0.2% -> -44%, 0.4% -> -65%, ~1 giay ca model."""
import bpy, bmesh
from mathutils.bvhtree import BVHTree

DEFAULT_TOL = 0.002       # 0.2% co model
PIECE_TOL = 0.03          # tran: 3% co chinh manh


def _tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def _bvh(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def _closed(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    ok = len(bm.edges) > 0 and all(len(e.link_faces) == 2 for e in bm.edges)
    bm.free()
    return ok


def _deviation(a, b, ta=None):
    """Sai lech hai chieu (lon nhat) giua hai luoi cung he toa do; lay mau dinh."""
    import numpy as np
    from mathutils import Vector
    ta = ta or _bvh(a)
    tb = _bvh(b)
    A = np.empty(len(a.vertices) * 3)
    a.vertices.foreach_get("co", A)               # bpy_prop_collection khong cat [::k] duoc (manh > 3000 dinh loi)
    A = A.reshape(-1, 3)[::max(1, len(a.vertices) // 1500)]
    d1 = max(((tb.find_nearest(Vector(v))[3] or 0.0) for v in A), default=0.0)
    d2 = max(((ta.find_nearest(v.co)[3] or 0.0) for v in b.vertices), default=0.0)
    return max(d1, d2)


def optimize_object(ob, tol, steps=7):
    """Giam mat MOT object (luoi da o toa do cuoi, matrix identity) -> (tam giac truoc, sau)."""
    me0 = ob.data
    n0 = _tris(me0)
    if n0 < 60 or tol <= 0:
        return n0, n0
    was_closed = _closed(me0)
    ta = _bvh(me0)
    best = None
    lo, hi = 0.03, 1.0
    for _ in range(steps):
        r = (lo + hi) / 2
        m = ob.modifiers.new("_opt", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = r
        m.use_collapse_triangulate = False
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.remove(m)
        ok = (not was_closed or _closed(me2)) and _deviation(me0, me2, ta) <= tol
        if ok:
            if best is not None:
                bpy.data.meshes.remove(best)
            best, hi = me2, r
        else:
            bpy.data.meshes.remove(me2)
            lo = r
    if best is None:
        return n0, n0
    n1 = _tris(best)
    if n1 >= n0:
        bpy.data.meshes.remove(best)
        return n0, n0
    mats = list(me0.materials)
    ob.data = best
    best.materials.clear()
    for m in mats:
        best.materials.append(m)
    best.name = me0.name
    if me0.users == 0:
        bpy.data.meshes.remove(me0)
    return n0, n1


def optimize(objs, model_size, tol_rel=DEFAULT_TOL, log=print):
    """Moi object (S / M / D) -> tong (truoc, sau)."""
    tot0 = tot1 = 0
    bpy.context.view_layer.update()
    for ob in objs:
        size = max(ob.dimensions) or model_size
        tol = min(tol_rel * model_size, PIECE_TOL * size)
        a, b = optimize_object(ob, tol)
        tot0 += a
        tot1 += b
    if log:
        log("[toi uu] sai lech toi da %.2f%% co model: %d -> %d tam giac (-%.0f%%)" % (
            100 * tol_rel, tot0, tot1, 100 * (1 - tot1 / max(1, tot0))))
    return tot0, tot1
