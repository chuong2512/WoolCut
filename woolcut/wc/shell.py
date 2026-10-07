"""TACH VO + DUNG PHAN BEN TRONG (nguoi dung 2026-10-07, gau di xe may BearOnScooter3dModel1).

Tripo hay duc lop ngoai thanh KHOI DAC up len manh ben trong: mu bao hiem la mot vom dac, mat gau la phan tren-truoc
cua manh THAN, ben trong mu khong co dau. Tach mu ra roi go di (game cuon len tung manh) thi chi con mat cat nghieng
tren dinh than. Thao tac nay dung lai cho dung:
  1. CO: tiet dien hep nhat cua manh trong, ngay duoi day vo (TM.snap) -> cat cuc bo (nap co mang ma nhat cat nen duoc
     bo cong nhu moi nhat khac): phan tren = MAT, phan duoi = THAN;
  2. PHAN TRONG = (vo co vao t) U (tam day = vo giao mat no ra 1.25 t) U mat. Co / no bang VOXEL + day theo phap tuyen:
     Solidify thang mat Tripo thi tai mu tu cat nhau, tam day noi gai xa 7 don vi o goc nhon -> Boolean hong;
  3. VO = vo goc - phan trong: rong, day ~t, ho o cho ap vao mat; mat ngoai giu nguyen be mat Tripo.
Hai manh bu khit (khong chong, khong khe). Chay trong Blender (Remesh voxel + Boolean EXACT). Ghi plan.json:
  {"op": "shell", "outer": diem neo vo, "inner": diem neo manh trong, "t": do day, "neck": [[diem], [phap tuyen]]}"""
import numpy as np
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .tm import TM, unit
from . import bl

T_REL = 0.04          # do day vo mac dinh = 4% co manh vo (mu gau 6,2 -> 0,25)
CONTACT_REL = 0.006   # mat vo cach manh trong < 0.6% co model = ap vao
SLAB_REL = (1.25, 1.5, 1.8)   # tam day = vo giao (mat no ra k.t); vo ho thi thu k lon hon. 1.15 de lai khe mong -> vo
#                               ho; 1.5 an mat mep vanh mu tren mat (vien be + go khi go mu) - gau 2026-10-07


def _bvh(t):
    return BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)


