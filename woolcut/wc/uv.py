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
BOX_NZ, BOX_STRICT = 0.97, 0.33   # unwrap_v2: HOP THAT = >= 33% mat NGANG PHANG (lech < 14 do), khong tinh nap / tiep xuc:
                                  # de tron 54%, nap vali 37-54%, de giay 70% | dau 18%, giay 20%, vai ao, dinh ong quan
                                  # (>0.85 thi 21-36% - 30/37 manh cao lot vao nhanh hop, tay chan meo 13-21 do)
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


CYL_NH = 28               # so tang theo truc (tam tung tang di theo khoi) cho UV bam truc


ALIGNED = True            # unwrap_v2: khoi khong phai hop -> UV bam truc (_aligned_uv); False = unwrap Blender cu


def _mark_uv_seams(me):
    """Danh dau seam o canh co UV khong lien (de xem o UV Editor va dem dao)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    for e in bm.edges:
        lf = e.link_loops
        if len(lf) != 2:
            e.seam = True
            continue
        cut = False
        for v in e.verts:
            uvs = [l[uvl].uv for f in e.link_faces for l in f.loops if l.vert is v]
            if len(uvs) == 2 and (uvs[0] - uvs[1]).length > 1e-5:
                cut = True
        e.seam = cut
    bm.to_mesh(me)
    bm.free()
    me.update()


def _cg(I, J, Vv, b, n, iters=1500, tol=1e-7):
    """Giai A x = b (A doi xung, dang COO I, J, Vv) bang gradient lien hop + tien dieu kien duong cheo (khong co scipy)."""
    dg = np.bincount(I[I == J], Vv[I == J], minlength=n)
    Minv = 1.0 / np.where(dg > 1e-30, dg, 1.0)

    def A(x):
        return np.bincount(I, Vv * x[J], minlength=n)
    x = np.zeros(n)
    r = b - A(x)
    z = Minv * r
    p = z.copy()
    rz = r @ z
    nb = np.linalg.norm(b) or 1.0
    for _ in range(iters):
        Ap = A(p)
        pap = p @ Ap
        if abs(pap) < 1e-300:
            break
        al = rz / pap
        x += al * p
        r -= al * Ap
        if np.linalg.norm(r) < tol * nb:
            break
        z = Minv * r
        rz2 = r @ z
        p = z + (rz2 / rz) * p
        rz = rz2
    return x


ALIGN_CAP = 0.75          # |n.truc| > 0.75 -> chop, chieu phang
ALIGN_EPS = 0.05          # trong so tron (khong huong) o vung chop - truc gan song song phap tuyen


REGION_R = 0.3            # lan can do hinh dang tai cho = 0.3 x canh dai nhat cua manh
REGION_ELONG = 1.8        # lan can dai >= 1.8 lan be ngang -> doan ONG (ong tay ao), van chay doc ong
REGION_MIN = 0.06         # cum huong < 6% mau -> nhap vao vung tron


def _frame(a):
    """Truc a (huong len) -> (a, e1 = huong "truoc" (-Y) chieu len mat phang vuong goc, e2)."""
    a = a / (np.linalg.norm(a) or 1.0)
    if a[2] < -1e-6 or (abs(a[2]) < 1e-6 and a[0] < 0):
        a = -a
    fr = np.array([0.0, -1.0, 0.0])
    fr = fr - (fr @ a) * a
    if np.linalg.norm(fr) < 0.3:
        fr = np.array([0.0, 0.0, 1.0]) - a[2] * a
    e1 = fr / np.linalg.norm(fr)
    return a, e1, np.cross(a, e1)


def _axis_regions(W, PC, padj, size):
    """Chia manh theo HINH DANG TAI CHO (than ao kem hai ong tay, cao 2026-10-08: truc dai nhat la truc NGANG qua hai tay
    -> lung ao van nam ngang): lan can dai nhu ong -> truc cua ong; tron -> truc dung Z. -> (nhan moi mat, [truc])."""
    from mathutils.kdtree import KDTree
    rng = np.random.RandomState(7)
    S = W[rng.choice(len(W), min(400, len(W)), replace=False)]
    kd = KDTree(len(W))
    for i, p in enumerate(W):
        kd.insert(Vector(p), i)
    kd.balance()
    Z = np.array([0.0, 0.0, 1.0])
    refs, lab_s = [Z], []
    for p in S:
        idx = [i for _, i, _ in kd.find_range(Vector(p), REGION_R * size)]
        if len(idx) < 8:
            lab_s.append(0)
            continue
        c, ext, U = _pca(W[idx])
        ax = U[:, 0]
        if ext[0] < REGION_ELONG * max(ext[1], 1e-9) or abs(ax @ Z) > math.cos(math.radians(30)):
            lab_s.append(0)                              # tron, hoac ong DUNG -> cung truc Z
            continue
        ax = _frame(ax)[0]
        best = max(range(1, len(refs)), key=lambda k: abs(refs[k] @ ax), default=None)
        if best is not None and abs(refs[best] @ ax) > math.cos(math.radians(25)):
            lab_s.append(best)
        else:
            refs.append(ax)
            lab_s.append(len(refs) - 1)
    lab_s = np.array(lab_s)
    for k in range(1, len(refs)):
        if (lab_s == k).mean() < REGION_MIN:
            lab_s[lab_s == k] = 0
    ks = KDTree(len(S))
    for i, p in enumerate(S):
        ks.insert(Vector(p), i)
    ks.balance()
    lab = np.array([lab_s[ks.find(Vector(c))[1]] for c in PC])
    for _ in range(2):                                   # lam min bien vung: da so lang gieng
        new = lab.copy()
        for f, nb in enumerate(padj):
            if nb:
                vals, cnt = np.unique(lab[nb], return_counts=True)
                if cnt.max() > len(nb) / 2:
                    new[f] = vals[cnt.argmax()]
        lab = new
    axes = [refs[k] if k else Z for k in range(len(refs))]
    return lab, axes


def _components(mask, padj):
    seen = np.zeros(len(mask), bool)
    out = []
    for f0 in np.where(mask)[0]:
        if seen[f0]:
            continue
        comp, st = [f0], [f0]
        seen[f0] = True
        while st:
            f = st.pop()
            for g in padj[f]:
                if mask[g] and not seen[g]:
                    seen[g] = True
                    comp.append(g)
                    st.append(g)
        out.append(np.array(comp))
    return out


def _solve_region(W, lv, ps, pt, pn, polys, tris, a):
    """Mot vung: grad v = truc chieu len mat, grad u vuong goc, do dai 1 (binh phuong toi thieu); duong noi phia sau;
    chop (|n.truc| > ALIGN_CAP) chieu phang. -> {loop: (u, v)} hoac None."""
    a, e1, e2 = _frame(np.asarray(a, float))
    pset = np.zeros(len(ps), bool)
    pset[polys] = True
    vin = np.unique(np.concatenate([lv[ps[k]:ps[k] + pt[k]] for k in polys]))
    c0 = W[vin].mean(0)
    H = (W - c0) @ a
    h0, h1 = float(H[vin].min()), float(H[vin].max())
    NH = CYL_NH
    hf = np.clip((H - h0) / max(h1 - h0, 1e-9) * (NH - 1), 0, NH - 1)
    X, Y = (W - c0) @ e1, (W - c0) @ e2
    cx, cy, okr = np.zeros(NH), np.zeros(NH), np.zeros(NH, bool)
    for i in range(NH):
        m = np.abs(hf[vin] - i) <= 0.75
        if m.sum() >= 3:
            cx[i], cy[i], okr[i] = X[vin][m].mean(), Y[vin][m].mean(), True
    if okr.sum() >= 2:
        xh = np.arange(NH)
        cx, cy = np.interp(xh, xh[okr], cx[okr]), np.interp(xh, xh[okr], cy[okr])
    th = np.arctan2(Y - np.interp(hf, np.arange(NH), cy), X - np.interp(hf, np.arange(NH), cx))
    nv = len(W)
    out = {}
    cap = np.abs(pn @ a) > ALIGN_CAP
    var = {}
    for k in polys:
        sl = range(ps[k], ps[k] + pt[k])
        if cap[k]:
            nk = a if pn[k] @ a > 0 else -a
            b1 = np.cross(nk, e1)
            b1 = b1 / (np.linalg.norm(b1) or 1.0)
            b2 = np.cross(nk, b1)
            for l in sl:
                p = W[lv[l]]
                out[l] = (float(p @ b1), float(p @ b2))
            continue
        t_ = th[lv[ps[k]:ps[k] + pt[k]]]
        wrap = t_.max() - t_.min() > math.pi
        for l in sl:
            var[l] = lv[l] + (nv if wrap and th[lv[l]] < 0 else 0)
    if len(var) < 6:
        return out
    L = np.array(list(var.keys()))
    used, vidx = np.unique(np.array([var[l] for l in L]), return_inverse=True)
    lidx = dict(zip(L.tolist(), vidx.tolist()))
    n = len(used)
    Wv = W[used % nv]
    sel = pset[tris[:, 3]] & ~cap[tris[:, 3]]
    T = np.array([[lidx[l] for l in t[:3]] for t in tris[sel]])
    if len(T) < 4:
        return None
    P0, P1, P2 = Wv[T[:, 0]], Wv[T[:, 1]], Wv[T[:, 2]]
    nrm = np.cross(P1 - P0, P2 - P0)
    A2 = np.linalg.norm(nrm, axis=1)
    ok = A2 > 1e-14
    T, P0, P1, P2, nrm, A2 = T[ok], P0[ok], P1[ok], P2[ok], nrm[ok], A2[ok]
    nh = nrm / A2[:, None]
    Ar = A2 / 2
    G = np.stack([np.cross(nh, P2 - P1), np.cross(nh, P0 - P2), np.cross(nh, P1 - P0)], 1) / A2[:, None, None]
    d = a[None, :] - (nh @ a)[:, None] * nh
    w = (d * d).sum(1)
    tv = d / np.maximum(np.sqrt(w), 1e-9)[:, None]
    tu = np.cross(tv, nh)
    c = w + ALIGN_EPS * (1 - w)
    K = np.einsum("tid,tjd->tij", G, G) * (Ar * c)[:, None, None]
    reg = 1e-9 * float(K[:, 0, 0].mean())
    I = np.concatenate([np.repeat(T, 3, axis=1).ravel(), np.arange(n)])
    J = np.concatenate([np.tile(T, (1, 3)).ravel(), np.arange(n)])
    Vv = np.concatenate([K.ravel(), np.full(n, reg)])
    bu, bv = np.zeros(n), np.zeros(n)
    np.add.at(bu, T, np.einsum("tid,td->ti", G, tu) * (Ar * w)[:, None])
    np.add.at(bv, T, np.einsum("tid,td->ti", G, tv) * (Ar * w)[:, None])
    u = _cg(I, J, Vv, bu, n)
    v = _cg(I, J, Vv, bv, n)
    gu = np.einsum("tid,ti->td", G, u[T])
    gv = np.einsum("tid,ti->td", G, v[T])
    sc_ = np.sqrt(np.abs((np.cross(gu, gv) * nh).sum(1)))
    o_ = np.argsort(sc_)
    med = sc_[o_][min(len(o_) - 1, np.searchsorted(np.cumsum(Ar[o_]) / Ar.sum(), 0.5))]
    if med > 1e-9:                                       # phep giai co ngan grad ~ 0,8 -> dua co mui ve dung mat do
        u, v = u / med, v / med
    # neo hang mui theo toa do truc the gioi, uu tien MAT DUNG (o do v ~ z dung): hai manh dau cat doi giua mat (cao
    # 2026-10-08, nguoi dung khoanh giua hai mat) khop hang o duong cat thay vi lech theo do doc rieng tung manh
    wv = np.zeros(n)
    np.add.at(wv, T, (Ar * w)[:, None] * np.ones((1, 3)))
    v += float(((Wv @ a - v) * wv).sum() / max(wv.sum(), 1e-12))
    front = np.abs(th[used % nv]) < 0.3
    u -= float(u[front].mean()) if front.any() else float(u.mean())
    ua = (u[T[:, 1]] - u[T[:, 0]]) * (v[T[:, 2]] - v[T[:, 0]]) - (u[T[:, 2]] - u[T[:, 0]]) * (v[T[:, 1]] - v[T[:, 0]])
    if (np.sign(ua) * Ar).sum() < 0:
        u = -u
    for l, i in lidx.items():
        out[l] = (float(u[i]), float(v[i]))
    return out


def _aligned_uv(ob, density, axis=None):
    """UV BAM TRUC (nguoi dung 2026-10-08: "uv van len phai xu ly chuan... tay, chan hoi loan, phai duoc nhu de tron"):
    unwrap goc dan phang tung nua than nhu ban do -> hang mui cong xoay, co mui lech. Nay: chia manh theo hinh dang tai
    cho (_axis_regions: than tron -> truc Z, ong tay -> truc ong), moi vung giai binh phuong toi thieu grad v = truc chieu
    len mat, grad u vuong goc (cot mui chay doc than / doc ong, mui deu), chop + nap cat chieu phang, duong noi phia sau.
    Cao truot van: lech co mui > 25% 8,3% -> 1,9% dien tich, meo goc 5,5 -> 2,5 do. -> True / False."""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name=std.UV_NAME)
    M4 = np.array(ob.matrix_world)
    nv = len(me.vertices)
    if nv < 8 or not len(me.polygons):
        return False
    co = np.empty(nv * 3)
    me.vertices.foreach_get("co", co)
    W = co.reshape(-1, 3) @ M4[:3, :3].T + M4[:3, 3]
    nl = len(me.loops)
    lv = np.empty(nl, np.int64)
    me.loops.foreach_get("vertex_index", lv)
    le = np.empty(nl, np.int64)
    me.loops.foreach_get("edge_index", le)
    npoly = len(me.polygons)
    ps = np.empty(npoly, np.int64)
    pt = np.empty(npoly, np.int64)
    me.polygons.foreach_get("loop_start", ps)
    me.polygons.foreach_get("loop_total", pt)
    pn = np.empty(npoly * 3)
    me.polygons.foreach_get("normal", pn)
    pn = pn.reshape(-1, 3) @ np.linalg.inv(M4[:3, :3])
    pn = pn / np.maximum(np.linalg.norm(pn, axis=1), 1e-12)[:, None]
    PC = np.array([W[lv[ps[k]:ps[k] + pt[k]]].mean(0) for k in range(npoly)])
    lp = np.repeat(np.arange(npoly), pt)
    e2p = collections.defaultdict(list)
    for l in range(nl):
        e2p[le[l]].append(lp[l])
    padj = [[] for _ in range(npoly)]
    for fs_ in e2p.values():
        if len(fs_) == 2:
            padj[fs_[0]].append(fs_[1])
            padj[fs_[1]].append(fs_[0])
    capa = me.attributes.get("wc_cap")
    cutcap = np.zeros(npoly, bool)
    if capa is not None and capa.domain == "FACE":
        cv = np.empty(npoly, np.int32)
        capa.data.foreach_get("value", cv)
        cutcap = cv >= 0
    me.calc_loop_triangles()
    ntri = len(me.loop_triangles)
    tl = np.empty(ntri * 3, np.int64)
    me.loop_triangles.foreach_get("loops", tl)
    tp = np.empty(ntri, np.int64)
    me.loop_triangles.foreach_get("polygon_index", tp)
    tris = np.hstack([tl.reshape(-1, 3), tp[:, None]])
    size = float((W.max(0) - W.min(0)).max()) or 1.0
    if axis is not None:
        lab, axes = np.zeros(npoly, int), [np.asarray(axis, float)]
    else:
        lab, axes = _axis_regions(W, PC, padj, size)
    UU = np.zeros(nl)
    VV = np.zeros(nl)
    done = np.zeros(nl, bool)
    for k in np.where(cutcap)[0]:                        # nap do cat (an trong khe): chieu phang theo phap tuyen nap
        nk = pn[k]
        b1 = np.cross(nk, [0.0, 0.0, 1.0] if abs(nk[2]) < 0.9 else [1.0, 0.0, 0.0])
        b1 = b1 / (np.linalg.norm(b1) or 1.0)
        b2 = np.cross(nk, b1)
        sl = slice(ps[k], ps[k] + pt[k])
        P = W[lv[sl]]
        UU[sl], VV[sl], done[sl] = P @ b1, P @ b2, True
    for _ in range(4):                                   # cum vai mat le (nhieu nhan) -> theo vung ben canh
        moved = False
        for r in range(len(axes)):
            for comp in _components((lab == r) & ~cutcap, padj):
                if len(comp) >= 24 or len(comp) == (~cutcap).sum():
                    continue
                nb = [lab[g] for f in comp for g in padj[f] if lab[g] != r and not cutcap[g]]
                if nb:
                    lab[comp] = collections.Counter(nb).most_common(1)[0][0]
                    moved = True
        if not moved:
            break
    n_ok = 0
    for r, ax in enumerate(axes):
        for comp in _components((lab == r) & ~cutcap, padj):
            res = _solve_region(W, lv, ps, pt, pn, comp, tris, ax)
            if res is None:                              # vung qua nho de giai -> chieu phang
                a_, e1_, e2_ = _frame(np.asarray(ax, float))
                for k in comp:
                    sl = slice(ps[k], ps[k] + pt[k])
                    P = W[lv[sl]]
                    UU[sl], VV[sl], done[sl] = P @ e1_, P @ a_, True
                continue
            n_ok += 1
            for l, (u_, v_) in res.items():
                UU[l], VV[l], done[l] = u_, v_, True
    if not done.all() or not n_ok:
        return False
    uv = np.empty(nl * 2)
    uv[0::2] = UU * density
    uv[1::2] = VV * density
    me.uv_layers.active.data.foreach_set("uv", uv)
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


def _piece_stats(ob):
    """(meo goc trung binh do, phan dien tich lech > 2x trong dao, phan dien tich co mui lech > 25% so trung vi manh)."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    uvl = bm.loops.layers.uv.active
    st = _island_stats(bm, uvl)
    S, A = [], []
    for f in bm.faces:
        ls = f.loops
        for j in range(1, len(ls) - 1):
            l0, l1, l2 = ls[0], ls[j], ls[j + 1]
            a3 = (l1.vert.co - l0.vert.co).cross(l2.vert.co - l0.vert.co).length / 2
            d1, d2 = l1[uvl].uv - l0[uvl].uv, l2[uvl].uv - l0[uvl].uv
            if a3 > 1e-12:
                S.append(math.sqrt(abs(d1.x * d2.y - d2.x * d1.y) / 2 / a3))
                A.append(a3)
    bm.free()
    nf = max(1, len(me.polygons))
    ang = sum(a * n_ / nf for a, b, n_, fs in st.values())
    bad = sum(b * n_ / nf for a, b, n_, fs in st.values())
    spread = 0.0
    if A:
        S, A = np.array(S), np.array(A)
        o_ = np.argsort(S)
        ref = S[o_][min(len(o_) - 1, np.searchsorted(np.cumsum(A[o_]) / A.sum(), 0.5))]
        spread = float(A[np.abs(S / max(ref, 1e-12) - 1) > 0.25].sum() / A.sum())
    return ang, bad, spread


