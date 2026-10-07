"""BO CONG MEP CAT bang HINH HOC MOI (fillet kieu CAD) - nguoi dung 2026-10-05: "vet cat van qua xau... co the cat bot
va tao them mesh". Voi tung mat cat (ma nap cid) cua manh:
  1. cat bo mot lop mong sau w sat mat cat (plane_cut song song, cuc bo) -> vong mep L nam tren be mat that;
  2. dung dai cong 1/4 elip `segs` bac tu L: P(theta) = L + C*w*sin(theta) + in*r*(1 - cos(theta)) (C phap tuyen nap
     huong ra, in = huong vao trong nap, r <= w kep theo be rong nap tai cho);
  3. bit lai nap nho hon o mat phang cat cu (tessellate_polygon, co lo).
Khong dung lai luoi cu (luoi Tripo thua -> lan dinh cu gay mat). Moi buoc hong thi giu nguyen manh (an toan)."""
import math
import numpy as np
from .tm import TM, unit

try:
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon
    from mathutils.kdtree import KDTree
except ImportError:
    Vector = tessellate_polygon = KDTree = None

FILLET_ID = 7000          # ma tam cho nhat cat lop mong


def _refine(t, C, d0, w, passes=4):
    """Chia nho canh BE MAT THAT dai > 1.5 w cat qua dai do sau [0, 2.5 w] duoi mat cat (tam giac manh sat mep do nhat cat
    truoc de lai -> mat phang lop mong cat qua sat dinh, plane_cut tu choi). Giu mau / ma nap theo mat."""
    import bmesh
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in t.V.tolist()]
    lk = bm.faces.layers.int.new("k")
    lc = bm.faces.layers.int.new("c")
    for f, k, c in zip(t.F.tolist(), t.cap.tolist(), t.col.tolist()):
        try:
            ff = bm.faces.new([vs[i] for i in f])
        except ValueError:
            bm.free()
            return t
        ff[lk], ff[lc] = int(k), int(c)
    for _ in range(passes):
        cand = []
        for e in bm.edges:
            if e.calc_length() <= 2.5 * w or not any(f[lk] < 0 for f in e.link_faces):
                continue
            da = d0 - float(np.dot(e.verts[0].co, C))
            db = d0 - float(np.dot(e.verts[1].co, C))
            lo, hi = min(da, db), max(da, db)
            if hi >= -1e-6 and lo <= 1.6 * w:
                cand.append(e)
        if not cand:
            break
        bmesh.ops.subdivide_edges(bm, edges=cand, cuts=1, use_grid_fill=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.verts.index_update()
    V = np.array([v.co[:] for v in bm.verts], dtype=np.float64)
    F = np.array([[v.index for v in f.verts] for f in bm.faces], dtype=np.int64)
    K = np.array([f[lk] for f in bm.faces], dtype=np.int64)
    Cc = np.array([f[lc] for f in bm.faces], dtype=np.int64)
    bm.free()
    out = TM(V, F, Cc, K)
    return out if out.is_closed() else t


def _loops(F, region):
    """Cac vong bien CO HUONG cua tap mat `region` (canh ma canh nguoc khong thuoc region). Tra ve list list dinh."""
    de = {}
    inner = set()
    for f in F[region]:
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        for x, y in ((a, b), (b, c), (c, a)):
            inner.add((x, y))
    nxt = {}
    for (x, y) in inner:
        if (y, x) not in inner:
            if x in nxt:                     # dinh khong da tap tren vien -> bo
                return None
            nxt[x] = y
    loops, seen = [], set()
    for s in list(nxt):
        if s in seen:
            continue
        lp, v = [], s
        while v not in seen:
            seen.add(v)
            lp.append(v)
            v = nxt.get(v)
            if v is None:
                return None
        if v != s or len(lp) < 3:
            return None
        loops.append(lp)
    return loops


def _fillet_one(t, cid, w, segs):
    capf = np.where(t.cap == cid)[0]
    if not len(capf):
        return t, "khong nap"
    A = t.face_areas()
    N = t.face_normals()
    Cn = (N[capf] * 1.0).sum(0)
    if np.linalg.norm(Cn) < 1e-12:
        return t, "phap tuyen nap"
    C = unit(Cn)
    d0 = float(np.mean(t.V[np.unique(t.F[capf].ravel())] @ C))
    cap_area = float(A[capf].sum())
    t = _refine(t, C, d0, w)
    capf = np.where(t.cap == cid)[0]
    A = t.face_areas()
    big = capf[int(np.argmax(A[capf]))]
    q = t.face_centers()[big] - C * w
    p_cut = q - C * (float(q @ C) - (d0 - w))
    sz = float(t.size) or 1.0
    res = t.plane_cut(p_cut, C, FILLET_ID, mode="local", q=q, grow=True, shift_rel=0.08 * w / sz, attempts=7)
    if not res or len(res) < 2:
        return t, "cat lop mong hong"
    res = sorted(res, key=lambda r: -abs(r.volume()))
    k, slab = res[0], res[1:]
    kc = float(k.centroid() @ C)
    if any(float(r.centroid() @ C) < kc for r in slab):
        return t, "lop mong khong tach gon"
    vs = sum(abs(r.volume()) for r in slab)
    if vs > 2.5 * cap_area * w + 1e-9:
        return t, "lop mong qua day (cat vao hinh, %.3f > %.3f)" % (vs, 2.5 * cap_area * w)
    reg = np.where(k.cap == FILLET_ID)[0]
    loops = _loops(k.F, reg)
    if not loops:
        return t, "vong mep loi"
    V = k.V
    dcut = float(np.mean(V[np.unique(k.F[reg].ravel())] @ C))
    hz = max(1e-4, d0 - dcut)                          # do cao dai bo = do sau that cua nhat cat lop mong
    # be rong nap tai cho -> ban kinh ngang r_i
    allv = [v for lp in loops for v in lp]
    kd = KDTree(len(allv))
    pos_in = {}
    for i, v in enumerate(allv):
        kd.insert(Vector(V[v]), i)
    kd.balance()
    li_of = {}
    for li, lp in enumerate(loops):
        for j, v in enumerate(lp):
            li_of[v] = (li, j, len(lp))
    newV = list(V)
    newF = [f for i, f in enumerate(k.F) if k.cap[i] != FILLET_ID]
    newC = [c for i, c in enumerate(k.col) if k.cap[i] != FILLET_ID]
    newK = [c for i, c in enumerate(k.cap) if k.cap[i] != FILLET_ID]
    # mau cua dai bo = mau mat that ke dinh mep
    vcol = {}
    for i, f in enumerate(k.F):
        if k.cap[i] < 0 and k.col[i] >= 0:
            for v in f:
                vcol.setdefault(int(v), int(k.col[i]))
    rings_all = []
    for li, lp in enumerate(loops):
        n = len(lp)
        P = V[lp]
        ins, rad = [], []
        for j in range(n):
            e = P[(j + 1) % n] - P[j - 1]
            iv = np.cross(C, e)
            iv = iv / (np.linalg.norm(iv) or 1.0)
            # be rong: dinh mep gan nhat khong thuoc lan can cung vong
            best = None
            for co, ix, dist in kd.find_n(Vector(P[j]), 16):
                v2 = allv[ix]
                l2, j2, n2 = li_of[v2]
                if l2 == li and min(abs(j2 - j), n2 - abs(j2 - j)) <= 4:
                    continue
                best = dist if best is None else min(best, dist)
            r = w if best is None else min(w, 0.4 * best)
            ins.append(iv)
            rad.append(r)
        ins = np.array(ins)
        rad = np.array(rad)
        for _ in range(3):                                   # lam min huong + ban kinh doc vong
            ins = (np.roll(ins, 1, 0) + 2 * ins + np.roll(ins, -1, 0)) / 4.0
            ins /= np.maximum(np.linalg.norm(ins, axis=1, keepdims=True), 1e-12)
            rad = np.minimum(rad, (np.roll(rad, 1) + 2 * rad + np.roll(rad, -1)) / 4.0 + 1e-9)
        rings = [list(lp)]
        for s in range(1, segs + 1):
            th = 0.5 * math.pi * s / segs
            ids = []
            for j in range(n):
                newV.append(P[j] + C * hz * math.sin(th) + ins[j] * rad[j] * (1.0 - math.cos(th)))
                ids.append(len(newV) - 1)
            rings.append(ids)
        for s in range(segs):
            th = 0.5 * math.pi * (s + 0.5) / segs
            for j in range(n):
                a, b = rings[s][j], rings[s][(j + 1) % n]
                c, d = rings[s + 1][(j + 1) % n], rings[s + 1][j]
                nout = -ins[j] * math.cos(th) + C * math.sin(th)
                for tri in ((a, b, c), (a, c, d)):
                    x, y, z = (np.asarray(newV[i]) for i in tri)
                    if np.cross(y - x, z - x) @ nout < 0:
                        tri = (tri[0], tri[2], tri[1])
                    newF.append(tri)
                    newC.append(vcol.get(int(lp[j]), -1))
                    newK.append(-1)
        rings_all.append(rings[-1])
    # nap moi o mat phang cu: tessellate (co lo)
    u = unit(np.cross(C, [1.0, 0, 0] if abs(C[0]) < 0.9 else [0, 1.0, 0]))
    vv = np.cross(C, u)
    polys = [[Vector((float(newV[i] @ u), float(newV[i] @ vv), 0.0)) for i in rg] for rg in rings_all]
    flat = [i for rg in rings_all for i in rg]
    tris = tessellate_polygon(polys)
    if not tris:
        return t, "bit nap hong"
    for a, b, c in tris:
        tri = (flat[a], flat[b], flat[c])
        x, y, z = (np.asarray(newV[i]) for i in tri)
        if np.cross(y - x, z - x) @ C < 0:
            tri = (tri[0], tri[2], tri[1])
        newF.append(tri)
        newC.append(-1)
        newK.append(cid)
    out = TM(np.array(newV, dtype=np.float64), np.array(newF, dtype=np.int64),
             np.array(newC, dtype=np.int64), np.array(newK, dtype=np.int64))
    if not out.is_closed():
        return t, "khong kin sau bo"
    return out, None


def fillet_geo(t, w, segs=4, ids=None, log=None):
    """Bo cong moi mat cat cua TM t (hoac chi cac ma `ids`). Tra ve TM moi (giu nguyen phan nao hong)."""
    if log is None:
        log = print
    if w <= 0 or tessellate_polygon is None or not (t.cap >= 0).any():
        return t
    size = float((t.V.max(0) - t.V.min(0)).min())
    w = min(float(w), 0.25 * size)
    if w <= 1e-4:
        return t
    cids = sorted(set(int(c) for c in np.unique(t.cap) if c >= 0 and c != FILLET_ID))
    if ids is not None:
        cids = [c for c in cids if c in set(ids)]
    for cid in cids:
        try:
            t2, why = _fillet_one(t, cid, w, segs)
        except Exception as e:                       # mot mat hong khong lam hong ca manh
            t2, why = t, "loi %s" % e
        if why and log is not None:
            log("  (bo cong nap %d bo qua: %s)" % (cid, why))
        t = t2
    return t


def fillet(t, w, log=None, face_mult=3.0, keep_surface=True, band=1.6):
    """BO CONG MAC DINH (2026-10-05, thay fillet_geo hay that bai o vo mong / cho hep -> con nep gap, mep vuong): dung lai
    manh bang VOXEL (o = max(w/3, co/140), <= canh ngan/8) roi LAM TRON (Laplace co trong so, giam dan theo khoang cach
    toi mat cat cu, trong 1.6 w) moi dinh gan mat cat -> moi mep cat thanh ranh tron, ca nep gap. Giam mat ve ~face_mult x
    so mat goc (giu kin). Mau theo mat goc gan nhat; khong con nap (khong canh sac)."""
    import bpy, bmesh
    from mathutils.bvhtree import BVHTree
    from . import bl
    if w <= 0 or not (t.cap >= 0).any():
        return t
    dims = t.V.max(0) - t.V.min(0)
    w = min(float(w), 0.25 * float(dims.min()))
    if w <= 1e-4:
        return t
    size = float(dims.max())
    vs = min(max(w / 3.5, size / 170.0), float(dims.min()) / 8.0)
    made = []
    try:
        me = bpy.data.meshes.new("_vf")
        me.from_pydata(t.V.tolist(), [], t.F.tolist())
        me.update()
        ob = bpy.data.objects.new("_vf", me)
        bpy.context.scene.collection.objects.link(ob)
        made.append(ob)
        r = ob.modifiers.new("r", "REMESH")
        r.mode = "VOXEL"
        r.voxel_size = vs
        dg = bpy.context.evaluated_depsgraph_get()
        m2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        bm = bmesh.new()
        bm.from_mesh(m2)
        bpy.data.meshes.remove(m2)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        capf = np.where(t.cap >= 0)[0]
        cb = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in t.F[f]) for f in capf],
                                  all_triangles=True)
        sel, wt, dcap = [], {}, {}
        for v in bm.verts:
            hit = cb.find_nearest(v.co)
            dcap[v] = hit[3] if hit[3] is not None else 1e9
            if dcap[v] < band * w:
                sel.append(v)
                wt[v] = 1.0 - dcap[v] / (band * w)
        nb = {v: [e.other_vert(v) for e in v.link_edges] for v in sel}
        n_it = max(4, int(round((w / vs) ** 2 * 1.2)))
        for _ in range(n_it):
            new = {}
            for v in sel:
                if not nb[v]:
                    continue
                avg = sum((o.co for o in nb[v]), Vector()) / len(nb[v])
                new[v] = v.co + (avg - v.co) * 0.6 * wt[v]
            for v, c in new.items():
                v.co = c
        if keep_surface:
            # BOT "SUA" (2026-10-05: voxel lam ca manh mem, gon): dinh XA mat cat ep ve DUNG be mat goc Tripo; trong dai
            # bo pha dan (smoothstep) giua be mat goc va ban da lam tron -> chi mep cat tron, phan con lai giu net.
            sidef = np.where(t.cap < 0)[0]
            if len(sidef):
                sb = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in t.F[f]) for f in sidef],
                                          all_triangles=True)
                for v in bm.verts:
                    x = min(1.0, dcap[v] / (band * w))
                    b = x * x * (3 - 2 * x)               # 0 sat mep (giu ban tron) -> 1 xa mep (ve be mat goc)
                    if b <= 1e-3:
                        continue
                    hit = sb.find_nearest(v.co)
                    if hit[0] is not None:
                        v.co = v.co.lerp(hit[0], b)
        m3 = bpy.data.meshes.new("_vf3")
        bm.to_mesh(m3)
        bm.free()
        ob3 = bpy.data.objects.new("_vf3", m3)
        bpy.context.scene.collection.objects.link(ob3)
        made.append(ob3)
        full = bl.tm_from_mesh(m3)
        t2 = full
        target = max(1200, min(face_mult * len(t.F), 1.3 * len(t.F) + 3000))   # khoi lon: khong nhan 3 so mat
        if len(full.F) > target:
            d = ob3.modifiers.new("d", "DECIMATE")
            d.decimate_type = "COLLAPSE"
            d.use_collapse_triangulate = True
            for k in (1.0, 1.4, 2.0):
                d.ratio = min(1.0, k * target / len(full.F))
                dg = bpy.context.evaluated_depsgraph_get()
                m4 = bpy.data.meshes.new_from_object(ob3.evaluated_get(dg))
                tt = bl.tm_from_mesh(m4)
                bpy.data.meshes.remove(m4)
                if tt.is_closed():
                    t2 = tt
                    break
    except Exception as e:
        if log:
            log("  (bo cong voxel loi: %s - giu manh)" % e)
        return t
    finally:
        for o in made:
            m_ = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if m_ is not None and m_.users == 0:
                bpy.data.meshes.remove(m_)
    if not len(t2.F) or not t2.is_closed():
        if log:
            log("  (bo cong voxel: khong kin - giu manh)")
        return t
    comps = t2.split_components(min_faces=1)
    if len(comps) > 1:              # vun 2-12 mat, the tich 0 o mep cat (tach sau 2026-10-06: dau / mom gau) -> bo
        v0 = max(abs(c.volume()) for c in comps) or 1e-12
        keep = [c for c in comps if abs(c.volume()) >= 0.002 * v0 and len(c.F) >= 20]
        if keep and len(keep) < len(comps):
            off = np.cumsum([0] + [len(c.V) for c in keep[:-1]])
            t2 = TM(np.concatenate([c.V for c in keep]), np.concatenate([c.F + o for c, o in zip(keep, off)]))
    kd = KDTree(len(t.F))
    for i, c in enumerate(t.face_centers()):
        kd.insert(Vector(c), i)
    kd.balance()
    idx = np.array([kd.find(Vector(c))[1] for c in t2.face_centers()], dtype=np.int64)
    t2.col = np.where(t.cap[idx] >= 0, -1, t.col[idx])
    t2.cap = np.full(len(t2.F), -1, np.int64)
    return t2
