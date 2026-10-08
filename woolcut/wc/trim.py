"""CAT TIA PHAN DU cua part (2026-10-08, nguoi dung: "cac part duoc tach ra thi duoc cat tia cac mesh bi du va bo kin lai
de tao thanh part dep... vi du banh xe ma co phan du thi nen cat di").

Phan du thuong gap tren part Tripo (xe may, gau dau bep): GAI / VAT MONG moc ra khoi khoi chinh (banh truoc co 2 gai cua
chan bun, phuoc co vat nhau o dau), VIEN RANG CUA mong o mep tam. Chung deu MONG hon han khoi chinh -> do do day tung
mat (ban tia vao trong, cham mat doi dien NGUOC huong trong tau) -> cum mat mong nho (< MAX_COMP dien tich) = du -> bo,
va kin TAI CHO (prep.local_close), lam muot nhe vung va. Phan con lai giu NGUYEN. Part ma ban than la tam mong (> MAX_THIN
dien tich mong: la, canh, vanh mu) khong dung."""
import numpy as np
from .tm import TM

THIN_REL = 0.012          # do day < 1.2% co model (co 10 -> 0.12) = mong
MAX_THIN = 0.35           # part > 35% dien tich mong = tam mong -> khong cat
MAX_COMP = 0.25           # mot cum mong > 25% dien tich part -> khong phai "du", giu


def thin_mask(t, tau):
    """Mat MONG: tia tu tam mat vao trong (-n) cham mat doi dien huong nguoc (sheet) trong khoang tau."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)
    C = t.face_centers()
    N = t.face_normals()
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-20)[:, None]
    eps = 1e-5 * max(float((t.V.max(0) - t.V.min(0)).max()), 1e-9)
    out = np.zeros(len(t.F), bool)
    for k in range(len(t.F)):
        n = Vector(N[k])
        loc, nh, idx, d = bvh.ray_cast(Vector(C[k]) - n * eps, -n, tau)
        if loc is not None and idx != k and nh is not None and nh.dot(n) < -0.3:
            out[k] = True
    return out


def thickness(t, maxd):
    """Do day tung mat: khoang cach tia vao trong (-n) toi mat doi dien NGUOC huong (inf neu khong cham trong maxd)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)
    C = t.face_centers()
    N = t.face_normals()
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-20)[:, None]
    eps = 1e-5 * max(float((t.V.max(0) - t.V.min(0)).max()), 1e-9)
    out = np.full(len(t.F), np.inf)
    for k in range(len(t.F)):
        n = Vector(N[k])
        loc, nh, idx, d = bvh.ray_cast(Vector(C[k]) - n * eps, -n, maxd)
        if loc is not None and idx != k and nh is not None and nh.dot(n) < -0.3:
            out[k] = d
    return out


def thin_relative(t, rel=0.5):
    """Mat mong hon rel x do day KHOI CHINH cua part (phan vi 75% do day theo dien tich) - dung khi Claude da xac nhan
    part co phan thua (vat nhau cua bo phan khac dinh sang ong phuoc: day hon nguong tuyet doi 1,2% nhung mong hon han
    ong)."""
    size = float((t.V.max(0) - t.V.min(0)).max()) or 1.0
    th = thickness(t, size)
    A = t.face_areas()
    ok = np.isfinite(th)
    if ok.sum() < 10:
        return np.zeros(len(t.F), bool), 0.0
    o_ = np.argsort(th[ok])
    cw = np.cumsum(A[ok][o_]) / A[ok].sum()
    main = float(th[ok][o_][min(len(o_) - 1, np.searchsorted(cw, 0.75))])
    return th < rel * main, main


def _face_comps(t, mask):
    """Thanh phan lien thong (qua canh) cua cac mat trong mask -> danh sach mang chi so mat."""
    ef, _ = t.edge_faces()
    par = {int(i): int(i) for i in np.where(mask)[0]}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    for a, b in ef[ok]:
        a, b = int(a), int(b)
        if a in par and b in par:
            ra, rb = find(a), find(b)
            if ra != rb:
                par[ra] = rb
    comps = {}
    for f in par:
        comps.setdefault(find(f), []).append(f)
    return [np.array(v) for v in comps.values()]


