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
    if axis is not None:                        # khoi dai (unwrap_v2): van len chay DOC truc khoi
        ax = np.array(axis[:], dtype=float)
        ax = ax / (np.linalg.norm(ax) or 1.0)
        if ax[2] < 0:
            ax = -ax

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
        use_ax = axis is not None and np.linalg.norm(grad(fs, get, ax)) >= 0.25
        if use_ax:
            G = grad(fs, get, ax)
        elif horiz or np.linalg.norm(G) < 0.25:
            G = grad(fs, get, Y)
        ang = math.atan2(G[0], G[1]) if np.linalg.norm(G) > 1e-9 else 0.0
        ca, sa = math.cos(ang), math.sin(ang)
        U = U @ np.array([[ca, -sa], [sa, ca]]).T
        # neo theo the gioi: v ~ (Z hoac Y) * mat do, u ~ huong ngang cua +U * mat do
        P = np.array([np.array(mw @ l.vert.co) for l in loops])
        up = ax if use_ax else (Y if (horiz or np.linalg.norm(grad(fs, get, Z)) < 0.25) else Z)
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


# ------------------------------------------------------------------ UV KIEU MOI (A + C, 2026-10-08)
# Nguoi dung: "trai uv cho dep hon, hien tai dang hoi lo". Do: bo goc 2,2-3,3 dao / mesh, meo goc 3-6 do, dien tich lech
# > 2x 0,6-5%; unwrap() cu 1 dao / mesh (khoi tron ep thanh mot dia) -> meo goc 10-14 do, lech 3-12%.
#   A. khoi KIN tron -> tach doi truoc / sau (det -> theo mat det); do do meo tung dao, dao meo qua -> bo doi theo truc
#      dai cua dao roi trai lai (toi da MAX_ISLANDS dao / manh);
#   C. khoi DAI -> rach mot duong doc phia sau (nhu ong) va van len chay DOC truc khoi (_fit_islands axis).
ANGLE_MAX = 8.0           # do meo goc trung binh cua dao (do) - bo goc 3-6
BAD_MAX = 0.05            # phan dien tich lech > 2x
MAX_ISLANDS = 6
LONG_RATIO = 1.6          # truc dai >= 1.6 truc ke -> khoi dai (cach C)


def _pca(P):
    c = P.mean(0)
    w, U = np.linalg.eigh(np.cov((P - c).T) if len(P) > 3 else np.eye(3))
    return c, np.sqrt(np.maximum(w, 0))[::-1], U[:, ::-1]          # lon -> nho


BOX_FLAT = 0.2           # khoi co >= 20% dien tich mat phang ngang (|n.z| > 0.85) = dang HOP (vali, de, nap)
BAND_Z = 0.6             # |n.z| > 0.6 = mat tren / mat day; con lai = dai quanh than


def _split_band(fs, R3):
    """Khoi dang HOP (2026-10-08, nguoi dung: "chinh uv de texture di dep hon" - vali: van len xeo 47-74 do): mat TREN,
    mat DAY rieng, bon mat ben thanh MOT DAI quan quanh than (_cut_to_disks rach mot duong o phia sau) -> van len tren mat
    ben chay dung va lien mach nhu len quan quanh hop. Cum tren / day nho (< 5% dien tich, vd u nho) nhap vao dai."""
    nz = {f: (R3 @ f.normal).z for f in fs}
    grp = {f: (1 if nz[f] > BAND_Z else (-1 if nz[f] < -BAND_Z else 0)) for f in fs}
    tot = sum(f.calc_area() for f in fs) or 1.0
    seen = set()
    for f0 in fs:                                    # cum tren / day qua nho -> vao dai
        if f0 in seen or grp[f0] == 0:
            continue
        comp, st = [f0], [f0]
        seen.add(f0)
        while st:
            g = st.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h in grp and h not in seen and grp[h] == grp[f0]:
                        seen.add(h)
                        comp.append(h)
                        st.append(h)
        if sum(f.calc_area() for f in comp) < 0.05 * tot:
            for f in comp:
                grp[f] = 0
    for f in fs:
        for e in f.edges:
            if e.seam:
                continue
            lf = e.link_faces
            if len(lf) == 2 and lf[0] in grp and lf[1] in grp and grp[lf[0]] != grp[lf[1]]:
                e.seam = True


