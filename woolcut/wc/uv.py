"""UV kieu bo goc: moi manh 1-3 dao UV, van len chay DOC chieu dai bo phan, mat do 2.148 o/m.

Do 2026-10-02 tren BearArt / SteernSquid / Totoro / Chicken: moi mesh 1-3 dao, mat do 2.15-2.34 o/m; nhin len
that: van chay doc chan gia ve, vong quanh vong tham. Chieu hop (uv_box cu) bam moi manh thanh ~15 dao, van doi
huong va dut o moi goc gay.

Cach lam tung manh (luoi da o kich thuoc cuoi):
  1. duong noi (seam) = canh sac (mep nap phang, do buoc cat danh dau) -> moi nap phang mot dao;
  2. phan mat cong phai la dia de trai phang: ong (2 vong bien) / khoi kin (0 bien) thi rach them duong ngan nhat
     noi cac vong bien (hoac noi hai dau khoi), uu tien phia SAU model (+Y) cho khuat;
  3. bpy.ops.uv.unwrap (Minimum Stretch neu co, khong thi Angle Based);
  4. tung dao: co gian ve dung mat do, xoay de truc dai nhat cua manh chay theo V (van len doc), khoi tron
     thi theo truc dung Z."""
import math, heapq, collections
import numpy as np
import bpy, bmesh
from mathutils import Vector
from . import std


def _islands(bm):
    """Dao = thanh phan lien thong cua mat qua canh KHONG phai seam."""
    lab = {}
    k = 0
    for f in bm.faces:
        if f in lab:
            continue
        st = [f]
        lab[f] = k
        while st:
            g = st.pop()
            for e in g.edges:
                if e.seam:
                    continue
                for h in e.link_faces:
                    if h not in lab:
                        lab[h] = k
                        st.append(h)
        k += 1
    return lab, k


def _boundary_loops(faces_set, bm):
    """Vong bien cua mot dao (canh seam hoac canh bien co dung 1 mat trong dao)."""
    bedges = set()
    for f in faces_set:
        for e in f.edges:
            inside = sum(1 for h in e.link_faces if h in faces_set)
            if e.seam or inside == 1:
                if inside == 1 or e.seam:
                    bedges.add(e)
    # gom canh bien thanh cac nhom lien thong qua dinh
    adj = collections.defaultdict(list)
    for e in bedges:
        a, b = e.verts
        adj[a].append(b)
        adj[b].append(a)
    seen, loops = set(), []
    for v in adj:
        if v in seen:
            continue
        st, comp = [v], []
        seen.add(v)
        while st:
            x = st.pop()
            comp.append(x)
            for y in adj[x]:
                if y not in seen:
                    seen.add(y)
                    st.append(y)
        loops.append(comp)
    return loops, bedges


def _euler(faces_set):
    vs, es = set(), set()
    for f in faces_set:
        vs.update(f.verts)
        es.update(f.edges)
    return len(vs) - len(es) + len(faces_set)


def _path(faces_set, src, dst, back_y, size):
    """Duong canh ngan nhat tu tap dinh src toi tap dinh dst trong dao; phia truoc (-Y) dat gap 4."""
    allowed = set()
    for f in faces_set:
        allowed.update(f.edges)
    dst = set(dst)
    dist = {}
    prev = {}
    pq = []
    for v in src:
        dist[v] = 0.0
        heapq.heappush(pq, (0.0, id(v), v))
    hit = None
    while pq:
        d, _, v = heapq.heappop(pq)
        if d > dist.get(v, 1e18):
            continue
        if v in dst:
            hit = v
            break
        for e in v.link_edges:
            if e not in allowed or e.seam:
                continue
            w = e.other_vert(v)
            mid = (v.co + w.co) / 2
            front = max(0.0, (back_y - mid.y) / max(size, 1e-9))       # cang ve phia truoc cang dat
            nd = d + e.calc_length() * (1 + 4 * front)
            if nd < dist.get(w, 1e18):
                dist[w] = nd
                prev[w] = (v, e)
                heapq.heappush(pq, (nd, id(w), w))
    if hit is None:
        return []
    out = []
    v = hit
    while v in prev:
        v, e = prev[v]
        out.append(e)
    return out


def _cut_to_disks(bm, size, back_y):
    """Rach them seam cho moi dao thanh dia (Euler = 1)."""
    for _ in range(6):
        lab, k = _islands(bm)
        groups = collections.defaultdict(set)
        for f, i in lab.items():
            groups[i].add(f)
        changed = False
        for i, fs in groups.items():
            chi = _euler(fs)
            if chi == 1:
                continue
            loops, _ = _boundary_loops(fs, bm)
            if len(loops) >= 2:                       # ong / nhieu lo: noi vong 0 voi vong gan nhat
                a = loops[0]
                rest = [v for l in loops[1:] for v in l]
                path = _path(fs, a, rest, back_y, size)
            elif len(loops) == 0:                     # khoi kin: noi hai dau theo truc dai
                vs = list({v for f in fs for v in f.verts})
                P = np.array([v.co[:] for v in vs])
                c = P.mean(0)
                w, U = np.linalg.eigh(np.cov((P - c).T))
                ax = U[:, -1]
                t = (P - c) @ ax
                path = _path(fs, [vs[int(t.argmin())]], [vs[int(t.argmax())]], back_y, size)
            else:                                     # 1 vong nhung co quai (genus) - de Blender tu xu ly
                path = []
            for e in path:
                e.seam = True
                changed = True
        if not changed:
            break