OPEN_REL = 0.006          # phep MO: co roi no 0.6% co model (co 10 -> 0.06) - xoa moi thu mong hon ~0.12
EXCESS_MIN = 0.004        # phan du (dien tich xa khoi mo) < 0.4% -> coi nhu sach, giu nguyen
EXCESS_MAX = 0.25         # > 25% -> ban than la chi tiet mong (la, vat ao, quai) -> khong mo, chi ghi chu


def opening(t, r):
    """Phep MO hinh hoc: co vao r roi no ra r (voxel, shell._offset) -> khoi sach (gai, vat, manh nhon mong hon 2r bien
    mat; khoi chinh giu hinh, goc bo tron ban kinh ~r). None neu hong."""
    from . import shell
    obs = []
    try:
        a = shell._offset(t, -r, "_mo1")
        obs.append(a)
        te = shell._main(shell._evaluated_tm(a))
        if te is None or len(te.F) < 20:
            return None
        b = shell._offset(te, r, "_mo2")
        obs.append(b)
        to = shell._main(shell._evaluated_tm(b))
        return to if to is not None and to.is_closed() else None
    except Exception:
        return None
    finally:
        shell._drop(*obs)


def _decimate_closed(t, target):
    """Giam mat (collapse) ve ~target, van KIN; khong duoc thi giu nguyen."""
    if len(t.F) <= target:
        return t
    import bpy
    from . import shell
    ob = shell._obj(t, "_giam")
    try:
        d = ob.modifiers.new("d", "DECIMATE")
        d.decimate_type = "COLLAPSE"
        d.use_collapse_triangulate = True
        for k in (1.0, 1.4, 2.0):
            d.ratio = min(1.0, k * target / len(t.F))
            t2 = shell._evaluated_tm(ob)
            if t2.is_closed():
                return t2
    except Exception:
        pass
    finally:
        shell._drop(ob)
    return t