def _obj(t, name):
    me = bl.mesh_from_tm(t, name, flat_caps=False)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _evaluated_tm(ob):
    """Object (ap dung modifier) -> TM toa do the gioi."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    V = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3)
    F = np.array([[v.index for v in f.verts] for f in bm.faces], dtype=np.int64).reshape(-1, 3)
    bm.free()
    bpy.data.meshes.remove(me)
    return TM(V, F)


def _drop(*obs):
    for ob in obs:
        me = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def _offset(t_in, d, name="_off"):
    """Khoi kin co vao (d < 0) / no ra (d > 0) mot doan |d|: voxel -> day theo phap tuyen -> voxel lai. Phan mong hon
    2|d| (tai mu) tu bien mat khi co."""
    size = float((t_in.V.max(0) - t_in.V.min(0)).max())
    vx = max(abs(d) / 3.0, size / 160.0)
    ob = _obj(t_in, name)
    r1 = ob.modifiers.new("v1", "REMESH")
    r1.mode, r1.voxel_size = "VOXEL", vx
    m = ob.modifiers.new("off", "DISPLACE")
    m.direction, m.mid_level, m.strength = "NORMAL", 0.0, float(d)
    r2 = ob.modifiers.new("v2", "REMESH")
    r2.mode, r2.voxel_size = "VOXEL", vx
    return ob


def _lighter(t, n_ref):
    """Khoi voxel trung gian (mat trong vo, khong ai nhin) -> giam con ~0.6 so mat vo goc, van kin."""
    target = max(1500, int(0.6 * n_ref))
    if len(t.F) <= 1.3 * target:
        return t
    size = float((t.V.max(0) - t.V.min(0)).max())
    return bl.voxel_rebuild(t, voxel=size / 120.0, target_faces=target) or t


def _main(t):
    """Khoi lon nhat (theo the tich) - bo vun Boolean."""
    cs = t.split_components(min_faces=4)
    return max(cs, key=lambda c: abs(c.volume())) if cs else None


def _boolean(base, others, op):
    for i, b in enumerate(others):
        m = base.modifiers.new("%s%d" % (op, i), "BOOLEAN")
        m.operation, m.object, m.solver = op, b, "EXACT"


def find_neck(outer, inner, log=print):
    """Mat phang CO cua manh trong: tiet dien hep nhat ngay duoi day vo, theo truc tu tam manh trong toi tam vo."""
    cO, cI = outer.centroid(), inner.centroid()
    a = unit(cO - cI)
    pO = outer.V @ a
    low, h = float(pO.min()), float(pO.max() - pO.min())
    q = cI + a * (low - 0.15 * h - cI @ a)          # diem tren truc than, hoi duoi day vo
    pp, nn, area = inner.snap(q, a, 0.2 * h, q=q, grow=(1.0, 1.5), fallback="min")
    log("  co: diem %s, phap tuyen %s, tiet dien %.2f" % (np.round(pp, 2).tolist(), np.round(nn, 2).tolist(), area))
    return np.asarray(pp, float), unit(nn)


def contact(outer, inner, eps, sample=None):
    """Ti le mat vo ap vao (cach < eps) hoac lot SAT vao trong manh trong. Chi xet dau trong/ngoai khi gan (< 4 eps):
    o xa, diem gan nhat roi vao canh / dinh, phap tuyen tra ve sai dau -> manh nho canh mu (P02) bi tinh 'cham' nhieu
    hon ca than (gau 2026-10-07). sample: chi xet ~ngan ay mat (do nhanh khi do tim manh trong)."""
    bv = _bvh(inner)
    n = 0
    C = outer.face_centers()
    if sample and len(C) > sample:
        C = C[::int(np.ceil(len(C) / sample))]
    for c in C:
        loc, nrm, _, d = bv.find_nearest(Vector(c), 4 * eps)
        if loc is not None and (d < eps or (Vector(c) - loc).dot(nrm) < 0):
            n += 1
    return n / max(1, len(C))


def build(outer, inner, t=None, neck=None, cid_neck=901, cid_rim=902, model_size=10.0, log=print):
    """outer, inner: TM (toa do the gioi). Tra ve dict(shell=TM, core=TM, rest=[TM], neck=[p, n], t) hoac ValueError."""
    size_o = float((outer.V.max(0) - outer.V.min(0)).max())
    t = float(t) if t else T_REL * size_o
    k = contact(outer, inner, CONTACT_REL * model_size)
    if k <= 0:
        raise ValueError("vỏ không chạm mảnh bên trong")
    if k > 0.6:
        raise ValueError("vỏ gần như nằm lọt trong mảnh bên trong - chọn nhầm mảnh?")
    if neck is not None:
        pp, nn = np.asarray(neck[0], float), unit(neck[1])
    else:
        pp, nn = find_neck(outer, inner, log)
    # 1. cat manh trong o co
    parts = inner.plane_cut(pp, nn, cid_neck, mode="local", q=pp)
    if not parts:
        raise ValueError("không cắt được cổ của mảnh bên trong")
    top = [x for x in parts if (x.cap == cid_neck).any() and float((x.centroid() - pp) @ nn) > 0]
    rest = [x for x in parts if not any(x is y for y in top)]
    if not top or not rest:
        raise ValueError("không tìm thấy phần nằm dưới vỏ (mặt cắt cổ không tách được hai phía)")
    face = top[0]
    for x in top[1:]:
        face = face.merge_with(x)
    neck_c = face.face_centers()[face.cap == cid_neck].mean(0)   # plane_cut co the xe mat phang chut it
    made = []
    try:
        # 2. phan trong = (vo co vao t) U (tam day = vo giao mat no ra) U mat
        lo = _offset(outer, -t, "_lo")
        made.append(lo)
        eroded = _lighter(_evaluated_tm(lo), len(outer.F))  # giu rieng: mat vo nam tren khoi co vao = mat trong vo
        for k in SLAB_REL:
            fx, so = _offset(face, k * t, "_mat_no"), _obj(outer, "_vo_dac")
            made += [fx, so]
            _boolean(so, [fx], "INTERSECT")
            slab = _evaluated_tm(so)
            lo, sl, fo = _obj(eroded, "_lo2"), _obj(slab, "_day"), _obj(face, "_mat")
            made += [lo, sl, fo]
            _boolean(lo, [sl, fo], "UNION")
            core = _evaluated_tm(lo)
            # 3. vo = vo goc - phan trong
            co, so = _obj(core, "_trong"), _obj(outer, "_vo")
            made += [co, so]
            _boolean(so, [co], "DIFFERENCE")
            shell = _evaluated_tm(so)
            core, shell = _main(core), _main(shell)          # vun boolean con sot -> bo
            if core is not None and shell is not None and core.is_closed() and shell.is_closed():
                break
            log("  (tam day %.2f t: vo / phan trong ho - thu day hon)" % k)
    finally:
        _drop(*made)
    if core is None or shell is None:
        raise ValueError("không dựng được vỏ / phần bên trong")
    for what, x in (("phần bên trong", core), ("vỏ", shell)):
        if not x.is_closed():
            log("  (%s ho - dung lai bang voxel)" % what)
    core = core if core.is_closed() else (bl.voxel_rebuild(core) or core)
    shell = shell if shell.is_closed() else (bl.voxel_rebuild(shell) or shell)
    # ma nhat cat: nap co cua phan trong bo cong cung than; vanh mieng vo = mat KHONG nam tren be mat vo goc cung khong nam
    # tren khoi co vao (tuc la vach tam day / mat) -> bo cong mep mieng vo
    eps = 2e-3 * model_size
    on = (np.abs((core.face_centers() - neck_c) @ nn) < eps) & (np.abs(core.face_normals() @ nn) > 0.98)
    core.cap = np.where(on, cid_neck, -1)
    bo, be = _bvh(outer), _bvh(eroded)
    rim = np.array([(bo.find_nearest(Vector(c))[3] or 9) > eps and (be.find_nearest(Vector(c))[3] or 9) > eps
                    for c in shell.face_centers()], bool)
    shell.cap = np.where(rim, cid_rim, -1)
    log("  vo: %d mat, day %.2f, vanh %d mat; phan trong: %d mat (nap co %d); than: %d manh"
        % (len(shell.F), t, int(rim.sum()), len(core.F), int(on.sum()), len(rest)))
    return dict(shell=shell, core=core, rest=rest, neck=[pp.tolist(), nn.tolist()], t=t)


def op_shell(R, o):
    """Thao tac plan.json (plan.Run): thay manh vo bang VO RONG, manh trong bang [PHAN TRONG] + [than]."""
    from .plan import Piece
    po, pi = R.find_surface(o["outer"]), R.find_surface(o["inner"])
    if po is None or pi is None or po is pi:
        raise ValueError("shell: không tìm thấy hai mảnh vỏ / bên trong")
    R.say("  vo: manh %d mat tam %s; trong: manh %d mat tam %s" % (
        len(po.tm.F), np.round(po.tm.centroid(), 2).tolist(), len(pi.tm.F), np.round(pi.tm.centroid(), 2).tolist()))
    cn, cr = R.next_cut(), R.next_cut()
    res = build(po.tm, pi.tm, t=o.get("t"), neck=o.get("neck"), cid_neck=cn, cid_rim=cr,
                model_size=R.model_size, log=R.say)

    def main_col(t):
        ok = t.col >= 0
        return int(np.bincount(t.col[ok]).argmax()) if ok.any() else -1
    co, ci = main_col(po.tm), main_col(pi.tm)
    res["shell"].col = np.full(len(res["shell"].F), co, np.int64)
    res["core"].col = np.full(len(res["core"].F), ci, np.int64)
    for x in res["rest"]:
        x.col = np.where(x.col >= 0, x.col, ci)
    ps, pc = Piece(res["shell"]), Piece(res["core"])
    pr = [Piece(x) for x in res["rest"]]
    R.replace(po, [ps])
    R.replace(pi, [pc] + pr)
    o.setdefault("neck", res["neck"])
    o.setdefault("t", res["t"])
    R.say("  shell: vo + phan trong + %d manh than" % len(pr))
    return dict(shell=ps, core=pc, rest=pr)
