"""Cau noi TM <-> Blender, material bang mau. Chay trong Blender."""
import numpy as np
import bpy, bmesh
from mathutils import Vector
from . import std
from .tm import TM


def tm_from_mesh(me, matrix=None):
    """Mesh Blender -> TM tam giac (khong mang mau)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    if matrix is not None:
        bm.transform(matrix)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    V = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3)
    F = np.array([[v.index for v in f.verts] for f in bm.faces], dtype=np.int64).reshape(-1, 3)
    bm.free()
    return TM(V, F)


def mesh_from_tm(t, name, flat_caps=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(t.V.tolist(), [], t.F.tolist())
    me.update()
    a = me.attributes.new("wc_cap", "INT", "FACE")          # ma nhat cat cua mat nap (-1 = be mat that) - de bo cong mep
    a.data.foreach_set("value", np.asarray(t.cap, dtype=np.int32))
    sm = np.ones(len(t.F), dtype=bool)
    me.polygons.foreach_set("use_smooth", sm)
    if flat_caps and (t.cap >= 0).any():
        # canh giua nap phang va mat that: sac (normal tach) -> nap phang, mat cong van muot
        E, FE = t.edges()
        ef, cnt = t.edge_faces()
        isc = t.cap >= 0
        sharp = np.zeros(len(E), dtype=bool)
        ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
        sharp[ok] = isc[ef[ok, 0]] != isc[ef[ok, 1]]
        # cung la canh giua hai nap khac nhat cat (goc mui cam)
        kk = t.cap
        sharp[ok] |= isc[ef[ok, 0]] & isc[ef[ok, 1]] & (kk[ef[ok, 0]] != kk[ef[ok, 1]])
        key = {(int(a), int(b)): i for i, (a, b) in enumerate(E)}
        attr = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
        vals = np.zeros(len(me.edges), dtype=bool)
        ev = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", ev)
        ev = np.sort(ev.reshape(-1, 2), axis=1)
        for j, (a, b) in enumerate(ev):
            i = key.get((int(a), int(b)))
            if i is not None and sharp[i]:
                vals[j] = True
        attr.data.foreach_set("value", vals)
    return me


def round_seams(ob, width, segments=None, refine=True):
    """BO CONG MEP CAT MUOT (nguoi dung 2026-10-05: "van can bo cong nhung vet cat phai cong muot"): (1) chia nho luoi
    trong dai 2.5 w quanh mep cat toi canh <= w/2 (luoi Tripo thua -> lan truc tiep thi tam giac to bi be gap, meo);
    (2) lan mep (_roll_seams); (3) lam min Laplace dai bo (het rang cua, gay khuc). Tra ve so dinh mep."""
    me = ob.data
    if width <= 0 or "wc_cap" not in me.attributes or not len(me.polygons):
        return 0
    dims = np.array(ob.dimensions)
    w = min(float(width), 0.2 * float(dims.min()))
    if w <= 1e-4:
        return 0
    if refine:
        _refine_near_rim(me, w)
    n = _roll_seams(ob, width)
    if n:
        _smooth_band(me, w)
    return n


def _rim_info(bm, lay):
    rim = set()
    for e in bm.edges:
        if len(e.link_faces) == 2 and ((e.link_faces[0][lay] >= 0) != (e.link_faces[1][lay] >= 0)):
            rim.update(e.verts)
    return rim


def _band_verts(bm, rim, radius):
    from mathutils.kdtree import KDTree
    if not rim:
        return set()
    kd = KDTree(len(rim))
    for i, v in enumerate(rim):
        kd.insert(v.co, i)
    kd.balance()
    return {v for v in bm.verts if kd.find(v.co)[2] < radius}


def _refine_near_rim(me, w, passes=3):
    """Chia doi cac canh dai > w/2 nam trong dai 2.5 w quanh mep cat (giu thuoc tinh wc_cap cua mat)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.faces.layers.int.get("wc_cap")
    if lay is None:
        bm.free()
        return
    for _ in range(passes):
        band = _band_verts(bm, _rim_info(bm, lay), 2.5 * w)
        long_e = [e for e in bm.edges if e.verts[0] in band and e.verts[1] in band and e.calc_length() > 0.5 * w
                  and any(f[lay] < 0 for f in e.link_faces)]     # chi be mat that sat mep, khong chia mat nap
        if not long_e:
            break
        bmesh.ops.subdivide_edges(bm, edges=long_e, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(me)
    bm.free()
    me.update()


def _smooth_band(me, w, iters=4):
    """Lam min Laplace dai bo: dinh BE MAT THAT trong dai 1.5 w, chi trung binh voi hang xom qua canh cua mat that
    (khong lay dinh mat nap - nap Boolean / CDT la tam giac rat dai, keo mep vao giua -> thung, 2026-10-05). Dinh mep chi
    trung binh voi dinh mep ke ben (giu duong mep tron deu)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.faces.layers.int.get("wc_cap")
    rim = _rim_info(bm, lay)
    band = [v for v in _band_verts(bm, rim, 1.5 * w) if any(f[lay] < 0 for f in v.link_faces)]
    nb = {}
    for v in band:
        ns = []
        for e in v.link_edges:
            if not any(f[lay] < 0 for f in e.link_faces):
                continue
            o = e.other_vert(v)
            if v in rim and o not in rim:
                continue
            ns.append(o)
        if len(ns) >= 2:
            nb[v] = ns
    for _ in range(iters):
        new = {v: v.co * 0.5 + sum((o.co for o in ns), v.co * 0) * (0.5 / len(ns)) for v, ns in nb.items()}
        for v, c in new.items():
            v.co = c
    bm.to_mesh(me)
    bm.free()
    me.update()


def _roll_seams(ob, width, segments=None):
    """BO CONG MEP CAT bang cach LAN MEP (nguoi dung 2026-10-02 gui anh model mau: manh phong nhu goi, duong noi lom
    thanh ranh tron): dinh cua BE MAT THAT cach mep cat s < w duoc keo lui vao trong (nguoc phap tuyen) theo cung
    tron d(s) = w - sqrt(w^2 - (w - s)^2): o mep lui dung w (nam tren mat nap), toi s = w thi bang 0. Mat nap (ap vao
    manh ben canh, khuat) co lai tuong ung. Khong them mat, khong doi topo. (bmesh bevel tu kep do rong theo canh
    luoi sat mep ~0.05 -> xin 0.12 hay 0.25 deu nhu nhau.) w tu nho lai voi manh mong (<= 1/5 canh ngan nhat).
    Tra ve so dinh mep."""
    me = ob.data
    if width <= 0 or "wc_cap" not in me.attributes or not len(me.polygons):
        return 0
    nf, nv = len(me.polygons), len(me.vertices)
    cap = np.empty(nf, dtype=np.int32)
    me.attributes["wc_cap"].data.foreach_get("value", cap)
    if not (cap >= 0).any():
        return 0
    V = np.empty(nv * 3)
    me.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    me.calc_loop_triangles()
    T = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", T)
    T = T.reshape(-1, 3)
    TP = np.empty(len(me.loop_triangles), dtype=np.int64)
    me.loop_triangles.foreach_get("polygon_index", TP)
    is_cap = cap[TP] >= 0
    on_cap = np.zeros(nv, bool)
    on_side = np.zeros(nv, bool)
    on_cap[T[is_cap].ravel()] = True
    on_side[T[~is_cap].ravel()] = True
    rim = np.where(on_cap & on_side)[0]
    if not len(rim):
        return 0
    dims = V.max(0) - V.min(0)
    w = min(float(width), 0.2 * float(dims.min()))
    if w <= 1e-4:
        return 0
    # phap tuyen cua BE MAT THAT (khong tron voi nap)
    a, b, c = V[T[~is_cap, 0]], V[T[~is_cap, 1]], V[T[~is_cap, 2]]
    fn = np.cross(b - a, c - a)
    N = np.zeros_like(V)
    A = np.zeros(len(V))
    fa = np.linalg.norm(fn, axis=1)
    for j in range(3):
        np.add.at(N, T[~is_cap, j], fn)
        np.add.at(A, T[~is_cap, j], fa)
    # vo mong gap lai o mep (mat truoc + mat sau chung dinh): phap tuyen triet tieu -> huong keo lung tung -> GAI.
    # Dinh co |tong phap tuyen| < 0.6 tong dien tich = huong khong ro -> khong keo
    clear = np.linalg.norm(N, axis=1) >= 0.6 * np.maximum(A, 1e-12)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    N[~clear] = 0.0
    from mathutils.kdtree import KDTree
    from mathutils import Vector
    # phap tuyen NAP tai dinh mep + do sac cua goc: goc vuong (N . C = 0) bo du; mat cat luot gan song song be mat
    # (|N . C| >= 0.75) von da thoai -> khong bo (truoc: keo theo N vuong goc mat cat -> xe nap thanh GAI, xe may 2026-10-02)
    ac, bc, cc = V[T[is_cap, 0]], V[T[is_cap, 1]], V[T[is_cap, 2]]
    cn = np.cross(bc - ac, cc - ac)
    C = np.zeros_like(V)
    for j in range(3):
        np.add.at(C, T[is_cap, j], cn)
    C /= np.maximum(np.linalg.norm(C, axis=1, keepdims=True), 1e-12)
    dotNC = np.abs(np.einsum("ij,ij->i", N, C))
    fac = np.clip((0.75 - dotNC) / 0.75, 0.0, 1.0)
    fac[~clear] = 0.0
    kd = KDTree(len(rim))
    for i, v in enumerate(rim):
        kd.insert(Vector(V[v]), i)
    kd.balance()
    side = np.where(on_side)[0]
    found = [kd.find(Vector(V[v])) for v in side]
    sdist = np.array([f[2] for f in found])
    nearest = np.array([rim[f[1]] for f in found], dtype=np.int64)
    near = sdist < w
    s_ = sdist[near]
    d = (w - np.sqrt(np.maximum(0.0, w * w - (w - s_) ** 2))) * fac[nearest[near]]
    idx = side[near]
    D = -N[idx].copy()
    isrim = on_cap[idx]
    if isrim.any():                         # dinh mep: chi truot TRONG mat phang cat (vao trong nap)
        P = D[isrim] - np.einsum("ij,ij->i", D[isrim], C[idx[isrim]])[:, None] * C[idx[isrim]]
        ln = np.linalg.norm(P, axis=1, keepdims=True)
        D[isrim] = np.where(ln > 0.3, P / np.maximum(ln, 1e-12), 0.0)
    # VO MONG (kinh chan gio Tripo): keo vao trong qua do day thi hai mat cham nhau -> nhan, gai. Ban tia vao trong
    # do do day that tai tung dinh, keo toi da 35% do day
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([Vector(v) for v in V], [tuple(int(i) for i in f) for f in T], all_triangles=True)
    eps = 1e-4 * float(dims.max())
    for k, v in enumerate(idx):
        if d[k] <= 0 or float(D[k] @ D[k]) < 0.25:
            d[k] = 0.0
            continue
        o = V[v] + D[k] * eps - (C[v] * 10 * eps if on_cap[v] else 0.0)   # dinh mep: lui vao trong khoi, khong cham nap
        hit = bvh.ray_cast(Vector(o), Vector(D[k]), 4.0 * w)
        if hit[0] is not None:
            d[k] = min(d[k], 0.35 * float(hit[3]))
    V[idx] += D * d[:, None]
    me.vertices.foreach_set("co", V.ravel())
    me.update()
    return int(len(rim))


def voxel_rebuild(t, voxel=None, target_faces=None):
    """TM -> dung lai bang VOXEL REMESH (vo kin, het vat mong / mat chong / lo), giam ve ~target_faces mat; mau va ma
    nap theo mat goc gan nhat. voxel mac dinh = co / 80. None neu khong ra khoi kin."""
    from mathutils.kdtree import KDTree
    size = float((t.V.max(0) - t.V.min(0)).max()) or 1.0
    vs = float(voxel) if voxel else size / 80.0
    target = int(target_faces or max(200, 1.3 * len(t.F)))
    made, t2 = [], None
    try:
        me = bpy.data.meshes.new("_vx")
        me.from_pydata(t.V.tolist(), [], t.F.tolist())
        me.update()
        ob = bpy.data.objects.new("_vx", me)
        bpy.context.scene.collection.objects.link(ob)
        made.append(ob)
        r = ob.modifiers.new("vx", "REMESH")
        r.mode = "VOXEL"
        r.voxel_size = max(vs, 1e-3)
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob2 = bpy.data.objects.new("_vx2", me2)
        bpy.context.scene.collection.objects.link(ob2)
        made.append(ob2)
        n_now = 2 * len(me2.polygons)
        t_full = tm_from_mesh(me2)
        t2 = t_full
        if n_now > target:
            d = ob2.modifiers.new("dc", "DECIMATE")
            d.decimate_type = "COLLAPSE"
            d.use_collapse_triangulate = True
            t2 = t_full                            # giam mat lam ho o moi ti le -> dung ban chua giam (van kin)
            for k in (1.0, 1.3, 1.7, 2.5, 4.0):
                d.ratio = min(1.0, k * target / n_now)
                dg = bpy.context.evaluated_depsgraph_get()
                me3 = bpy.data.meshes.new_from_object(ob2.evaluated_get(dg))
                tt = tm_from_mesh(me3)
                bpy.data.meshes.remove(me3)
                if tt.is_closed():
                    t2 = tt
                    break
    except Exception as e:
        print("[mesh lai] loi: %s" % e)
        t2 = None
    finally:
        for o in made:
            m = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if m is not None and m.users == 0:
                bpy.data.meshes.remove(m)
    if t2 is None or not len(t2.F) or not t2.is_closed():
        return None
    comps = t2.split_components()                  # bo mau vun < 1% dien tich (voxel de lai hat li ti)
    if len(comps) > 1:
        tot = sum(float(c.face_areas().sum()) for c in comps) or 1.0
        keep = [c for c in comps if float(c.face_areas().sum()) >= 0.01 * tot]
        V, F, off = [], [], 0
        for c in keep:
            V.append(c.V)
            F.append(c.F + off)
            off += len(c.V)
        t2 = TM(np.concatenate(V), np.concatenate(F))
    kd = KDTree(len(t.F))
    for i, c in enumerate(t.face_centers()):
        kd.insert(Vector(c), i)
    kd.balance()
    idx = np.array([kd.find(Vector(c))[1] for c in t2.face_centers()], dtype=np.int64)
    t2.col = np.asarray(t.col)[idx].copy()
    t2.cap = np.asarray(t.cap)[idx].copy()
    return t2


_MATS = {}


def palette_material(mat_name, rgb_lin=None):
    """Material dung TEN bang mau (Unity tim material theo ten) va dung MAU FBX nhu model mau cua nguoi dung
    (BearArt: Base Color = mau bang trong FBX, Roughness 0.553) - dat canh model goc trong Blender khong lech mau."""
    m = bpy.data.materials.get(mat_name)
    if m is None:
        m = bpy.data.materials.new(mat_name)
        m.use_nodes = True
    c = rgb_lin if rgb_lin is not None else std.PALETTE_BY_MAT.get(mat_name) or std.nominal_lin(mat_name)
    p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.node_tree else None
    if p is not None:
        p.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
        p.inputs["Roughness"].default_value = 0.553
    m.diffuse_color = (c[0], c[1], c[2], 1.0)
    return m


def flat_material(name, rgb):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        p.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        p.inputs["Roughness"].default_value = 0.8
        m.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
    return m


def object_from_tm(t, name, names=None, coll=None, mat=None, per_face=True):
    """Tao object. per_face: material theo mau tung mat (de xem vung mau); khong thi mot material `mat`."""
    me = mesh_from_tm(t, name)
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    elif per_face and names is not None:
        used = sorted(set(int(c) for c in t.col if c >= 0))
        slot = {}
        for c in used:
            me.materials.append(palette_material(names[c]))
            slot[c] = len(me.materials) - 1
        if not used:
            me.materials.append(flat_material("_gray", (0.5, 0.5, 0.5)))
        # mat nap (-1) lay mau mat ke -> de mau nhat cua manh
        fill = max(used, key=lambda c: (t.col == c).sum()) if used else None
        mi = np.array([slot.get(int(c), slot.get(fill, 0)) for c in t.col], dtype=np.int64)
        me.polygons.foreach_set("material_index", mi)
    me.update()
    return ob
