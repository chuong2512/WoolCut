"""CHIA KHOI THEO THE TICH (2026-10-12) - tach vung mat (vung mau texture) ra khoi mot khoi KIN ma KHONG dung nap phang.

Van de (gau ve tranh): bien mau texture chay cong 3D quanh than / vai / co, than Tripo khong loi -> moi kieu nap dung tu
VONG BIEN (CDT phang, quat tu tam, mang cang Laplace) deu dam XUYEN be mat: 9-10/14 manh tach mau tu cat nhau, bo cong
ghep khong duoc (lui ve voxel ca manh), cat tia an mat mep -> mep rach.

Cach moi: TRUONG DIEU HOA trong the tich: u = 1 sat be mat vung A, 0 sat be mat phan con lai B (doc mot doan doc tron
qua duong bien), giai Laplace cho cac o ben trong -> mat u = 0,5 la MANG cang qua vong bien NAM TRONG khoi (gan mat
dien tich nho nhat): o co / co chan thi nam ngang cho thot, duoi mieng va thi la thau kinh nong (~0,6 ban kinh), giay /
dau la ca khoi. (Da thu "diem trong thuoc vung be mat gan nhat" + gioi han do sau: giay thanh cai bat rong, ong quan cam
xuong long giay.) Marching tetrahedra -> khoi cat C kin -> Boolean EXACT: A' = khoi giao C, B' = khoi tru C. Be mat
Tripo giu nguyen (chi tam giac nam tren duong bien bi xe), mat ngan la mat dong muc cua mot truong -> KHONG tu cat."""
import numpy as np

VS_N = 64               # o luoi theo canh dai nhat cua khoi
VS_MAXPTS = 500000      # tran so diem luoi
VS_BLUR = 1.2           # do mo truong (sigma, theo o luoi): nghiem TV gan nhi phan -> mat bac thang neu khong mo
VS_BAND = 1.6           # o luoi cach be mat <= 1,6 o = dieu kien bien (gia tri theo vung gan nhat, doc qua duong bien)
VS_ITERS = 600          # vong CG toi da cho phuong trinh Laplace (diem khoi dau)
VS_TV_ITERS = 500       # vong primal-dual toi thieu bien phan toan phan (mat ngan dien tich nho nhat)
VS_CUT_FACES = 6000     # giam mat khoi cat ve ~ so nay truoc Boolean
VS_KEEP = (0.75, 1.3)   # dien tich be mat ngoai cua A' / dien tich mask phai trong khoang nay


def _bvh(t, faces):
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    sub = t.subset(np.asarray(faces))
    return BVHTree.FromPolygons([Vector(v) for v in sub.V], [tuple(int(i) for i in f) for f in sub.F],
                                all_triangles=True)


def _blur(phi, s):
    if s <= 0.3:
        return phi
    r = int(np.ceil(3 * s))
    x = np.arange(-r, r + 1)
    k = np.exp(-0.5 * (x / s) ** 2)
    k /= k.sum()
    for ax in range(3):
        pad = [(0, 0)] * 3
        pad[ax] = (r, r)
        p = np.pad(phi, pad, mode="edge")
        out = np.zeros_like(phi)
        for i, w in enumerate(k):
            sl = [slice(None)] * 3
            sl[ax] = slice(i, i + phi.shape[ax])
            out += w * p[tuple(sl)]
        phi = out
    return phi


# 6 tu dien Kuhn cua mot o (chung duong cheo 0-7, khop giua cac o ke nhau -> mat kin, da tap)
_KUHN = np.array([[0, a, a | b, 7] for a, b in ((1, 2), (1, 4), (2, 1), (2, 4), (4, 1), (4, 2))], dtype=np.int64)