def excess_frac(t, core, r):
    """Phan dien tich be mat t nam XA khoi `core` (> 1.5 r) = phan du ma phep mo da xoa."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bc = BVHTree.FromPolygons([Vector(v) for v in core.V], [tuple(int(i) for i in f) for f in core.F], all_triangles=True)
    A = t.face_areas()
    far = np.array([(bc.find_nearest(Vector(c))[3] or 0.0) > 1.5 * r for c in t.face_centers()])
    return float(A[far].sum() / max(A.sum(), 1e-12))


def clean_part(t, model_size=10.0, log=None, open_rel=OPEN_REL, excess_max=EXCESS_MAX, trim_max=MAX_COMP):
    """CAT TIA + MESH LAI (nguoi dung 2026-10-08: "chi tiet thua nen duoc cat bo di va mesh lai"): (1) bo cum mong, va tai
    cho (giu be mat); (2) con du (phep mo xoa them > EXCESS_MIN dien tich) -> thay bang khoi da MO (mesh lai, sach).
    Phan du > EXCESS_MAX = chi tiet mong that -> khong dung. -> (TM, mo ta, muc: "" | "cat" | "mesh lai" | "mong")."""
    t1, m1 = trim(t, model_size, max_comp=trim_max)
    if m1.startswith("tam mong"):
        return t, m1, "mong"
    base = t1 if m1 and not m1.endswith("giu") else t
    if not base.is_closed():
        return t1, m1, "cat" if base is t1 and m1 else ""
    r = open_rel * model_size
    core = opening(base, r)
    if core is None:
        return base, m1, "cat" if base is t1 and m1 else ""
    ex = excess_frac(base, core, r)
    if ex < EXCESS_MIN:
        return base, m1, "cat" if base is t1 and m1 else ""
    if ex > excess_max:
        return base, (m1 + "; " if m1 else "") + "du %.0f%% - chi tiet mong, giu" % (100 * ex), "mong"
    core = _decimate_closed(core, max(600, int(1.5 * len(base.F))))     # voxel min (o r/3) ra 26-37k mat / part
    if len(getattr(t, "col", [])) == len(t.F):
        from . import prep
        prep._copy_col(t, core)
    msg = (m1 + "; " if m1 else "") + "mo r=%.2f bo %.1f%% du -> mesh lai %d mat" % (r, 100 * ex, len(core.F))
    if log:
        log("  [cat tia] " + msg)
    return core, msg, "mesh lai"


def _rebuild(t, model_size):
    """Lo de lai sau khi bo vat lon qua to de va tai cho -> MESH LAI (voxel) phan con lai, giam mat ve ~co cu."""
    from . import prep
    t2 = prep.rebuild(t, "cat tia", log=lambda *_: None)
    if t2 is None or not t2.is_closed():
        return None
    return _decimate_closed(t2, max(600, int(1.3 * len(t.F))))


AUTO_COMP = 0.03         # tu dong khi cat (khong hoi Claude): chi bo GAI mong nho <= 3% dien tich part (gai banh xe
                          # 1,3%); vat lon hon (phuoc 6-16%) de Claude xem ca model quyet "trim" - vanh mu / tai mong
                          # la chi tiet that


def trim(t, model_size=10.0, tau_rel=THIN_REL, log=None, max_comp=MAX_COMP, relative=None):
    """-> (TM moi hoac t, mo ta). Bo cum mat mong nho, va kin tai cho, lam muot vung va. relative=0.5: nguong = nua do day
    khoi chinh cua part (Claude da xac nhan co phan thua) thay cho nguong tuyet doi."""
    from . import prep
    if len(t.F) < 40:
        return t, ""
    if relative:
        thin, main = thin_relative(t, relative)
    else:
        thin = thin_mask(t, tau_rel * model_size)
    A = t.face_areas()
    tot = float(A.sum()) or 1.0
    frac = float(A[thin].sum()) / tot
    if frac <= 0.0:
        return t, ""
    if frac > (0.6 if relative else MAX_THIN):
        return t, "tam mong %.0f%% - giu" % (100 * frac)
    drop = []
    for c in _face_comps(t, thin):
        a = float(A[c].sum()) / tot
        if a <= max_comp and len(c) >= 3:
            drop.append(c)
    if not drop:
        return t, ""
    kill = np.zeros(len(t.F), bool)
    for c in drop:
        kill[c] = True
    t3, how = _cut(t, kill, model_size, big=bool(relative))
    if t3 is None:
        return t, how
    msg = "bo %d cum mong (%.1f%% dien tich), %d -> %d mat%s" % (
        len(drop), 100 * float(A[kill].sum()) / tot, len(t.F), len(t3.F), how)
    if log:
        log("  [cat tia] " + msg)
    return t3, msg


def _cut(t, kill, model_size, big=False):
    """Bo cac mat kill, giu thanh phan lon nhat, go RANG CUA o mep lo (mat co >= 2 canh bien), VA KIN tai cho (big: lo
    vai nghin canh), lam muot mieng va (be mat goc giu yen). -> (TM, "") hoac (None, ly do). Khong voxel lai luoi ho
    (ra vo rong hai lop - mat na xe may 2026-10-08): khong va duoc thi repair dung lai tu than chinh."""
    from . import prep
    keep = ~kill
    for _ in range(4):
        t2 = t.subset(np.where(keep)[0])
        _, cnt = t2.edge_faces()
        FE = t2.edges()[1]
        ears = (cnt[FE] == 1).sum(1) >= 2
        if not ears.any():
            break
        keep[np.where(keep)[0][ears]] = False
    t2 = t.subset(np.where(keep)[0])
    comps = t2.split_components()                   # vun con lai sau khi bo vat (manh treo) -> chi giu khoi lon nhat
    if len(comps) > 1:
        t2 = max(comps, key=lambda c: float(c.face_areas().sum()))
    t3 = prep.local_close(t2, max_loop=6000 if big else 400)
    if t3 is None:
        return None, "va kin hong - giu"
    t3 = relax_fill(t3, t2)
    if len(getattr(t, "col", [])) == len(t.F):
        prep._copy_col(t, t3)
    return t3, ""


def relax_fill(t3, orig, iters=30):
    """Mieng VA (dinh khong nam tren be mat goc) -> chia nho tam giac quat roi lam muot voi vien giu yen: mat va cong
    deu nhu mang cang, khong thanh hinh SAO / chop nhon (quat ve tam lo: than sau xe may 2026-10-08). Sua tai cho t3."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from . import prep
    import bmesh
    bo = BVHTree.FromPolygons([Vector(v) for v in orig.V], [tuple(int(i) for i in f) for f in orig.F], all_triangles=True)
    eps = 1e-6 * max(float((orig.V.max(0) - orig.V.min(0)).max()), 1e-9)

    def on_orig(V):
        return np.array([(bo.find_nearest(Vector(v))[3] or 0.0) < eps for v in V])
    fixed = on_orig(t3.V)
    if fixed.all():
        return t3
    bm = prep._tm_bm(t3)
    bm.verts.ensure_lookup_table()
    new = [bm.verts[i] for i in np.where(~fixed)[0]]
    edges = list({e for v in new for f in v.link_faces for e in f.edges})
    long_ = np.median([e.calc_length() for e in bm.edges]) * 2.0
    edges = [e for e in edges if e.calc_length() > long_ or any(not fixed[x.index] for x in e.verts)]
    if edges:
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=2, use_grid_fill=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    t4 = prep._bm_tm(bm)
    bm.free()
    if not t4.is_closed():
        return t3
    t4.taubin(iters=iters, keep=on_orig(t4.V))
    return t4