def _old_unwrap(ob, density, method, back_y):
    """Trai Blender theo dao (cach truoc 2026-10-08): seam o mep nap, khoi kin dai -> noi doc sau, tron -> truoc / sau,
    dao meo -> bo doi; can dao theo khung the gioi (_fit_islands)."""
    me = ob.data
    size = max(ob.dimensions) or 1.0
    long_axis = None
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
            R3 = ob.matrix_world.to_3x3().normalized()
            if qe[0] >= LONG_RATIO * max(qe[1], 1e-9):         # C: khoi dai -> duong noi doc phia sau
                long_axis = Vector(qU[:, 0].tolist())
                continue
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
        for _ in range(3):                                     # dao meo qua: bo doi theo truc dai cua dao, trai lai
            bm = bmesh.new()
            bm.from_mesh(me)
            uvl = bm.loops.layers.uv.active
            st = _island_stats(bm, uvl)
            bad = [(a, b, n_, fs) for a, b, n_, fs in st.values() if (a > ANGLE_MAX or b > BAD_MAX) and n_ >= 40]
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
        return True
    except Exception as e:                     # khong de mot manh loi lam hong ca xuat
        print("[uv] %s: trai UV moi loi (%s) - dung chieu hop" % (ob.name, e))
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        from .export import uv_box
        uv_box(me, density)
        return False