def marching_tets(phi, lo, h, clamp=0.03):
    """Mat dong muc phi = 0 (phi < 0 = ben trong) -> (V [n,3], F [m,3]) kin, phap tuyen ra ngoai (huong phi > 0).
    Bien luoi phai > 0."""
    nx, ny, nz = phi.shape
    N = nx * ny * nz
    flat = phi.ravel()
    flat = np.where(flat == 0, 1e-12, flat)
    ii, jj, kk = np.meshgrid(np.arange(nx - 1), np.arange(ny - 1), np.arange(nz - 1), indexing="ij")
    base = ((ii * ny + jj) * nz + kk).ravel()
    off = np.array([((b & 1) * ny + ((b >> 1) & 1)) * nz + ((b >> 2) & 1) for b in range(8)], dtype=np.int64)
    corner = flat[base[:, None] + off[None]]                          # [ncube, 8]
    mixed = (corner.min(1) < 0) & (corner.max(1) > 0)
    base = base[mixed]
    T = base[:, None, None] + off[_KUHN][None]                        # [ncube, 6, 4]
    T = T.reshape(-1, 4)
    val = flat[T]
    ins = val < 0
    cnt = ins.sum(1)
    keep = (cnt > 0) & (cnt < 4)
    T, val, ins, cnt = T[keep], val[keep], ins[keep], cnt[keep]

    def pos(g):
        k = g % nz
        j = (g // nz) % ny
        i = g // (ny * nz)
        return lo + h * np.stack([i, j, k], axis=1)

    keys, tris = [], []
    # sap xep moi tu dien: dinh "trong" truoc (on dinh) -> xu ly theo so dinh trong
    order = np.argsort(~ins, axis=1, kind="stable")
    T = np.take_along_axis(T, order, 1)
    val = np.take_along_axis(val, order, 1)
    edges_all = []
    for c in (1, 2, 3):
        m = cnt == c
        if not m.any():
            continue
        Tm = T[m]
        if c == 1:                     # 1 trong (0) -> tam giac tren canh (0,1),(0,2),(0,3)
            E = [(0, 1), (0, 2), (0, 3)]
            tri = [(0, 1, 2)]
        elif c == 3:                   # 3 trong (0,1,2), ngoai 3 -> canh (0,3),(1,3),(2,3)
            E = [(0, 3), (1, 3), (2, 3)]
            tri = [(0, 1, 2)]
        else:                          # 2 trong (0,1), ngoai (2,3) -> tu giac (0,2),(0,3),(1,3),(1,2)
            E = [(0, 2), (0, 3), (1, 3), (1, 2)]
            tri = [(0, 1, 2), (0, 2, 3)]
        ek = [np.minimum(Tm[:, a], Tm[:, b]) * N + np.maximum(Tm[:, a], Tm[:, b]) for a, b in E]
        for tr in tri:
            tris.append((np.stack([ek[tr[0]], ek[tr[1]], ek[tr[2]]], axis=1), Tm, c))
    if not tris:
        return None
    allk = np.concatenate([x[0].ravel() for x in tris])
    uk, inv = np.unique(allk, return_inverse=True)
    a, b = uk // N, uk % N
    va, vb = flat[a], flat[b]
    tt = np.clip(va / (va - vb), clamp, 1 - clamp)
    V = pos(a) + tt[:, None] * (pos(b) - pos(a))
    F, o = [], 0
    for kk_, Tm, c in tris:
        n_ = kk_.size
        F.append(inv[o:o + n_].reshape(-1, 3))
        o += n_
    # huong: phap tuyen phai chi tu dinh "trong" sang dinh "ngoai" cua tu dien
    out = []
    for (kk_, Tm, c), f in zip(tris, F):
        P_ = pos(Tm.ravel()).reshape(-1, 4, 3)
        cin = P_[:, :c].mean(1)
        cout = P_[:, c:].mean(1)
        nrm = np.cross(V[f[:, 1]] - V[f[:, 0]], V[f[:, 2]] - V[f[:, 0]])
        flip = (nrm * (cout - cin)).sum(1) < 0
        f = f.copy()
        f[flip] = f[flip][:, ::-1]
        out.append(f)
    F = np.concatenate(out)
    good = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    return V, F[good]


def _boolean(t, Vc, Fc, op, robust=False):
    """Boolean EXACT t (op) C -> (TM, mat goc tu C?) ; thuoc tinh mat "wc_src" (0 = t, 1 = C) di theo mat."""
    import bpy
    from . import bl
    made = []
    try:
        def mk(V, F, nm, src):
            me = bpy.data.meshes.new(nm)
            me.from_pydata(np.asarray(V).tolist(), [], np.asarray(F).tolist())
            me.update()
            at = me.attributes.new("wc_src", "INT", "FACE")
            at.data.foreach_set("value", [src] * len(me.polygons))
            if src == 0:
                fi = me.attributes.new("wc_fi", "INT", "FACE")
                fi.data.foreach_set("value", list(range(len(me.polygons))))
            ob = bpy.data.objects.new(nm, me)
            bpy.context.scene.collection.objects.link(ob)
            made.append(ob)
            return ob
        ob = mk(t.V, t.F, "_vs_t", 0)
        oc = mk(Vc, Fc, "_vs_c", 1)
        mod = ob.modifiers.new("b", "BOOLEAN")
        mod.operation, mod.solver, mod.object = op, "EXACT", oc
        if robust:                                          # khoi cat sau giam mat co the tu cat / ho li ti
            mod.use_self = True
            mod.use_hole_tolerant = True
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        me2.calc_loop_triangles()
        nt = len(me2.loop_triangles)
        V = np.empty(len(me2.vertices) * 3)
        me2.vertices.foreach_get("co", V)
        F = np.empty(nt * 3, np.int64)
        me2.loop_triangles.foreach_get("vertices", F)
        P = np.empty(nt, np.int64)
        me2.loop_triangles.foreach_get("polygon_index", P)
        src = np.zeros(len(me2.polygons), np.int64)
        fi = np.full(len(me2.polygons), -1, np.int64)
        if "wc_src" in me2.attributes and len(me2.polygons):
            me2.attributes["wc_src"].data.foreach_get("value", src)
        if "wc_fi" in me2.attributes and len(me2.polygons):
            me2.attributes["wc_fi"].data.foreach_get("value", fi)
        bpy.data.meshes.remove(me2)
        from .tm import TM
        out = TM(V.reshape(-1, 3), F.reshape(-1, 3))
        return out, src[P], fi[P]
    except Exception:
        return None
    finally:
        for o_ in made:
            m_ = o_.data
            bpy.data.objects.remove(o_, do_unlink=True)
            if m_ is not None and m_.users == 0:
                bpy.data.meshes.remove(m_)


def _inside_grid(bvh, lo, h, dims, x0=None):
    """Diem luoi nam TRONG khoi kin: moi cot theo X ban MOT tia, dem chan / le giao diem (nhanh, khong sai dau phap
    tuyen o canh lom nhu cach 'diem gan nhat')."""
    from mathutils import Vector
    nx, ny, nz = dims
    xs = lo[0] + h * np.arange(nx)
    out = np.zeros(dims, bool)
    rnd = np.random.RandomState(7)
    d = Vector((1.0, 0.0, 0.0))
    far = h * (nx + 4) + (0.0 if x0 is None else float(lo[0] - x0))
    for j in range(ny):
        for k in range(nz):
            y = lo[1] + h * j + 1e-4 * h * rnd.rand()
            z = lo[2] + h * k + 1e-4 * h * rnd.rand()
            o = Vector((lo[0] - 2 * h if x0 is None else x0, y, z))   # tia phai bat dau NGOAI khoi
            hits = []
            for _ in range(200):
                hit = bvh.ray_cast(o, d, far)
                if hit[0] is None:
                    break
                hits.append(hit[0].x)
                o = hit[0] + d * (1e-6 * h + 1e-9)
            if len(hits) >= 2:
                cnt = np.searchsorted(np.asarray(hits), xs)
                out[:, j, k] = (cnt % 2) == 1
    return out


def _flood(allowed, seeds):
    """Lan 6 huong trong `allowed` tu `seeds` -> mat na cac o noi toi hat giong."""
    r = seeds & allowed
    while True:
        g = r.copy()
        g[1:] |= r[:-1]
        g[:-1] |= r[1:]
        g[:, 1:] |= r[:, :-1]
        g[:, :-1] |= r[:, 1:]
        g[:, :, 1:] |= r[:, :, :-1]
        g[:, :, :-1] |= r[:, :, 1:]
        g &= allowed
        if g.sum() == r.sum():
            return g
        r = g


def _decimate(V, F, target):
    """Giam mat khoi cat (marching tets ra ~4 tam giac / o) - collapse giu kin; hong thi giu ban goc."""
    import bpy
    from . import bl
    if len(F) <= target:
        return V, F
    me = bpy.data.meshes.new("_vs_dc")
    me.from_pydata(np.asarray(V).tolist(), [], np.asarray(F).tolist())
    me.update()
    ob = bpy.data.objects.new("_vs_dc", me)
    bpy.context.scene.collection.objects.link(ob)
    try:
        m = ob.modifiers.new("dc", "DECIMATE")
        m.ratio = float(target) / len(F)
        m.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        t2 = bl.tm_from_mesh(me2)
        bpy.data.meshes.remove(me2)
    except Exception:
        t2 = None
    finally:
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(me)
    if t2 is None or not len(t2.F) or not t2.is_closed():
        return V, F
    return t2.V, t2.F


def _harmonic(u, unknown, iters=VS_ITERS, tol=1e-5):
    """Giai Laplace (6 lang gieng) cho cac o `unknown`, cac o khac giu gia tri trong u (dieu kien bien) - CG."""
    unk = unknown.astype(np.float64)

    def nb(v):
        o = np.zeros_like(v)
        o[1:] += v[:-1]
        o[:-1] += v[1:]
        o[:, 1:] += v[:, :-1]
        o[:, :-1] += v[:, 1:]
        o[:, :, 1:] += v[:, :, :-1]
        o[:, :, :-1] += v[:, :, 1:]
        return o

    def A(v):
        return (6.0 * v - nb(v)) * unk

    b = nb(np.where(unknown, 0.0, u)) * unk
    x = 0.5 * unk
    r = b - A(x)
    p = r.copy()
    rs = float((r * r).sum())
    b2 = max(float((b * b).sum()), 1e-30)
    for _ in range(iters):
        Ap = A(p)
        al = rs / max(float((p * Ap).sum()), 1e-30)
        x += al * p
        r -= al * Ap
        rn = float((r * r).sum())
        if rn < tol * tol * b2:
            break
        p = r + (rn / rs) * p
        rs = rn
    return np.where(unknown, x, u)


def _tv(u, known, iters=VS_TV_ITERS):
    """MAT CAT NHO NHAT (lien tuc): min tong |grad u| voi u co dinh o `known`, 0 <= u <= 1 - Chambolle-Pock. Theo cong
    thuc dien tich (coarea) moi mat muc cua nghiem la mat ngan DIEN TICH NHO NHAT noi vong bien trong khoi: dau tron hai
    vong (duoi mu, o co) -> hai DIA chu khong phai ong thong qua loi dau (truong dieu hoa: dau thanh cai bat), giay -> dia
    ngang co chan, mieng va -> dia nong."""
    tau = sig = 0.28                                        # tau * sig * ||grad||^2 <= 1 (||grad||^2 <= 12)
    g = u.copy()
    px, py, pz = np.zeros_like(u), np.zeros_like(u), np.zeros_like(u)
    ub = u.copy()
    free = ~known
    for _ in range(iters):
        gx = np.zeros_like(u)
        gy = np.zeros_like(u)
        gz = np.zeros_like(u)
        gx[:-1] = ub[1:] - ub[:-1]
        gy[:, :-1] = ub[:, 1:] - ub[:, :-1]
        gz[:, :, :-1] = ub[:, :, 1:] - ub[:, :, :-1]
        px += sig * gx
        py += sig * gy
        pz += sig * gz
        nr = np.maximum(1.0, np.sqrt(px * px + py * py + pz * pz))
        px /= nr
        py /= nr
        pz /= nr
        dv = px.copy()
        dv[1:] -= px[:-1]
        dv += py
        dv[:, 1:] -= py[:, :-1]
        dv += pz
        dv[:, :, 1:] -= pz[:, :, :-1]
        un = np.clip(u + tau * dv, 0.0, 1.0)
        un[known] = g[known]
        ub = 2.0 * un - u
        u = un
    return np.where(free, u, g)


def _uf_labels(n, pairs):
    """Nhan thanh phan lien thong (union-find) cho n phan tu voi cac cap noi `pairs` [k,2]."""
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a_, b_ in pairs:
        ra, rb = find(int(a_)), find(int(b_))
        if ra != rb:
            par[ra] = rb
    return np.array([find(i) for i in range(n)])


def _loops(t, mask):
    """Vong bien cua vung mask -> (nhom canh bien theo vong, dao vung A cua moi vong, nhan "phia A" tren MAT cua tung
    vong) hoac None neu co vong khong chia doi be mat (khoi co quai / lo xuyen)."""
    E, _ = t.edges()
    ef, _ = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    bd = np.zeros(len(E), bool)
    bd[ok] = mask[ef[ok, 0]] != mask[ef[ok, 1]]
    be = np.where(bd)[0]
    if not len(be):
        return None
    vg = _uf_labels(len(t.V), E[be])                      # canh bien noi nhau qua dinh = mot vong (nhom)
    g_of = vg[E[be, 0]]
    groups = [be[g_of == g] for g in np.unique(g_of)]
    inner = ok & ~bd & mask[np.maximum(ef[:, 0], 0)] & mask[np.maximum(ef[:, 1], 0)]
    isl = _uf_labels(len(t.F), ef[inner])                 # dao A: mat A noi qua canh khong phai bien
    out = []
    for ge in groups:
        fa = np.where(mask[ef[ge, 0]], ef[ge, 0], ef[ge, 1])
        island = int(np.bincount(isl[fa]).argmax()) if len(fa) else -1
        cut = np.zeros(len(E), bool)
        cut[ge] = True
        comp = _uf_labels(len(t.F), ef[ok & ~cut])
        ca = int(np.bincount(comp[fa]).argmax())
        side = comp == ca
        fb = np.where(mask[ef[ge, 0]], ef[ge, 1], ef[ge, 0])
        if side[fb].mean() > 0.5:                         # vong khong chia doi be mat
            return None
        out.append((ge, island, side))
    return E, out


def cutter(t, mask, log=None):
    """Khoi cat C (V, F) cho vung mat `mask` cua khoi kin t, kem thong tin do.
    MOI VONG BIEN bit bang MOT MANG rieng (dien tich nho nhat, nam trong khoi) - nhu nhat cat phang cu ve y nghia (dau =
    khoi giua dia duoi mu va dia o co), khac cho mang cong / di vong theo hinh khoi chu khong dam xuyen be mat. Giai tren
    luoi con quanh vong (bien luoi con tu do), ngoai luoi con lay theo phia be mat gan nhat roi sua theo lien thong (khong
    con coc cam sau duoi mieng va). Gop: giao cac vong cua mot dao A, hop cac dao."""
    from mathutils import Vector
    from mathutils.kdtree import KDTree
    if not mask.any() or mask.all():
        return None
    lp = _loops(t, mask)
    if lp is None:
        if log:
            log("  (chia the tich: co vong bien khong chia doi be mat - bo)")
        return None
    E, loops = lp
    # luoi CHI phu quanh vung A (khoi cat khong vuot ra ngoai bao cua mat A + nap): vung nho -> o min (dai ong quan 1,4%
    # tren luoi ca than bi lam mo mat)
    Va = t.V[np.unique(t.F[mask].ravel())]
    lo, hi = Va.min(0), Va.max(0)
    size = float((hi - lo).max())
    h = size / VS_N
    margin = 3 * h
    ext = (hi - lo) + 2 * margin
    while np.prod(np.ceil(ext / h) + 1) > VS_MAXPTS:
        h *= 1.1
        margin = 3 * h
        ext = (hi - lo) + 2 * margin
    lo2 = lo - margin
    dims = tuple(int(x) for x in (np.ceil(ext / h) + 1))
    bA = _bvh(t, np.where(mask)[0])
    bB = _bvh(t, np.where(~mask)[0])
    bT = _bvh(t, np.arange(len(t.F)))
    gi = np.stack(np.meshgrid(*[np.arange(d) for d in dims], indexing="ij"), axis=-1).reshape(-1, 3)
    G = lo2 + h * gi
    inside = _inside_grid(bT, lo2, h, dims, x0=float(t.V[:, 0].min()) - 1.0).ravel()
    band = VS_BAND * h
    nf = np.empty(len(G), np.int64)
    dT = np.empty(len(G))
    for n, p in enumerate(G):
        hit = bT.find_nearest(Vector(p))
        nf[n], dT[n] = hit[2], hit[3]
    near = dT <= band
    ramp = np.full(len(G), np.nan)
    L = 4 * h
    for n in np.where(near)[0]:
        v = Vector(G[n])
        ha = bA.find_nearest(v, L)
        hb = bB.find_nearest(v, L)
        dA = ha[3] if ha[0] is not None else L
        dB = hb[3] if hb[0] is not None else L
        ramp[n] = 0.5 + min(0.5, max(-0.5, (dB - dA) / (3 * h)))   # doc tron qua duong bien A | B
    # o dai sat be mat gan vong nao (doc tron chi dung cho vong do)
    S, gid = [], []
    for k, (ge, _, _) in enumerate(loops):
        P0, P1 = t.V[E[ge, 0]], t.V[E[ge, 1]]
        S += [P0, P1, 0.5 * (P0 + P1)]
        gid += [k] * (3 * len(ge))
    S = np.concatenate(S)
    kd = KDTree(len(S))
    for i, q in enumerate(S):
        kd.insert(Vector(q), i)
    kd.balance()
    gid = np.asarray(gid)
    nl = np.full(len(G), -1)
    for n in np.where(near)[0]:
        _, i, d = kd.find(Vector(G[n]))
        if d < 3 * h:
            nl[n] = gid[i]
    shp = dims
    nearg = near.reshape(shp)
    by_island = {}
    for k, (ge, island, side) in enumerate(loops):
        lab = side[nf].astype(np.float64)                    # phia be mat gan nhat (ngoai luoi con)
        fix = near & (nl == k)
        lab[fix] = ramp[fix]
        u = lab.reshape(shp)
        # luoi con quanh vong
        Pv = t.V[np.unique(E[ge].ravel())]
        pad = 0.3 * float(np.linalg.norm(Pv.max(0) - Pv.min(0))) + 6 * h
        i0 = np.maximum(np.floor((Pv.min(0) - pad - lo2) / h).astype(int), 0)
        i1 = np.minimum(np.ceil((Pv.max(0) + pad - lo2) / h).astype(int) + 1, np.array(shp))
        sl = tuple(slice(int(a_), int(b_)) for a_, b_ in zip(i0, i1))
        sub = u[sl].copy()
        kn = nearg[sl] | ~inside.reshape(shp)[sl]
        sub = _harmonic(sub, ~kn)
        sub = _tv(sub, kn)
        u[sl] = sub
        # sua theo lien thong: vung > 0,5 khong noi toi dai be mat phia A -> 0 (coc duoi mieng va); nguoc lai -> 1
        hi_ = u > 0.5
        r1 = _flood(hi_, hi_ & nearg)
        lo_ = ~hi_
        seed0 = lo_ & nearg
        seed0[0, :, :] = seed0[-1, :, :] = seed0[:, 0, :] = seed0[:, -1, :] = seed0[:, :, 0] = seed0[:, :, -1] = True
        r0 = _flood(lo_, seed0 & lo_)
        u = np.where(hi_ & ~r1, 0.0, np.where(lo_ & ~r0, 1.0, u))
        by_island[island] = u if island not in by_island else np.minimum(by_island[island], u)
    u = np.max(np.stack(list(by_island.values())), axis=0)
    u[(~inside & ~near).reshape(shp)] = 0.0                   # ngoai khoi: C chi om sat be mat A
    u = _blur(u, VS_BLUR)
    phi = 0.5 - u                                             # phi < 0 = trong khoi cat (phia A)
    phi[0, :, :] = phi[-1, :, :] = phi[:, 0, :] = phi[:, -1, :] = phi[:, :, 0] = phi[:, :, -1] = 0.5
    # bo BOT rieng sau khi gop (vung C khong noi toi dai be mat A / vung ngoai C khong noi toi dai B hay bien luoi)
    nearA = nearg & (ramp.reshape(shp) > 0.5)
    nearB = nearg & ~(ramp.reshape(shp) > 0.5)
    neg = phi < 0
    phi[neg & ~_flood(neg, neg & nearA)] = 0.5
    pos = ~(phi < 0)
    sb = pos & nearB
    sb[0, :, :] = sb[-1, :, :] = sb[:, 0, :] = sb[:, -1, :] = sb[:, :, 0] = sb[:, :, -1] = True
    phi[pos & ~_flood(pos, sb & pos)] = -0.5
    r = marching_tets(phi, lo2, h)
    if r is None:
        return None
    n0 = len(r[1])
    Vc, Fc = _decimate(r[0], r[1], VS_CUT_FACES)
    return Vc, Fc, dict(h=h, dims=dims, n0=n0, loops=len(loops))


def split(t, mask, cut_id, log=None):
    """Tach khoi kin t theo vung mat `mask` bang khoi cat the tich. -> (list TM phan A, list TM phan B) hoac None."""
    from .tm import TM
    if not t.is_closed() or mask.all() or not mask.any():
        return None
    c = cutter(t, mask, log)
    if c is None:
        return None
    Vc, Fc, info = c
    ar = t.face_areas()
    out = None
    tries = [(Vc, Fc, False), (Vc, Fc, True)]
    for Vk, Fk, rob in tries:
        out = []
        for op in ("INTERSECT", "DIFFERENCE"):
            r = _boolean(t, Vk, Fk, op, robust=rob)
            res = r[0] if r is not None else None
            if res is None or not len(res.F) or not res.is_closed():
                if log:
                    log("  (chia the tich: Boolean %s%s ra khoi ho)" % (op, " (tu cat)" if rob else ""))
                out = None
                break
            src, fi = r[1], r[2]
            fromC = (src == 1) | (fi < 0)
            fi2 = np.where(fromC, 0, fi)
            res.col = np.where(fromC, -1, t.col[fi2])
            res.cap = np.where(fromC, cut_id, t.cap[fi2])
            out.append(res)
        if out:
            break
    if not out:
        return None
    A, B = out
    a_ar, b_ar = A.face_areas(), B.face_areas()
    surfA = float(a_ar[A.cap != cut_id].sum())
    surfB = float(b_ar[B.cap != cut_id].sum())
    mA, mB = float(ar[mask].sum()), float(ar[~mask].sum())
    kA, kB = surfA / max(mA, 1e-30), surfB / max(mB, 1e-30)
    if not (VS_KEEP[0] <= kA <= VS_KEEP[1] and VS_KEEP[0] <= kB <= VS_KEEP[1]):
        if log:
            log("  (chia the tich: dien tich lech mask %.2f / %.2f - bo)" % (kA, kB))
        return None
    pa = A.split_components(min_faces=4)
    pb = B.split_components(min_faces=4)
    if not pa or not pb or not all(x.is_closed() for x in pa + pb):
        return None
    if log:
        log("  (chia the tich: %d vong, luoi %s o %.3f, khoi cat %d -> %d mat)" % (
            info["loops"], info["dims"], info["h"], info["n0"], len(Fc)))
    return pa, pb