def _box_uv(ob, density):
    """UV KHOI HOP khong dai (vali, de, hop): bo giai UV uon dai quanh than thanh vong cung -> van xien 30 do. Nay CHIEU
    TRUC TIEP: dai quanh than V = chieu cao THE GIOI x mat do (van len dung tuyet doi, hang mui khop giua cac manh ke nhau),
    U = quang duong VONG QUANH than (chu vi o giua chieu cao theo goc quanh tam), duong noi o phia SAU (+Y); mat tren / day
    chieu phang tu tren (u = x, v = +-y). Tra ve True neu lam duoc."""
    me = ob.data
    mw = ob.matrix_world
    R3 = mw.to_3x3().normalized()
    if not me.uv_layers:
        me.uv_layers.new(name=std.UV_NAME)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.active
    fs = list(bm.faces)
    _split_band(fs, R3)                                 # danh dau seam = ranh gioi tren / day / dai (de doc nhom)
    nz = {f: (R3 @ f.normal).z for f in fs}
    grp = {}
    for f in fs:                                        # nhom theo thanh phan qua canh khong seam: da so phap tuyen
        grp[f] = 1 if nz[f] > BAND_Z else (-1 if nz[f] < -BAND_Z else 0)
    lab, _k = _islands(bm)
    votes = collections.defaultdict(collections.Counter)
    for f, i in lab.items():
        votes[i][grp[f]] += f.calc_area()
    isl_grp = {i: c.most_common(1)[0][0] for i, c in votes.items()}
    W = {v: np.array((mw @ v.co)[:]) for v in bm.verts}
    band = [f for f in fs if isl_grp[lab[f]] == 0]
    if not band:
        bm.free()
        return False
    P = np.array([W[v] for f in band for v in f.verts])
    cx, cy = float(P[:, 0].mean()), float(P[:, 1].mean())
    z0, z1 = float(P[:, 2].min()), float(P[:, 2].max())
    zm = (z0 + z1) / 2
    mid = P[np.abs(P[:, 2] - zm) <= 0.2 * max(z1 - z0, 1e-6)]
    if len(mid) < 8:
        mid = P
    th0 = math.atan2(1.0, 0.0)                          # duong noi o phia sau (+Y)
    ang = (np.arctan2(mid[:, 1] - cy, mid[:, 0] - cx) - th0) % (2 * math.pi)
    rad = np.hypot(mid[:, 0] - cx, mid[:, 1] - cy)
    NB = 144
    rb = np.full(NB, np.nan)
    idx = np.minimum((ang / (2 * math.pi) * NB).astype(int), NB - 1)
    for b in range(NB):
        m = idx == b
        if m.any():
            rb[b] = float(rad[m].mean())
    ok = ~np.isnan(rb)
    if ok.sum() < 8:
        bm.free()
        return False
    xb = np.arange(NB)
    rb = np.interp(xb, xb[ok], rb[ok], period=NB)
    th = (xb + 0.5) / NB * 2 * math.pi
    pts = np.stack([rb * np.cos(th), rb * np.sin(th)], 1)
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    Lb = np.concatenate([[0.0], np.cumsum(seg)])        # chu vi tich luy tai moi o (NB + 1 diem)
    thb = np.concatenate([th, [th[0] + 2 * math.pi]])
    tot = Lb[-1]
    T2 = np.concatenate([thb - 2 * math.pi, thb[1:], thb[1:] + 2 * math.pi])      # mo rong mot vong moi phia
    L2 = np.concatenate([Lb - tot, Lb[1:], Lb[1:] + tot])

    def L(a):
        return np.interp(a, T2, L2)
    for f in fs:
        g = isl_grp[lab[f]]
        ls = list(f.loops)
        if g == 0:
            a = np.array([(math.atan2(W[l.vert][1] - cy, W[l.vert][0] - cx) - th0) % (2 * math.pi) for l in ls])
            if a.max() - a.min() > math.pi:             # mat vat qua duong noi phia sau -> dua ve cung mot phia
                a = np.where(a < math.pi, a + 2 * math.pi, a)
            us = L(a)
            for l, u in zip(ls, us):
                l[uvl].uv = (float(u * density), float(W[l.vert][2] * density))
        else:
            for l in ls:
                p = W[l.vert]
                l[uvl].uv = (float(p[0] * density), float(p[1] * density * (1 if g > 0 else -1)))
    bm.to_mesh(me)
    bm.free()
    me.update()
    return True