def _contact_faces(ob, bvhs, tol):
    """Mat nam SAT be mat manh khac (mat tiep xuc sau khi cat phan chim - wc/overlap.py: dinh dui phang cho chui vao vat
    ao) -> an, khong tinh la "mat ngang cua hop" (cao 2026-10-08: 30/37 manh vao nhanh hop vi mat nay)."""
    me = ob.data
    out = np.zeros(len(me.polygons), bool)
    if not len(me.polygons):
        return out
    C = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("center", C)
    M4 = np.array(ob.matrix_world)
    C = C.reshape(-1, 3) @ M4[:3, :3].T + M4[:3, 3]
    lo, hi = C.min(0) - tol, C.max(0) + tol
    for n, (b, blo, bhi) in bvhs.items():
        if n == ob.name or (hi < blo).any() or (bhi < lo).any():
            continue
        m = np.all((C >= blo - tol) & (C <= bhi + tol), axis=1) & ~out
        for i in np.where(m)[0]:
            if b.find_nearest(Vector(C[i]), tol)[0] is not None:
                out[i] = True
    return out


def _uv_get(me):
    buf = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", buf)
    return buf


def unwrap_v2(objs, density=std.UV_DENSITY, log=print):
    """Trai UV kieu moi -> (so manh trai duoc, meo goc trung binh, phan dien tich lech > 2x).
    - Khoi HOP that (de tron, vali: >= 20% dien tich mat ngang, KHONG tinh nap cat / mat tiep xuc): _box_uv (nguoi dung
      2026-10-08: "de chuan roi").
    - Con lai (tay, chan, than, dau): UV BAM TRUC (_aligned_uv) - so voi cach cu tung manh, chi giu khi khong te hon ro
      (meo goc +3 do, lech > 2x +5%, co mui lech +8%): ven truot gau dau bep co manh det mong bam truc hong 40 do."""
    if not objs:
        return 0, 0.0, 0.0
    method = _unwrap_method()
    allP = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in objs])
    back_y = float(allP[:, 1].max())
    n_ok, s_ang, s_bad, s_area = 0, 0.0, 0.0, 0.0
    n_al = 0
    from mathutils.bvhtree import BVHTree
    bvhs = {}
    for o in objs:
        o.data.calc_loop_triangles()
        Wo = [o.matrix_world @ v.co for v in o.data.vertices]
        Wa = np.array([w[:] for w in Wo]) if Wo else np.zeros((1, 3))
        bvhs[o.name] = (BVHTree.FromPolygons(Wo, [tuple(t.vertices) for t in o.data.loop_triangles], all_triangles=True),
                        Wa.min(0), Wa.max(0))
    tol = 1e-3 * float((allP.max(0) - allP.min(0)).max())
    for ob in objs:
        me = ob.data
        if not me.uv_layers:
            me.uv_layers.new(name=std.UV_NAME)
        me.uv_layers[0].name = std.UV_NAME
        me.uv_layers.active = me.uv_layers[0]
        if len(me.vertices) < 4:
            continue
        R3o = ob.matrix_world.to_3x3().normalized()
        area = sum(p.area for p in me.polygons) or 1.0
        capa = me.attributes.get("wc_cap")
        capv = None
        if capa is not None and capa.domain == "FACE":
            capv = np.empty(len(me.polygons), np.int32)
            capa.data.foreach_get("value", capv)
        contact = _contact_faces(ob, bvhs, tol)
        real = [p for p in me.polygons if (capv is None or capv[p.index] < 0) and not contact[p.index]]
        area_r = sum(p.area for p in real) or area
        flat_o = sum(p.area for p in real if abs((R3o @ p.normal).z) > BOX_NZ) / area_r
        if flat_o >= BOX_STRICT:
            try:                                   # khoi HOP (de tron, vali): chieu dai quanh than - van dung, hang mui
                if _box_uv(ob, density):           # khop voi khoi ben duoi
                    a, b, _ = _piece_stats(ob)
                    s_ang += a * area
                    s_bad += b * area
                    s_area += area
                    n_ok += 1
                    continue
            except Exception as e:
                print("[uv] %s: chieu hop loi (%s) - trai thuong" % (ob.name, e))
        al = None
        if ALIGNED:
            try:
                if _aligned_uv(ob, density):
                    _mark_uv_seams(me)
                    al = (_uv_get(me), _piece_stats(ob))
            except Exception as e:
                print("[uv] %s: UV bam truc loi (%s) - trai thuong" % (ob.name, e))
        ok = _old_unwrap(ob, density, method, back_y)
        so = _piece_stats(ob)
        use = so
        if al is not None:
            sa = al[1]
            if sa[0] <= max(ANGLE_MAX, so[0] + 3.0) and sa[1] <= so[1] + 0.05 and sa[2] <= so[2] + 0.08:
                me.uv_layers.active.data.foreach_set("uv", al[0])
                _mark_uv_seams(me)
                use = sa
                n_al += 1
        s_ang += use[0] * area
        s_bad += use[1] * area
        s_area += area
        n_ok += int(ok or use is not so)
    ang, badf = s_ang / max(s_area, 1e-12), s_bad / max(s_area, 1e-12)
    if log:
        log("[uv moi] %d/%d manh (%d bam truc): meo goc ~%.1f do, dien tich lech > 2x ~%.1f%% (bo goc 3-6 do, 0,6-5%%)" % (
            n_ok, len(objs), n_al, ang, 100 * badf))
    return n_ok, ang, badf