VOX_N = 72                # o voxel theo canh dai nhat cua part (do day bang phep co tren luoi)
OPEN_K = 0.45             # ban kinh MO = 0.45 x ban kinh cho day nhat cua part
EX_MIN = 0.02             # phan du < 2% dien tich = sach
DIST_MAX = 30             # do khoang cach toi than chinh toi da (o)
EX_MAX = 0.5              # > 50% -> ca part la vat / manh vun, cat khong cuu duoc -> XAU (an)


def voxelize(t, n=VOX_N):
    """Khoi DAC cua luoi kin tren luoi o deu (bau 2/3 truc theo tia chan le - vat nhau tu cat / phap tuyen lat van dung).
    -> (occ bool [X,Y,Z], goc lo, canh o h)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    lo0, hi = t.V.min(0), t.V.max(0)
    h = float((hi - lo0).max()) / n
    lo = lo0 - 2 * h
    dims = (np.ceil((hi - lo) / h).astype(int) + 3)
    bvh = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)
    votes = np.zeros(tuple(dims), np.int8)
    jit = np.array([0.0137, 0.0291, 0.0419]) * h       # lech khoi canh / dinh chung (tia cham dung canh dem 2 lan)
    step = 1e-5 * h
    for ax in range(3):
        a1, a2 = [k for k in range(3) if k != ax]
        cz = lo[ax] + (np.arange(dims[ax]) + 0.5) * h
        d = [0.0, 0.0, 0.0]
        d[ax] = 1.0
        d = Vector(d)
        L = float(dims[ax] * h + 2 * h)
        o = np.zeros(3)
        for i in range(dims[a1]):
            for j in range(dims[a2]):
                o[a1] = lo[a1] + (i + 0.5) * h + jit[a1]
                o[a2] = lo[a2] + (j + 0.5) * h + jit[a2]
                o[ax] = lo[ax] - h
                p = Vector(o)
                hits = []
                while len(hits) < 200:
                    loc, _, _, dist = bvh.ray_cast(p, d, L)
                    if loc is None:
                        break
                    hits.append(loc[ax])
                    p = loc + d * step
                if len(hits) < 2:
                    continue
                inside = np.searchsorted(np.array(hits), cz) % 2 == 1
                if ax == 0:
                    votes[:, i, j] += inside
                elif ax == 1:
                    votes[i, :, j] += inside
                else:
                    votes[i, j, :] += inside
    return votes >= 2, lo, h


def _shift(m, ax, s):
    out = np.zeros_like(m)
    src, dst = [slice(None)] * 3, [slice(None)] * 3
    if s > 0:
        dst[ax], src[ax] = slice(1, None), slice(None, -1)
    else:
        dst[ax], src[ax] = slice(None, -1), slice(1, None)
    out[tuple(dst)] = m[tuple(src)]
    return out


def _morph(m, grow, cube):
    """Mot buoc co (grow=False) / no: chu thap 6 lang gieng, hoac khoi 3x3x3 (tach theo truc)."""
    op = np.logical_or if grow else np.logical_and
    out = m
    for ax in range(3):
        base = out if cube else m
        out = op(op(out, _shift(base, ax, 1)), _shift(base, ax, -1))
    return out


def _steps(m, k, grow):
    for s in range(k):
        m = _morph(m, grow, cube=bool(s % 2))       # xen ke chu thap / khoi -> gan hinh cau (bat giac)
    return m


def excess_voxel(t, n=VOX_N, k=OPEN_K):
    """Phan DU cua part do bang phep MO tren khoi dac voxel: co r roi no r (r = k x ban kinh cho day nhat) -> moi thu
    mong hon han than chinh (vat nhau, gai, kim) bien mat; mat nam ngoai vung (than da mo + 2 o) = du.
    -> (mask mat du hoac None, dict thong tin)."""
    if len(t.F) < 40 or not t.is_closed():
        return None, {"why": "ho / qua it mat"}
    occ, lo, h = voxelize(t, n)
    if occ.sum() < 50:
        return None, {"why": "khoi rong"}
    R, m = 0, occ
    while m.any() and R < n:
        m = _morph(m, False, cube=bool(R % 2))
        R += 1
    ro = int(round(k * R))
    if ro < 2:
        return None, {"why": "mong deu (day %d o)" % R, "R": R}
    core = _steps(_steps(occ, ro, False), ro, True) & occ
    # khoang cach (so o) tu than da mo toi tung mat: no dan tung buoc
    D = np.full(occ.shape, 255, np.uint8)
    D[core] = 0
    m = core
    for s in range(1, DIST_MAX + 1):
        m2 = _morph(m, True, cube=bool(s % 2))
        D[m2 & ~m] = s
        m = m2
    C = t.face_centers()
    idx = np.clip(np.floor((C - lo) / h).astype(int), 0, np.array(occ.shape) - 1)
    df = D[idx[:, 0], idx[:, 1], idx[:, 2]].astype(np.int64)
    # goc / canh hop bi phep mo bo tron lui vao ~0.4-0.7 ro; vanh banh, mep vo nho ra vai o -> khong phai du. DU = cum
    # mat nam ngoai vung do VA nho ra xa (vat, kim): >= ro + 3 o.
    zone = max(2, int(np.ceil(0.8 * ro)))
    far = df > zone
    kill = np.zeros(len(t.F), bool)
    ncomp = 0
    for c in _face_comps(t, far):
        if df[c].max() >= max(zone + 3, ro + 3):
            kill[c] = True
            ncomp += 1
    if kill.any():
        # lan tu cum du vao cac mat lien ke con nho ra >= 2 o -> cat sat goc, khong de chop rang cua
        ef, _ = t.edge_faces()
        ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
        pairs = ef[ok]
        low = df >= 2
        while True:
            a, b = pairs[:, 0], pairs[:, 1]
            grow = (kill[a] & ~kill[b] & low[b])
            grow2 = (kill[b] & ~kill[a] & low[a])
            add = np.concatenate([b[grow], a[grow2]])
            if not len(add):
                break
            kill[add] = True
    return kill, {"R": R, "ro": ro, "h": h, "thick": 2 * R * h, "comps": ncomp, "core": core, "lo": lo, "D": D,
                  "zone": zone}


def far_frac(t2, info):
    """Ti le dien tich t2 nam XA than chinh cua ban goc (> vung do): chop rang cua / gai con sot sau khi sua."""
    D, lo, h = info["D"], info["lo"], info["h"]
    idx = np.clip(np.floor((t2.face_centers() - lo) / h).astype(int), 0, np.array(D.shape) - 1)
    df = D[idx[:, 0], idx[:, 1], idx[:, 2]].astype(np.int64)
    A = t2.face_areas()
    return float(A[df > info["zone"]].sum() / max(A.sum(), 1e-12))


def jag(t, deg=60.0, faces=None):
    """Do LOM CHOM: ti le chieu dai canh co goc gap > deg (vat nhau, rang cua, chop sao). faces: chi xet canh giua
    cac mat nay."""
    ef, _ = t.edge_faces()
    E = t.edges()[0]
    N = t.face_normals()
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-20)[:, None]
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    if faces is not None:
        ok &= faces[np.maximum(ef[:, 0], 0)] & faces[np.maximum(ef[:, 1], 0)]
    if not ok.any():
        return 0.0
    ang = np.degrees(np.arccos(np.clip((N[ef[ok, 0]] * N[ef[ok, 1]]).sum(1), -1, 1)))
    L = np.linalg.norm(t.V[E[ok, 0]] - t.V[E[ok, 1]], axis=1)
    return float(L[ang > deg].sum() / max(L.sum(), 1e-12))


def _grid_tm(occ, lo, h):
    """Khoi o voxel -> luoi mat vuong (moi mat o giap ngoai = 2 tam giac)."""
    X, Y, Z = occ.shape
    vid = lambda i, j, k: (i * (Y + 1) + j) * (Z + 1) + k
    F = []
    for ax in range(3):
        for s in (1, -1):
            face = occ & ~_shift(occ, ax, -s)          # o dac ma lang gieng phia s rong
            I = np.argwhere(face)
            if not len(I):
                continue
            base = I.copy()
            if s > 0:
                base[:, ax] += 1
            u, v = [a for a in range(3) if a != ax]
            c = [base.copy() for _ in range(4)]
            c[1][:, u] += 1
            c[2][:, u] += 1
            c[2][:, v] += 1
            c[3][:, v] += 1
            ids = [vid(q[:, 0], q[:, 1], q[:, 2]) for q in c]
            q = np.stack(ids, 1)
            # u x v = +ax khi (u, v) = (truc ke tiep, truc sau nua) theo vong; nguoc lai dao chieu
            pos = ((u - ax) % 3 == 1)
            if (s > 0) != pos:
                q = q[:, ::-1]
            F.append(q[:, [0, 1, 2]])
            F.append(q[:, [0, 2, 3]])
    F = np.concatenate(F)
    used, inv = np.unique(F.ravel(), return_inverse=True)
    k = used % (Z + 1)
    j = (used // (Z + 1)) % (Y + 1)
    i = used // ((Y + 1) * (Z + 1))
    V = lo + np.stack([i, j, k], 1) * h
    return TM(V, inv.reshape(-1, 3))


def remesh_core(t, kill, info, model_size=10.0):
    """MESH LAI tu than da MO (excess_voxel): khoi o -> voxel remesh min -> lam muot -> BAM lai be mat goc (phan khong
    du) o nhung cho cach < 1,5 o: giu chi tiet goc, cho vat / gai cu thanh mat cong tron. -> TM kin hoac None."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from . import bl, prep
    h = info["h"]
    blocky = _grid_tm(info["core"], info["lo"], h)
    t2 = bl.voxel_rebuild(blocky, voxel=0.75 * h)
    if t2 is None:
        return None
    comps = t2.split_components()
    if len(comps) > 1:
        t2 = max(comps, key=lambda c: abs(c.volume()))
    t2.taubin(iters=12)
    keepF = np.where(~kill)[0]
    bo = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in t.F[f]) for f in keepF], all_triangles=True)
    V = t2.V.copy()
    for i, v in enumerate(V):
        loc, _, _, d = bo.find_nearest(Vector(v), 1.5 * h)
        if loc is not None:
            V[i] = loc[:]
    t2.V = V
    t2._E = None
    t2.taubin(iters=2)
    t2 = _decimate_closed(t2, max(600, int(1.2 * len(t.F))))
    if not t2.is_closed():
        return None
    if len(getattr(t, "col", [])) == len(t.F):
        prep._copy_col(t, t2)
    return t2