def knit_direction(ob):
    """Do XIEN cua van len tren MAT DUNG: goc giua huong +V va truc gan nhat (THANG DUNG hoac NAM NGANG quanh than) ->
    (trung vi do, phan dien tich xien > 20 do). Bo goc chi co van dung (~0) hoac ngang (~90) - khong bao gio cheo
    (Radio / BearArt / Totoro / CoolerBox / ToyBox do 2026-10-08)."""
    me = ob.data
    if not me.uv_layers:
        return 90.0, 1.0
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    bm.normal_update()
    uvl = bm.loops.layers.uv.active
    angs, A = [], []
    for f in bm.faces:
        if abs(f.normal.z) > 0.7:
            continue
        ls = f.loops
        for j in range(1, len(ls) - 1):
            l0, l1, l2 = ls[0], ls[j], ls[j + 1]
            e1, e2 = l1.vert.co - l0.vert.co, l2.vert.co - l0.vert.co
            d1, d2 = l1[uvl].uv - l0[uvl].uv, l2[uvl].uv - l0[uvl].uv
            det = d1.x * d2.y - d2.x * d1.y
            a3 = e1.cross(e2).length / 2
            if abs(det) < 1e-12 or a3 < 1e-12:
                continue
            dv = (e2 * d1.x - e1 * d2.x) / det
            if dv.length > 1e-12:
                a = math.degrees(math.acos(min(1.0, abs(dv.normalized().z))))
                angs.append(min(a, 90.0 - a))
                A.append(a3)
    bm.free()
    if not A:
        return 0.0, 0.0
    angs, A = np.array(angs), np.array(A)
    return float(np.median(angs)), float(A[angs > 20].sum() / A.sum())


def _split_by_plane(fs, c, n):
    """Seam = canh giua hai mat (cung dao) nam hai phia mat phang (c, n). Tra ve so canh."""
    side = {f: float((np.array(f.calc_center_median()[:]) - c) @ n) >= 0 for f in fs}
    k = 0
    for f in fs:
        for e in f.edges:
            if e.seam:
                continue
            lf = e.link_faces
            if len(lf) == 2 and lf[0] in side and lf[1] in side and side[lf[0]] != side[lf[1]]:
                e.seam = True
                k += 1
    return k


def _island_stats(bm, uvl):
    """Moi dao -> (meo goc trung binh theo dien tich (do), phan dien tich lech > 2x, so mat, mat)."""
    lab, k = _islands(bm)
    groups = collections.defaultdict(list)
    for f, i in lab.items():
        groups[i].append(f)
    out = {}
    for i, fs in groups.items():
        A3, AU, ANG = [], [], []
        for f in fs:
            ls = f.loops
            for j in range(1, len(ls) - 1):
                tri = (ls[0], ls[j], ls[j + 1])
                p = [l.vert.co for l in tri]
                u = [l[uvl].uv for l in tri]
                a3 = (p[1] - p[0]).cross(p[2] - p[0]).length / 2
                au = abs((u[1].x - u[0].x) * (u[2].y - u[0].y) - (u[2].x - u[0].x) * (u[1].y - u[0].y)) / 2
                da = 0.0
                for q in range(3):
                    e1, e2 = p[(q + 1) % 3] - p[q], p[(q + 2) % 3] - p[q]
                    f1, f2 = u[(q + 1) % 3] - u[q], u[(q + 2) % 3] - u[q]
                    if min(e1.length, e2.length, f1.length, f2.length) > 1e-12:
                        da += abs(e1.angle(e2) - f1.angle(f2))
                A3.append(a3)
                AU.append(au)
                ANG.append(da / 3)
        A3, AU, ANG = np.array(A3), np.array(AU), np.array(ANG)
        tot = A3.sum()
        if tot <= 1e-14 or AU.sum() <= 1e-14:
            out[i] = (90.0, 1.0, len(fs), fs)
            continue
        r = np.log2(np.maximum(AU, 1e-20) / np.maximum(A3 * AU.sum() / tot, 1e-20))
        out[i] = (float(np.degrees((ANG * A3).sum() / tot)), float(A3[np.abs(r) > 1].sum() / tot), len(fs), fs)
    return out


def _do_unwrap(ob, method):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method=method, margin=0.0, fill_holes=False, correct_aspect=True)
    bpy.ops.object.mode_set(mode="OBJECT")