def _unwrap_method():
    try:
        items = [i.identifier for i in bpy.ops.uv.unwrap.get_rna_type().properties["method"].enum_items]
    except Exception:
        items = ["ANGLE_BASED"]
    for m in ("MINIMUM_STRETCH", "ANGLE_BASED", "CONFORMAL"):
        if m in items:
            return m
    return items[0]


def _fit_islands(ob, density, axis=None):
    """Moi dao: co gian ve dung mat do, roi CAN THEO KHUNG THE GIOI de cac manh ke nhau lien mach (nguoi dung
    2026-10-02: "manh nay va manh kia khong co ti lien ket"): xoay cho truc DUNG Z cua the gioi chay theo +V (dao
    nam ngang thi +Y), dich cho v ~ z * mat_do va u ~ (huong ngang cua +U) * mat_do. Hai manh cat tu cung mot
    khoi vi vay cung huong van len va gan khop hang mui dan o duong noi."""
    me = ob.data
    mw = ob.matrix_world
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    lab, k = _islands(bm)
    groups = collections.defaultdict(list)
    for f, i in lab.items():
        groups[i].append(f)
    Z = np.array([0.0, 0.0, 1.0])
    Y = np.array([0.0, 1.0, 0.0])

    def grad(fs, uvget, axis3):
        """Gradient (theo u, v) cua f = P . axis3 tren dao (trung binh theo dien tich)."""
        G = np.zeros(2)
        for f in fs:
            ls = f.loops
            for j in range(1, len(ls) - 1):
                l0, l1, l2 = ls[0], ls[j], ls[j + 1]
                p0, p1, p2 = (np.array(mw @ l.vert.co) for l in (l0, l1, l2))
                u0, u1, u2 = (np.array(uvget(l)) for l in (l0, l1, l2))
                a3 = np.linalg.norm(np.cross(p1 - p0, p2 - p0)) / 2
                du1, du2 = u1 - u0, u2 - u0
                det = du1[0] * du2[1] - du2[0] * du1[1]
                if abs(det) > 1e-14:
                    f1, f2 = (p1 - p0) @ axis3, (p2 - p0) @ axis3
                    G += np.array([(f1 * du2[1] - f2 * du1[1]) / det, (f2 * du1[0] - f1 * du2[0]) / det]) * a3
        return G
    for i, fs in groups.items():
        A3 = A2 = 0.0
        for f in fs:
            ls = f.loops
            for j in range(1, len(ls) - 1):
                l0, l1, l2 = ls[0], ls[j], ls[j + 1]
                A3 += ((mw @ l1.vert.co - mw @ l0.vert.co).cross(mw @ l2.vert.co - mw @ l0.vert.co)).length / 2
                du1, du2 = l1[uvl].uv - l0[uvl].uv, l2[uvl].uv - l0[uvl].uv
                A2 += abs(du1.x * du2.y - du2.x * du1.y) / 2
        if A2 <= 1e-14 or A3 <= 1e-14:
            continue
        s = density * math.sqrt(A3 / A2)
        loops = [l for f in fs for l in f.loops]
        U = np.array([l[uvl].uv[:] for l in loops]) * s
        # huong "len" cua dao: Z the gioi; dao gan nam ngang (Z gan nhu khong doi) -> theo Y
        lid = {id(l): n for n, l in enumerate(loops)}
        get = lambda l: U[lid[id(l)]]
        G = grad(fs, get, Z)
        nrm = np.zeros(3)
        for f in fs:
            nrm += np.array(mw.to_3x3() @ f.normal) * f.calc_area()
        horiz = abs(nrm[2]) > 0.8 * (np.linalg.norm(nrm) or 1)
        if horiz or np.linalg.norm(G) < 0.25:
            G = grad(fs, get, Y)
        ang = math.atan2(G[0], G[1]) if np.linalg.norm(G) > 1e-9 else 0.0
        ca, sa = math.cos(ang), math.sin(ang)
        U = U @ np.array([[ca, -sa], [sa, ca]]).T
        # neo theo the gioi: v ~ (Z hoac Y) * mat do, u ~ huong ngang cua +U * mat do
        P = np.array([np.array(mw @ l.vert.co) for l in loops])
        up = Y if (horiz or np.linalg.norm(grad(fs, get, Z)) < 0.25) else Z
        side = np.cross(up, [0.0, 0.0, 1.0] if up is Y else [0.0, 1.0, 0.0])
        if np.linalg.norm(side) < 1e-9:
            side = np.array([1.0, 0.0, 0.0])
        side = side / np.linalg.norm(side)
        gu = grad(fs, get, side)
        if gu[0] < 0:
            side = -side
        U[:, 1] += float(np.mean(P @ up * density - U[:, 1]))
        U[:, 0] += float(np.mean(P @ side * density - U[:, 0]))
        for l, uv in zip(loops, U):
            l[uvl].uv = (float(uv[0]), float(uv[1]))
    bm.to_mesh(me)
    bm.free()
    me.update()