FAR_OK = 0.01             # ban sua con <= 1% dien tich xa than chinh (phuoc trai 1,2%: con mau vat)
THIN_OK = 0.03            # ban sua mong hon (gai, rang cua) be mat goc giu lai toi da 3% dien tich
JAG_OK = 0.08             # va goc gap > 60 do tren <= 8% chieu dai canh (nap ong vuong goc la binh thuong)


def _thin_frac(t, tau, faces=None):
    A = t.face_areas()
    th = thin_mask(t, tau)
    if faces is not None:
        A, th = A[faces], th[faces]
    return float(A[th].sum() / max(A.sum(), 1e-12))


def _good(t2, t, kill, base, info):
    """Ban sua chap nhan duoc: kin, con >= 40% dien tich, het phan xa than chinh, khong them GAI / RANG CUA mong (do mong
    < ban kinh mo so voi be mat goc giu lai), khong nhau nat."""
    if t2 is None or not t2.is_closed():
        return False, "ho"
    a2, a = float(t2.face_areas().sum()), float(t.face_areas()[~kill].sum())
    if a2 < 0.4 * a:
        return False, "mat %.0f%% dien tich" % (100 * (1 - a2 / max(a, 1e-12)))
    f = far_frac(t2, info)
    if f > FAR_OK:
        return False, "con %.1f%% xa than" % (100 * f)
    th = _thin_frac(t2, base["tau"])
    if th > base["thin0"] + THIN_OK:
        return False, "gai mong %.0f%% (goc %.0f%%)" % (100 * th, 100 * base["thin0"])
    j2 = jag(t2)
    if j2 > max(JAG_OK, 2.0 * base["j0"]):
        return False, "nhau %.3f" % j2
    return True, "xa %.1f%%, mong %.0f%%, nhau %.3f" % (100 * f, 100 * th, j2)