def unwrap_v2(objs, density=std.UV_DENSITY, log=print):
    """Trai UV kieu moi (A + C) -> (so manh trai duoc, meo goc trung binh, phan dien tich lech > 2x)."""
    if not objs:
        return 0, 0.0, 0.0
    method = _unwrap_method()
    allP = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in objs])
    back_y = float(allP[:, 1].max())
    n_ok, s_ang, s_bad, s_area = 0, 0.0, 0.0, 0.0
    for ob in objs:
        me = ob.data
        if not me.uv_layers:
            me.uv_layers.new(name=std.UV_NAME)
        me.uv_layers[0].name = std.UV_NAME
        me.uv_layers.active = me.uv_layers[0]
        P = np.array([v.co[:] for v in me.vertices])
        if len(P) < 4:
            continue
        size = max(ob.dimensions) or 1.0
        c, ext, U = _pca(P)
        long_axis = None
        R3o = ob.matrix_world.to_3x3().normalized()
        area = sum(p.area for p in me.polygons) or 1.0
        flat_o = sum(p.area for p in me.polygons if abs((R3o @ p.normal).z) > 0.85) / area
        if flat_o >= BOX_FLAT:
            try:                                   # khoi HOP (ke ca dai nhu lat nap vali): chieu dai quanh than - van dung,
                                                   # hang mui khop voi khoi ben duoi (tay / chan it mat ngang -> khong vao day)
                if _box_uv(ob, density):
                    bm = bmesh.new()
                    bm.from_mesh(me)
                    bm.transform(ob.matrix_world)
                    st = _island_stats(bm, bm.loops.layers.uv.active)
                    bm.free()
                    for a, b, n_, fs in st.values():
                        w = n_ / max(1, len(me.polygons))
                        s_ang += a * w * area
                        s_bad += b * w * area
                    s_area += area
                    n_ok += 1
                    continue
            except Exception as e:
                print("[uv] %s: chieu hop loi (%s) - trai thuong" % (ob.name, e))
        try:
            bm = bmesh.new()
            bm.from_mesh(me)
            for e in bm.edges:
                e.seam = (not e.smooth) or e.is_boundary          # mep nap phang (do buoc cat) = duong noi
            lab, k = _islands(bm)
            groups = collections.defaultdict(set)
            for f, i in lab.items():
                groups[i].add(f)
            for fs in groups.values():
                if _euler(fs) != 2:                                # dao co bien: _cut_to_disks lo (ong / dia)
                    continue
                Q = np.array([v.co[:] for v in {v for f in fs for v in f.verts}])
                qc, qe, qU = _pca(Q)
                if qe[0] >= LONG_RATIO * max(qe[1], 1e-9):         # C: khoi dai -> duong noi doc phia sau
                    long_axis = Vector(qU[:, 0].tolist())
                    continue
                R3 = ob.matrix_world.to_3x3().normalized()
                ar = sum(f.calc_area() for f in fs) or 1.0
                flat = sum(f.calc_area() for f in fs if abs((R3 @ f.normal).z) > 0.85) / ar
                if flat >= BOX_FLAT:                                # dang HOP -> tren / day / dai quanh than
                    _split_band(fs, R3)
                    continue
                n = qU[:, 2] if qe[2] < 0.5 * max(qe[1], 1e-9) else np.array([0.0, 1.0, 0.0])   # A: det | truoc/sau
                _split_by_plane(fs, qc, n)
            _cut_to_disks(bm, size, back_y - ob.matrix_world.translation.y)
            bm.to_mesh(me)
            bm.free()
            _do_unwrap(ob, method)
            # do do meo tung dao -> dao meo qua: bo doi theo truc dai cua dao, trai lai
            for _ in range(3):
                bm = bmesh.new()
                bm.from_mesh(me)
                uvl = bm.loops.layers.uv.active
                st = _island_stats(bm, uvl)
                bad = [(a, b, n_, fs) for a, b, n_, fs in st.values()
                       if (a > ANGLE_MAX or b > BAD_MAX) and n_ >= 40]
                if not bad or len(st) >= MAX_ISLANDS:
                    bm.free()
                    break
                for a, b, n_, fs in sorted(bad, key=lambda x: -x[0])[:MAX_ISLANDS - len(st)]:
                    Q = np.array([v.co[:] for v in {v for f in fs for v in f.verts}])
                    qc, qe, qU = _pca(Q)
                    _split_by_plane(set(fs), qc, qU[:, 0])
                _cut_to_disks(bm, size, back_y - ob.matrix_world.translation.y)
                bm.to_mesh(me)
                bm.free()
                _do_unwrap(ob, method)
            _fit_islands(ob, density, axis=long_axis)
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.transform(ob.matrix_world)
            st = _island_stats(bm, bm.loops.layers.uv.active)
            bm.free()
            area = sum(f.area for f in me.polygons) or 1.0
            for a, b, n_, fs in st.values():
                w = n_ / max(1, len(me.polygons))
                s_ang += a * w * area
                s_bad += b * w * area
            s_area += area
            n_ok += 1
        except Exception as e:                     # khong de mot manh loi lam hong ca xuat
            print("[uv] %s: trai UV moi loi (%s) - dung chieu hop" % (ob.name, e))
            if bpy.context.object and bpy.context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            from .export import uv_box
            uv_box(me, density)
    ang, badf = s_ang / max(s_area, 1e-12), s_bad / max(s_area, 1e-12)
    if log:
        log("[uv moi] %d/%d manh: meo goc ~%.1f do, dien tich lech > 2x ~%.1f%% (bo goc 3-6 do, 0,6-5%%)" % (
            n_ok, len(objs), ang, 100 * badf))
    return n_ok, ang, badf