FLOW_UV = "uvSet"      # ten kenh UV thu 2 o bo goc (BearArt) - shader UserWooler doc uv2.y lam tham so cuon len


def flow_uv(ob):
    """Kenh UV2 'uvSet' nhu BearArt: chieu PHANG, uv2.y chay 0 (dinh) -> 1 (day) theo chieu cao (len tan tu tren
    xuong); manh det nam ngang thi theo chieu dai. uv2.x cung ti le. Shader clip(uv2.y - _Progress): y phai trai
    du [0, 1] (validator game bao loi neu < 0.5 hoac am)."""
    me = ob.data
    while len(me.uv_layers) < 2:
        me.uv_layers.new(name=FLOW_UV)
    me.uv_layers[1].name = FLOW_UV
    mw = ob.matrix_world
    V = np.array([(mw @ v.co)[:] for v in me.vertices])
    if not len(V):
        return
    ext = V.max(0) - V.min(0)
    if ext[2] >= 0.5 * max(ext[0], ext[1]):
        t = V.max(0)[2] - V[:, 2]                  # dinh = 0
        h = V[:, 0] if ext[0] >= ext[1] else V[:, 1]
    else:
        k = 0 if ext[0] >= ext[1] else 1
        t = V[:, k] - V[:, k].min()
        h = V[:, 1 - k]
    span = float(t.max()) or 1.0
    y = t / span
    x = (h - h.min()) / span
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.stack([x[lv], y[lv]], axis=1).astype(np.float32).ravel()
    me.uv_layers[1].data.foreach_set("uv", uv)
    me.uv_layers.active = me.uv_layers[0]


def center_origin(ob):
    """Tam (origin) cua manh ve GIUA manh (tam hop bao), giu nguyen vi tri the gioi (nguoi dung 2026-10-02)."""
    from mathutils import Matrix, Vector
    me = ob.data
    if not me.vertices:
        return
    mw = ob.matrix_world.copy()
    W = np.array([(mw @ v.co)[:] for v in me.vertices])
    c = Vector(((W.min(0) + W.max(0)) / 2).tolist())
    local_c = mw.inverted() @ c
    me.transform(Matrix.Translation(-local_c))
    ob.matrix_world = mw @ Matrix.Translation(local_c)


def piece_axis(ob):
    """Truc de van len chay theo: truc dai nhat (PCA) neu manh thuon dai, khong thi truc dung Z."""
    P = np.array([v.co[:] for v in ob.data.vertices])
    if len(P) < 4:
        return Vector((0, 0, 1))
    w, U = np.linalg.eigh(np.cov((P - P.mean(0)).T))
    if w[-1] > 1.69 * max(w[-2], 1e-12):              # dai hon 1.3 lan chieu ke -> theo chieu dai
        a = U[:, -1]
        if a[2] < 0:
            a = -a
        return Vector(a.tolist())
    return Vector((0, 0, 1))


def unwrap(objs, density=std.UV_DENSITY):
    """Trai UV kieu bo goc cho cac object mesh (toa do the gioi = kich thuoc cuoi, mat truoc -Y)."""
    if not objs:
        return 0
    method = _unwrap_method()
    allP = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in objs])
    back_y = float(allP[:, 1].max())
    n_ok = 0
    for ob in objs:
        me = ob.data
        if not me.uv_layers:
            me.uv_layers.new(name=std.UV_NAME)
        me.uv_layers[0].name = std.UV_NAME
        me.uv_layers.active = me.uv_layers[0]
        bm = bmesh.new()
        bm.from_mesh(me)
        size = max(ob.dimensions) or 1.0
        for e in bm.edges:
            e.seam = (not e.smooth) or e.is_boundary
        _cut_to_disks(bm, size, back_y - ob.matrix_world.translation.y)
        bm.to_mesh(me)
        bm.free()
        bpy.context.view_layer.objects.active = ob
        for o in bpy.context.view_layer.objects:
            o.select_set(o is ob)
        try:
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.unwrap(method=method, margin=0.0, fill_holes=False, correct_aspect=True)
            bpy.ops.object.mode_set(mode="OBJECT")
            _fit_islands(ob, density)
            n_ok += 1
        except Exception as e:                     # khong de mot manh loi lam hong ca xuat
            print("[uv] %s: trai UV loi (%s) - dung chieu hop" % (ob.name, e))
            if bpy.context.object and bpy.context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            from .export import uv_box
            uv_box(me, density)
    return n_ok