def repair(t, model_size=10.0, log=None, ex_min=EX_MIN, ex_max=EX_MAX):
    """SUA PART XAU (nguoi dung 2026-10-08: "tool tu detect cac part xau va sua lai hoac an di"; "chi tiet thua nen cat
    bo va mesh lai"): phan DU = vat nhau / kim / gai mong hon han than chinh (excess_voxel). Thu (1) CAT phan du, va kin,
    lam muot mieng va - be mat con lai giu nguyen; khong dat (lom chom, con du) thi (2) MESH LAI tu than da mo, bam lai
    be mat goc. Ca hai khong dat -> "xau" (nen an).
    -> (TM, mo ta, muc): "" sach / khong do duoc | "cat" | "mesh lai" | "xau"."""
    kill, info = excess_voxel(t)
    if kill is None:
        return t, info.get("why", ""), ""
    A = t.face_areas()
    tot = float(A.sum()) or 1.0
    ex = float(A[kill].sum()) / tot
    if ex < ex_min:
        return t, "", ""
    if ex > ex_max:                                  # ca part mong (tam op, la): khong phan biet duoc than / vat
        return t, "du %.0f%% - part mong deu, khong tu sua" % (100 * ex), ""
    base = {"j0": jag(t, faces=~kill), "tau": info["ro"] * info["h"]}
    base["thin0"] = _thin_frac(t, base["tau"], ~kill)
    why = []
    t2, how = _cut(t, kill, model_size, big=True)
    if t2 is not None:
        t3, m3 = trim(t2, model_size, max_comp=0.05)     # gai mong con sot o mep cat
        if m3 and t3 is not t2:
            t2, how = t3, how + ", bo gai"
        ok, w = _good(t2, t, kill, base, info)
        if ok:
            msg = "cat %.0f%% phan du (mong hon %.2f), %d -> %d mat%s" % (
                100 * ex, info["ro"] * info["h"] * 2, len(t.F), len(t2.F), how)
            if log:
                log("  [sua part xau] " + msg)
            return t2, msg, "cat"
        why.append("cat: " + w)
    else:
        why.append("cat: " + how)
    t4 = remesh_core(t, kill, info, model_size)
    ok, w = _good(t4, t, kill, base, info)
    if ok:
        msg = "du %.0f%% -> mesh lai tu than chinh, %d -> %d mat (%s)" % (100 * ex, len(t.F), len(t4.F), "; ".join(why))
        if log:
            log("  [sua part xau] " + msg)
        return t4, msg, "mesh lai"
    why.append("mesh lai: " + w)
    return t, "du %.0f%%, sua khong dat (%s)" % (100 * ex, "; ".join(why)), "xau"
