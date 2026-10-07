"""NEP GAP -> ung vien nhat cat theo nep (nguoi dung 2026-10-06: "cac mesh co nep gap thi tach part cho cac phan do
neu cac phan do co y nghia rieng"; "tach ra cac model co y nghia roi thi tiep tuc xem tung part nen tach gi nua").

Tripo hay gop nhieu bo phan thanh mot khoi (gau + mu + tai + tay + chan; than xe + yen + san de chan). Cho noi giua
hai bo phan gan nhu luon la mot NEP LOM (ranh, goc gap vao trong). Tool tim cac canh lom, gom thanh dai nep, khop moi
dai mot mat phang cat (chua duong nep, di thang vao trong vat lieu theo phan giac hai mat), cat thu -> moi ung vien
la "neu cat o day thi phan nay roi ra". Claude chi viec NHIN va chon ung vien nao la mot bo phan co y nghia.

Do lom tinh TREN TUNG CANH (goc giua hai mat ke), KHONG lam min phap tuyen: ranh hep (vanh mu, gau ao) gom day lom +
hai mep loi, lam min thi triet tieu nhau (thu lan dau 2026-10-06: chi bat duoc co).

Mat phang chi la BUOC DAU: tay gau ap sat bung -> mat phang nao qua goc tay cung lay them mot mieng bung. Nen moi ung
vien duoc TINH LAI THEO NEP THAT: coi be mat la mang dien tro, qua nep lom thi dien tro rat lon; dau phan tach (chop tai,
ban tay) = 1, phan con lai o xa = 0, giai phuong trinh Laplace -> duong 0.5 nam dung tren nep (cho nep dut thi noi tron qua
cho ngan nhat). Cat theo duong do (khong phang), bit nap, lam min mep -> fillet bo cong nhu moi nhat cat khac.
Thuan numpy + mathutils (KDTree, BVH, CDT) -> chay trong Blender."""
import math
import numpy as np
from .tm import TM, unit, basis

TAU = 0.30          # goc gap (rad, ~17 do) cua mot canh lom de coi la canh NEP
SIGMA = 0.22        # dien tro qua canh lom: dan = exp(-(beta/SIGMA)^2) -> nep 0.6 rad dan ~0.06%
MIN_FRAC = 0.004    # phan tach ra >= 0.4% the tich manh (tai gau 0.9%)
MAX_FRAC = 0.62
MAX_CANDS = 20
CREASE_ID = 9999


def edge_bend(t):
    """(E, beta lom tung canh [0 neu loi / phang], phap tuyen phan giac tai canh, trung diem canh, do dai)."""
    E, _ = t.edges()
    ef, cnt = t.edge_faces()
    N = t.face_normals()
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-30)
    C = t.face_centers()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    a, b = np.where(ok, ef[:, 0], 0), np.where(ok, ef[:, 1], 0)
    cosb = np.clip((N[a] * N[b]).sum(1), -1, 1)
    sgn = ((N[b] - N[a]) * (C[b] - C[a])).sum(1)             # > 0 loi (phap tuyen toa ra), < 0 lom
    beta = np.where(ok & (sgn < 0), np.arccos(cosb), 0.0)
    M = N[a] + N[b]
    M = M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-30)
    mid = (t.V[E[:, 0]] + t.V[E[:, 1]]) / 2
    el = np.linalg.norm(t.V[E[:, 0]] - t.V[E[:, 1]], axis=1)
    return E, beta, M, mid, el


def vertex_crease(t, E, beta):
    """Do nep tung dinh = goc lom lon nhat cua canh ke (de ve anh)."""
    c = np.zeros(len(t.V))
    np.maximum.at(c, E[:, 0], beta)
    np.maximum.at(c, E[:, 1], beta)
    return c


def _edge_comps(E, sel, nv):
    """Nhom canh nep lien nhau (chung dinh)."""
    par = np.arange(nv)

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a, b in E[sel]:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            par[ra] = rb
    groups = {}
    for e in np.where(sel)[0]:
        groups.setdefault(find(int(E[e, 0])), []).append(int(e))
    return [np.array(g) for g in groups.values()]


def fit_plane(P, M, w):
    """Mat phang chua cac diem nep VA chua phap tuyen tai nep (cat thang vao trong theo phan giac). Nep thang (goc
    chu L) -> phap tuyen mat phang = huong nep x phap tuyen; nep vong (co, chan tai) -> mat phang cua vong.
    Tra ve (tam, phap tuyen, sai so tuong doi)."""
    w = w / max(w.sum(), 1e-30)
    c = (P * w[:, None]).sum(0)
    X = P - c
    C = (X * w[:, None]).T @ X
    s2 = max(float(np.linalg.eigvalsh(C).max()), 1e-18)
    Nm = (M * w[:, None]).T @ M
    ev, U = np.linalg.eigh(C / s2 + 0.12 * Nm)
    n = U[:, 0]
    res = math.sqrt(float(((X @ n) ** 2 * w).sum()) / s2)
    return c, unit(n), res


def _split2(P, idx):
    """Chia doi mot dai nep theo truc dai nhat (2-means)."""
    X = P[idx]
    c = X.mean(0)
    _, U = np.linalg.eigh(np.cov((X - c).T))
    lab = (X - c) @ U[:, -1] > 0
    for _ in range(8):
        if lab.all() or (~lab).all():
            break
        c0, c1 = X[~lab].mean(0), X[lab].mean(0)
        new = ((X - c1) ** 2).sum(1) < ((X - c0) ** 2).sum(1)
        if (new == lab).all():
            break
        lab = new
    return idx[~lab], idx[lab]


def bands(t, E, beta, mid, el, tau=TAU, min_e=4):
    """Cac DAI NEP (canh lom lien nhau), chia nho cho toi khi moi dai nam gon tren mot mat phang. Tra ve list
    mang chi so canh (ca dai goc lan cac nua - dai goc co the la mot vong tron ven)."""
    raw = [b for b in _edge_comps(E, beta >= tau, len(t.V)) if len(b) >= min_e]
    out = []
    stack = [(b, 0) for b in raw]
    while stack:
        b, depth = stack.pop()
        ext = float(np.linalg.norm(mid[b].max(0) - mid[b].min(0)))
        if ext < 0.035 * t.size:
            continue
        out.append(b)
        _, _, res = fit_plane(mid[b], np.zeros((len(b), 3)), beta[b] * el[b])
        if res > 0.10 and depth < 3 and len(b) >= 2 * min_e:
            for h in _split2(mid, b):
                if len(h) >= min_e:
                    stack.append((h, depth + 1))
    return out


class _Hot:
    """Canh nep (diem giua + huong) de do vong cat co CHAY DOC theo nep khong."""

    def __init__(self, mid, dirs):
        from mathutils.kdtree import KDTree
        from mathutils import Vector
        self.mid, self.dirs = mid, dirs
        self.kd = KDTree(max(len(mid), 1))
        for i, p in enumerate(mid):
            self.kd.insert(Vector(p), i)
        self.kd.balance()

    def coverage(self, loop_P, rad):
        """Ti le chieu dai vong cat di SAT va SONG SONG voi canh nep (cat ngang qua nep khong tinh): mat phang xien
        qua dau cham vao vanh mu, chan tai roi lay diem 'nep' gia (thu 2026-10-06)."""
        from mathutils import Vector
        if not len(self.mid) or len(loop_P) < 3:
            return 0.0
        P0, P1 = loop_P, np.roll(loop_P, -1, 0)
        seg = P1 - P0
        L = np.linalg.norm(seg, axis=1)
        on = np.zeros(len(L))
        for i in range(len(L)):
            if L[i] <= 0:
                continue
            s = seg[i] / L[i]
            for _, j, d in self.kd.find_range(Vector((P0[i] + P1[i]) / 2), rad):
                if abs(float(self.dirs[j] @ s)) >= 0.55:
                    on[i] = 1.0
                    break
        return float((L * on).sum() / max(L.sum(), 1e-30))


def _orients(P, M, w):
    """Cac huong mat phang thu cho mot dai nep: (1) chua nep + phan giac (goc chu L, vong co), (2) chi theo diem
    nep, (3) VUONG GOC phan giac trung binh - u nho ra (tai dung tren dau: nep chay vong chan tai, mat phang cat
    phai tiep tuyen voi dau, ca hai cach tren deu ra mat doc xe doi dau)."""
    out = []
    c, n1, r1 = fit_plane(P, M, w)
    out.append((c, n1, r1))
    _, n2, r2 = fit_plane(P, np.zeros_like(M), w)
    if abs(float(n2 @ n1)) < 0.95:
        out.append((c, n2, r2))
    m = (M * (w / max(w.sum(), 1e-30))[:, None]).sum(0)
    if np.linalg.norm(m) > 0.45:
        n3 = unit(m)
        if all(abs(float(n3 @ o[1])) < 0.95 for o in out):
            out.append((c, n3, 0.0))
    return out


# ------------------------------------------------------------------ cat THEO NEP THAT (khong phang)
def _graph(t):
    """Do thi mat: (a, b, dan dien) - dan nho khi qua canh lom."""
    E, beta, M, mid, el = edge_bend(t)
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    a, b = ef[ok, 0], ef[ok, 1]
    C = t.face_centers()
    d = np.linalg.norm(C[a] - C[b], axis=1)
    w = el[ok] / np.maximum(d, 1e-9 * max(t.size, 1e-9)) * np.exp(-(beta[ok] / SIGMA) ** 2)
    return a, b, np.maximum(w, 1e-12)


def harmonic(t, fixed, graph=None, iters=1500):
    """Giai Laplace tren do thi mat: fixed[f] = 1 / 0 (co dinh) hoac nan (tu do). Tra ve the tung mat."""
    a, b, w = graph or _graph(t)
    n = len(t.F)
    deg = np.maximum(np.bincount(a, w, n) + np.bincount(b, w, n), 1e-12)
    free = np.isnan(fixed)
    x = np.where(free, 0.5, fixed)
    idx = np.where(free)[0]
    if not len(idx):
        return x

    def L(v):
        return deg * v - np.bincount(a, w * v[b], n) - np.bincount(b, w * v[a], n)
    rhs = -L(np.where(free, 0.0, x))[idx]

    def A(vf):
        v = np.zeros(n)
        v[idx] = vf
        return L(v)[idx]
    xf = np.full(len(idx), 0.5)
    r = rhs - A(xf)
    Mi = 1.0 / deg[idx]
    z = Mi * r
    p = z.copy()
    rz = float(r @ z)
    nr0 = float(np.linalg.norm(rhs)) or 1.0
    for _ in range(iters):                       # CG + tien dieu kien Jacobi
        Ap = A(p)
        pAp = float(p @ Ap)
        if pAp <= 0:
            break
        al = rz / pAp
        xf += al * p
        r -= al * Ap
        if float(np.linalg.norm(r)) < 1e-7 * nr0:
            break
        z = Mi * r
        rz2 = float(r @ z)
        p = z + (rz2 / rz) * p
        rz = rz2
    x[idx] = xf
    return x


def _keep_connected(t, mask, seeds):
    """Chi giu cac mien cua mask co chua mat hat giong."""
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    ok &= mask[np.maximum(ef[:, 0], 0)] & mask[np.maximum(ef[:, 1], 0)]
    n = len(t.F)
    par = np.arange(n)

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for p_, q_ in ef[ok]:
        ra, rb = find(int(p_)), find(int(q_))
        if ra != rb:
            par[ra] = rb
    roots = {find(int(f)) for f in np.where(seeds & mask)[0]}
    return np.array([bool(m) and find(i) in roots for i, m in enumerate(mask)])


def _cap(P, loop):
    """Tam giac bit mot vong (chi so trong loop): CDT tren mat phang khop; chieu xuong bi tu cat -> None (quat)."""
    from mathutils.geometry import delaunay_2d_cdt
    from mathutils import Vector
    c = P.mean(0)
    X = P - c
    _, U = np.linalg.eigh(X.T @ X)
    u, w = U[:, 2], U[:, 1]
    P2 = np.stack([X @ u, X @ w], axis=1)
    sc = max(float(np.abs(P2).max()), 1e-12)
    try:
        res = delaunay_2d_cdt([Vector((float(x / sc), float(y / sc))) for x, y in P2], [],
                              [list(range(len(P2)))], 1, 1e-9)
    except Exception:
        return None
    vo, fo, ov = res[0], res[2], res[3]
    if len(vo) != len(P2) or any(len(o) != 1 for o in ov):
        return None
    m = [o[0] for o in ov]
    tris = [(loop[m[f[0]]], loop[m[f[1]]], loop[m[f[2]]]) for f in fo if len(f) == 3]
    return tris if len(tris) == len(P2) - 2 else None


def _clean_mask(t, mask, keep1, keep0, iters=10):
    """Don mien phan tach truoc khi cat: (1) mat bi hai / ba mat ke phia kia bao vay thi doi phe (bien rang cua; mat hat
    giong keep1 / keep0 giu nguyen), (2) manh bi phia kia bao kin (khong chua hat giong) -> doi phe (manh vun 52 mat giua
    hai dui), (3) dinh THAT EO (bien cham chinh no tai mot dinh -> khong bit nap duoc; gau 2026-10-06 cat dau sau khi da
    cat tay / ma) -> cac mat quanh dinh theo da so, KE CA mat hat giong (vanh hat giong nam ngay tren bien)."""
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    a, b = ef[ok, 0], ef[ok, 1]
    n = len(t.F)
    m = mask.copy()
    for _ in range(2):
        same = np.bincount(a, m[b] == m[a], n) + np.bincount(b, m[a] == m[b], n)
        deg = np.bincount(a, minlength=n) + np.bincount(b, minlength=n)
        flip = (deg - same >= 2) & ~keep1 & ~keep0
        if not flip.any():
            break
        m = np.where(flip, ~m, m)
    m = _fill_orphans(t, m, keep1, keep0)
    E, FE = t.edges()
    ar = t.face_areas()
    for it in range(iters):
        bd = np.zeros(len(E), bool)
        bd[ok] = m[ef[ok, 0]] != m[ef[ok, 1]]
        pinch = np.where(np.bincount(E[bd].ravel(), minlength=len(t.V)) > 2)[0]
        if not len(pinch):
            break
        for v in pinch:
            fs = np.where((t.F == v).any(1))[0]
            w1 = float(ar[fs][m[fs]].sum())
            m[fs] = (w1 >= float(ar[fs].sum()) - w1) if it < iters - 1 else True
        m = _fill_orphans(t, m, keep1, keep0)
    return m


def _fill_orphans(t, m, keep1, keep0):
    """Mien khong chua hat giong cua phe minh (bi phe kia bao kin) -> doi phe."""
    for side, seeds in ((False, keep0), (True, keep1)):
        if not seeds.any():
            continue
        reg = (m == side)
        lab = _region_labels(t, reg)
        good = set(np.unique(lab[reg & seeds]).tolist())
        orphan = reg & ~np.isin(lab, list(good))
        m = np.where(orphan, not side, m)
    return m


def _region_labels(t, reg):
    """Nhan thanh phan lien thong cua tap mat reg (mat ngoai reg = -1)."""
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    ok &= reg[np.maximum(ef[:, 0], 0)] & reg[np.maximum(ef[:, 1], 0)]
    n = len(t.F)
    par = np.arange(n)

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for p_, q_ in ef[ok]:
        ra, rb = find(int(p_)), find(int(q_))
        if ra != rb:
            par[ra] = rb
    lab = np.array([find(i) for i in range(n)])
    lab[~reg] = -1
    return lab


def split_by_mask(t, mask, cut_id, smooth=2):
    """Tach t theo tap mat `mask` (phan tach) / con lai: duong bien lam min (truot tren be mat goc), bit nap chung hai
    ben. Tra ve (list TM phan tach, list TM con lai) hoac None."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    F = t.F
    E, FE = t.edges()
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    bd = np.zeros(len(E), bool)
    bd[ok] = mask[ef[ok, 0]] != mask[ef[ok, 1]]
    if not bd.any() or mask.all() or not mask.any():
        return None
    nxt = {}
    for f in np.where(mask)[0]:
        for j in range(3):
            if bd[FE[f, j]]:
                u, v = int(F[f, j]), int(F[f, (j + 1) % 3])
                if u in nxt:
                    return None                      # dinh that eo (bien cham chinh no)
                nxt[u] = v
    loops, seen = [], set()
    for s0 in list(nxt):
        if s0 in seen:
            continue
        lp, u = [s0], nxt[s0]
        seen.add(s0)
        while u != s0:
            if u in seen or u not in nxt:
                return None
            lp.append(u)
            seen.add(u)
            u = nxt[u]
        if len(lp) < 3:
            return None
        loops.append(lp)
    V = t.V.copy()
    if smooth:
        bvh = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in F], all_triangles=True)
        for lp in loops:
            if len(lp) < 6:
                continue
            for _ in range(smooth):
                for f_ in (0.5, -0.52):                 # Taubin: min ma khong co vong lai
                    P = V[lp]
                    P = P + f_ * (0.5 * (np.roll(P, 1, 0) + np.roll(P, -1, 0)) - P)
                    for k, q in zip(lp, P):
                        hit = bvh.find_nearest(Vector(q))
                        V[k] = hit[0][:] if hit[0] is not None else q
    extra, caps = [], []
    for lp in loops:
        tris = _cap(V[lp], lp)
        if tris is None:                              # quat tu tam vong
            ci = len(V) + len(extra)
            extra.append(V[lp].mean(0))
            tris = [(ci, lp[i], lp[(i + 1) % len(lp)]) for i in range(len(lp))]
        # nap phia phan tach phai di NGUOC canh bien cua mat phan tach (u -> v)
        u0, v0 = lp[0], lp[1]
        same = any((tr[0], tr[1]) == (u0, v0) or (tr[1], tr[2]) == (u0, v0) or (tr[2], tr[0]) == (u0, v0)
                   for tr in tris)
        caps += [(a_, c_, b_) for a_, b_, c_ in tris] if same else list(tris)
    VV = np.concatenate([V, np.array(extra).reshape(-1, 3)])
    capF = np.array(caps, dtype=np.int64).reshape(-1, 3)
    out = []
    for side, cf in ((mask, capF), (~mask, capF[:, ::-1])):
        FF = np.concatenate([F[side], cf])
        col = np.concatenate([t.col[side], np.full(len(cf), -1, np.int64)])
        cap = np.concatenate([t.cap[side], np.full(len(cf), cut_id, np.int64)])
        comps = TM(VV, FF, col, cap).split_components(min_faces=4)
        if not comps or not all(c.is_closed() for c in comps):
            return None
        out.append(comps)
    return out[0], out[1]


def _classify(t, part, rest):
    """Mat goc thuoc phia nao cua nhat cat phang (mat goc gan mat cua manh nao hon)."""
    from mathutils.kdtree import KDTree
    from mathutils import Vector
    C = t.face_centers()
    out = []
    for m in (part, rest):
        kd = KDTree(len(m.F))
        for i, cc in enumerate(m.face_centers()):
            kd.insert(Vector(cc), i)
        kd.balance()
        out.append(np.array([kd.find(Vector(cc))[2] for cc in C]))
    return out[0] < out[1]


def refine_plane(t, c, n, part, rest, cut_id=CREASE_ID, band=0.06, tipq=0.5, graph=None):
    """Nhat cat phang (c, n -> phia `part`) -> nhat cat THEO NEP: dau phan tach (xa mat phang >= tipq) = 1, phan con
    lai ngoai dai +-band quanh vong cat = 0, giua tu do -> Laplace -> mien 0.5. Tra ve (parts, rests, frac) / None."""
    C = t.face_centers()
    is_part = _classify(t, part, rest)
    d = (C - c) @ n
    if not is_part.any() or d[is_part].max() <= 0:
        return None
    el = np.linalg.norm(t.V[t.F[:, 0]] - t.V[t.F[:, 1]], axis=1)
    w = max(band * t.size, 2.0 * float(np.median(el)))
    lat = np.linalg.norm((C - c) - np.outer(d, n), axis=1)
    ring = is_part & (np.abs(d) < w)
    R = float(lat[ring].max()) if ring.any() else float(lat[is_part].max())
    fixed = np.full(len(C), np.nan)
    fixed[is_part & (d >= tipq * d[is_part].max())] = 1.0
    near = (np.abs(d) < w) & (lat < R + w)
    fixed[~is_part & ~near] = 0.0
    x = harmonic(t, fixed, graph)
    keep1, keep0 = fixed == 1.0, fixed == 0.0
    mask = _clean_mask(t, _keep_connected(t, x > 0.5, keep1), keep1, keep0)
    res = split_by_mask(t, mask, cut_id)
    if res is None:
        return None
    v0 = abs(t.volume()) or 1e-9
    return res[0], res[1], sum(abs(p.volume()) for p in res[0]) / v0, mask


def _seed(t, pts, rad):
    """Mat gan cac diem trong ban kinh rad; rad = 0 -> dung mat GAN NHAT moi diem (hat giong tool ghi lai)."""
    from mathutils.kdtree import KDTree
    from mathutils import Vector
    C = t.face_centers()
    m = np.zeros(len(C), bool)
    kd = KDTree(len(C))
    for i, cc in enumerate(C):
        kd.insert(Vector(cc), i)
    kd.balance()
    for q in pts:
        q = Vector([float(x) for x in q])
        m[kd.find(q)[1]] = True
        if rad > 0:
            for _, i, _ in kd.find_range(q, rad):
                m[i] = True
    return m


def seeded(t, part_pts, rest_pts, cut_id=CREASE_ID, rad=0.035):
    """Diem tren bo phan con (part) va tren phan con lai (rest) -> cat theo nep giua chung. Claude chi vai diem
    (rad 0.035 x co manh); ung vien tool ghi ca vanh mat sat bien hai phia (rad 0 = dung mat gan nhat)."""
    src, snk = _seed(t, part_pts, rad * t.size), _seed(t, rest_pts, rad * t.size)
    src &= ~snk
    if not src.any() or not snk.any():
        return None
    fixed = np.full(len(t.F), np.nan)
    fixed[src], fixed[snk] = 1.0, 0.0
    x = harmonic(t, fixed)
    mask = _clean_mask(t, _keep_connected(t, x > 0.5, src), src, snk)
    res = split_by_mask(t, mask, cut_id)
    if res is None:
        return None
    E, beta, M, mid, el = edge_bend(t)
    return res[0], res[1], sum(abs(p.volume()) for p in res[0]) / (abs(t.volume()) or 1e-9), _cover(t, mask, beta, TAU)


def _sides(pl, c, n):
    """Manh cat phang -> (phan phia +n gop lai, phan con lai gop lai)."""
    pos = [x for x in pl if (x.centroid() - c) @ n > 0]
    neg = [x for x in pl if (x.centroid() - c) @ n <= 0]
    if not pos or not neg:
        vols = [abs(x.volume()) for x in pl]
        k = int(np.argmax(vols))
        pos, neg = [x for i, x in enumerate(pl) if i != k], [pl[k]]
    return _join(pos), _join(neg)


def _join(ts):
    if len(ts) == 1:
        return ts[0]
    off = np.cumsum([0] + [len(x.V) for x in ts[:-1]])
    return TM(np.concatenate([x.V for x in ts]), np.concatenate([x.F + o for x, o in zip(ts, off)]),
              np.concatenate([x.col for x in ts]), np.concatenate([x.cap for x in ts]))


def apply(t, o, cut_id, log=None):
    """Thao tac {"op":"crease"} trong plan.json: "at"+"normal" (ung vien tool tu do: cat phang roi tinh lai theo nep;
    "planar": true = giu phang) hoac "part"+"rest" (diem hai phia). Tra ve list TM (>= 2) hoac None."""
    v0 = abs(t.volume()) or 1e-9
    if o.get("part") and o.get("rest"):
        rad = float(o.get("seed_r", 0.035))
        r = seeded(t, o["part"], o["rest"], cut_id, rad=rad)
        if r is not None and (rad == 0 or r[3] >= 0.35):
            return _merge_tiny(r[0] + r[1], v0)
        # Claude tu chi diem ma duong 0,5 KHONG nam tren nep (thung hang tron, khong ranh nap: Laplace truot xuong mep day,
        # "nap" thanh ca cai thung - 2026-10-07) -> cat PHANG giua hai nhom diem, vuong goc huong rest -> part
        P, Q = np.asarray(o["part"], float).mean(0), np.asarray(o["rest"], float).mean(0)
        if np.linalg.norm(P - Q) > 1e-6:
            c, n = (P + Q) / 2, unit(P - Q)
            k = int(np.argmax(np.abs(n)))              # diem Claude lech chut -> mat cat nghieng; gan truc the gioi
            if abs(n[k]) >= np.cos(np.radians(25)):    # (model da xoay mat truoc) thi cat dung truc: nap ngang, vach dung
                n = np.eye(3)[k] * np.sign(n[k])
            pl = t.plane_cut(c, n, cut_id, mode="local", q=c)
            if pl and len(pl) >= 2:
                if log:
                    log("  (duong cat khong nam tren nep -> cat phang giua hai nhom diem)")
                return _merge_tiny(pl, v0)
        return _merge_tiny(r[0] + r[1], v0) if r else None
    c, n = np.asarray(o["at"], float), unit(np.asarray(o["normal"], float))
    pl = t.plane_cut(c, n, cut_id, mode="local", q=c)
    if not pl or len(pl) < 2:
        return None
    if o.get("planar"):
        return _merge_tiny(pl, v0)
    part, rest = _sides(pl, c, n)
    r = refine_plane(t, c, n, part, rest, cut_id, band=float(o.get("band", 0.06)), tipq=float(o.get("tipq", 0.5)))
    if r is None or not (MIN_FRAC <= r[2] <= 0.9):
        if log:
            log("  (cat theo nep khong duoc -> giu nhat cat phang)")
        return _merge_tiny(pl, v0)
    return _merge_tiny(r[0] + r[1], v0)


def _merge_tiny(pieces, v0, min_frac=0.003, min_faces=30):
    """Manh vun (< 0,3% the tich hoac < 30 mat - xe ga 2026-10-06: nhat yen ra them 24 + 6 mat) -> nhap vao manh lon gan
    nhat (bo nap chung; khong khep thi giu hai vo trong mot mesh, nhu plan._full_cuts). Con < 2 manh -> None."""
    big = [p for p in pieces if abs(p.volume()) >= min_frac * v0 and len(p.F) >= min_faces]
    tiny = [p for p in pieces if not any(p is b for b in big)]
    if not big:
        return pieces
    for x in tiny:
        k = min(range(len(big)), key=lambda i: big[i].dist(x.centroid()))
        m = big[k].merge_with(x)
        big[k] = m if m.is_closed() else _join([big[k], x])
    return big if len(big) >= 2 else None


# ------------------------------------------------------------------ khep kin nep ho (tay ap sat bung)
def _vadj(t, beta):
    """Ke dinh + gia canh: di doc nep RE hon di qua mat tron."""
    E, _ = t.edges()
    el = np.linalg.norm(t.V[E[:, 0]] - t.V[E[:, 1]], axis=1)
    cost = el * (1.0 - 0.85 * np.minimum(1.0, beta / 0.5))
    adj = [[] for _ in range(len(t.V))]
    for e, (a, b) in enumerate(E):
        adj[int(a)].append((int(b), e))
        adj[int(b)].append((int(a), e))
    return adj, cost


def _path(adj, cost, src, dst, banned=None, allowed=None):
    """Dijkstra src -> dst; tra ve list chi so canh (None neu khong toi)."""
    import heapq
    dist = {src: 0.0}
    prev = {}
    h = [(0.0, src)]
    while h:
        d, u = heapq.heappop(h)
        if u == dst:
            break
        if d > dist.get(u, 1e30):
            continue
        for v, e in adj[u]:
            if allowed is not None and e not in allowed:
                continue
            if banned is not None and v in banned and v != dst:
                continue
            nd = d + cost[e]
            if nd < dist.get(v, 1e30):
                dist[v] = nd
                prev[v] = (u, e)
                heapq.heappush(h, (nd, v))
    if dst not in prev:
        return None
    out, u = [], dst
    while u != src:
        u, e = prev[u]
        out.append(e)
    return out[::-1]


def _faces_split(t, cut_edges):
    """Nhan mien mat khi khong duoc di qua cac canh cat."""
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    ok[list(cut_edges)] = False
    n = len(t.F)
    par = np.arange(n)

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for a, b in ef[ok]:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            par[ra] = rb
    roots = np.array([find(i) for i in range(n)])
    _, lab = np.unique(roots, return_inverse=True)
    return lab


def closure_mask(t, band, E, beta, adj, cost):
    """Nep HO (chi chay mot phia goc tay / chan tai) -> noi hai dau bang duong ngan nhat VONG QUA PHIA KIA (khong di sat
    nep) -> vong kin -> mien nho hon = phan tach. Tra ve mask mat hoac None."""
    eb = set(int(e) for e in band)
    deg = {}
    for e in eb:
        for v in E[e]:
            deg[int(v)] = deg.get(int(v), 0) + 1
    ends = [v for v, d in deg.items() if d == 1]
    if len(ends) < 2:
        return None
    P = t.V[ends]
    D = np.linalg.norm(P[:, None] - P[None], axis=2)
    i, j = np.unravel_index(int(np.argmax(D)), D.shape)
    s, g = ends[i], ends[j]
    inner = _path(adj, cost, s, g, allowed=eb)
    if not inner:
        return None
    pv = {int(v) for e in inner for v in E[e]}
    rb = 0.035 * t.size
    near_end = np.linalg.norm(t.V - t.V[s], axis=1) < rb
    near_end |= np.linalg.norm(t.V - t.V[g], axis=1) < rb
    PV = t.V[sorted(pv)]
    banned = set()
    for k in range(0, len(PV), 1):
        dd = np.linalg.norm(t.V - PV[k], axis=1)
        banned |= set(np.where((dd < rb) & ~near_end)[0].tolist())
    banned |= pv - {s, g}
    outer = _path(adj, cost, g, s, banned=banned)
    if not outer:
        return None
    lab = _faces_split(t, set(inner) | set(outer))
    if lab.max() != 1:
        return None
    ar = t.face_areas()
    a0, a1 = ar[lab == 0].sum(), ar[lab == 1].sum()
    return lab == (0 if a0 < a1 else 1)


def _cover(t, mask, beta, tau):
    """Ti le chieu dai duong bien phan tach nam tren canh nep (bien tinh tren luoi goc nen chinh xac)."""
    E, _ = t.edges()
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    bd = np.zeros(len(E), bool)
    bd[ok] = mask[ef[ok, 0]] != mask[ef[ok, 1]]
    el = np.linalg.norm(t.V[E[:, 0]] - t.V[E[:, 1]], axis=1)
    tot = float(el[bd].sum())
    return float(el[bd & (beta >= 0.6 * tau)].sum()) / tot if tot > 0 else 0.0


def _seeds_of(t, mask):
    """Diem hat giong tai hien dung nhat cat: tam cac mat SAT bien hai phia (+ diem xa nhat cua moi ben)."""
    ef, cnt = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    a, b = ef[ok, 0], ef[ok, 1]
    bd = mask[a] != mask[b]
    ring = np.zeros(len(t.F), bool)
    ring[a[bd]] = True
    ring[b[bd]] = True
    C = t.face_centers()
    part = C[ring & mask]
    rest = C[ring & ~mask]
    return np.round(part, 4).tolist(), np.round(rest, 4).tolist()


# ------------------------------------------------------------------ ung vien
def candidates(t, tau=TAU, log=None, max_n=MAX_CANDS, max_bands=40):
    """Ung vien cat theo nep: [{op, frac, cover, score, mode, part TM, rest TM, tip, anchor}]. Moi dai nep cho toi da
    2 ung vien: (a) mat phang khop nep roi tinh lai theo nep that, (b) nep ho khep kin vong qua phia kia. Moi ung vien
    da cat thu THAT nen anh ve dung y nhu khi cat; "op" ghi vao plan.json tai hien dung nhat cat do."""
    E, beta, M, mid, el = edge_bend(t)
    bl = bands(t, E, beta, mid, el, tau)
    bl.sort(key=lambda b: -float((beta[b] * el[b]).sum()))
    bl = bl[:max_bands]
    hs = beta >= 0.6 * tau
    dirs = t.V[E[hs, 1]] - t.V[E[hs, 0]]
    hot = _Hot(mid[hs], dirs / np.maximum(np.linalg.norm(dirs, axis=1, keepdims=True), 1e-30))
    rad = max(1.6 * float(np.median(el)), 0.012 * t.size)
    v0 = abs(t.volume()) or 1e-9
    graph = _graph(t)
    adj, cost = _vadj(t, beta)
    ar = t.face_areas()
    out = []
    for b in bl:
        best = None
        for c, n, res in _orients(mid[b], M[b], beta[b] * el[b]):
            if res > 0.3:
                continue
            sec = t.section(c, n)
            loops, area = t.region(sec, c, "local")
            if not loops:
                continue
            cov = hot.coverage(loops[0]["P3"], rad)
            if best is None or cov > best[0]:
                best = (cov, c, n, res)
        if best is not None and best[0] >= 0.35:
            d = _try_plane(t, best[1], best[2], best[0], v0, graph, beta, tau)
            if d is not None:
                out.append(d)
        try:
            m = closure_mask(t, b, E, beta, adj, cost)
        except Exception:
            m = None
        if m is not None:
            d = _from_mask(t, m, v0, beta, tau, "khep")
            if d is not None:
                out.append(d)
    out.sort(key=lambda d: -d["score"])
    keep = []
    for d in out:                       # bo trung: hai phan tach trung nhau >= 80% dien tich -> giu o diem cao
        if any(_same(t, ar, k_, d) for k_ in keep):
            continue
        keep.append(d)
        if len(keep) >= max_n:
            break
    keep.sort(key=lambda d: -d["frac"])               # khoi lon truoc (dau / than), chi tiet nho sau (tai, giay)
    for d in keep:
        d["anchor"] = [round(float(x), 4) for x in d["anchor"]]
        d["tip"] = [round(float(x), 4) for x in d["tip"]]
    if log:
        log("  nep: %d canh lom, %d dai, %d ung vien" % (int((beta >= tau).sum()), len(bl), len(keep)))
    return keep, vertex_crease(t, E, beta)


def _same(t, ar, a, b):
    pa, pb = a["part"].centroid(), b["part"].centroid()
    if np.linalg.norm(pa - pb) < 0.025 * t.size and abs(a["frac"] - b["frac"]) < 0.06 * max(a["frac"], b["frac"]):
        return True                                    # cung khoi roi ra (vong khep tu hai dai nep doi xung, 2026-10-06)
    if a.get("mask") is not None and b.get("mask") is not None:
        inter = float(ar[a["mask"] & b["mask"]].sum())
        uni = float(ar[a["mask"] | b["mask"]].sum()) or 1e-30
        return inter / uni > 0.8
    return np.linalg.norm(pa - pb) < 0.05 * t.size and abs(a["frac"] - b["frac"]) < 0.2 * max(a["frac"], b["frac"])


def _score(cover, frac):
    """Diem: nep phu duong cat la chinh; manh rat lon (> 30%) ma nep khong kin thuong la lat xien qua khoi."""
    return cover * (1.0 - 0.35 * max(0.0, frac - 0.3) / 0.3)


def _from_mask(t, mask, v0, beta, tau, mode):
    r = split_by_mask(t, mask, CREASE_ID)
    if r is None:
        return None
    parts, rests = r
    frac = sum(abs(p.volume()) for p in parts) / v0
    if not (MIN_FRAC <= frac <= MAX_FRAC) or len(parts) > 2:
        return None
    cover = _cover(t, mask, beta, tau)
    if cover < 0.45:                                   # bien phan lon di qua mat tron -> lat xien, khong phai bo phan
        return None
    P = _join(parts)
    pc = t.face_centers()[mask].mean(0)
    rc = t.face_centers()[~mask].mean(0)
    n = unit(pc - rc)
    tip = P.V[int(np.argmax((P.V - rc) @ n))]
    sp, sr = _seeds_of(t, mask)
    op = {"op": "crease", "part": sp, "rest": sr, "seed_r": 0}
    anchor = np.asarray(sp[len(sp) // 2]) if sp else tip
    return dict(op=op, frac=frac, cover=cover, score=_score(cover, frac), mode=mode, part=P, rest=_join(rests),
                tip=tip, anchor=anchor, mask=mask)


def _try_plane(t, c, n, cover, v0, graph, beta, tau):
    """Cat thu mot mat phang theo nep, tinh lai theo nep that -> ung vien (hoac None)."""
    pl = t.plane_cut(c, n, CREASE_ID, mode="local", q=c)
    if not pl or len(pl) < 2:
        return None
    vols = [abs(x.volume()) for x in pl]
    k = int(np.argmax(vols))
    if (sum(vols) - vols[k]) / v0 < MIN_FRAC:
        return None
    small = [x for i, x in enumerate(pl) if i != k]
    if (_join(small).V.mean(0) - c) @ n < 0:
        n = -n                                         # n huong ve phan nho (phan tach)
    part, rest = _sides(pl, c, n)
    r = refine_plane(t, c, n, part, rest, graph=graph)
    if r is not None:
        d = _from_mask(t, r[3], v0, beta, tau, "nep")
        if d is not None:
            return d
    frac = abs(part.volume()) / v0
    if not (MIN_FRAC <= frac <= MAX_FRAC) or cover < 0.7:     # phang ma nep phu it -> mieng lat (xe ga 2026-10-06)
        return None
    tip = part.V[int(np.argmax((part.V - c) @ n))]
    op = {"op": "crease", "at": np.round(c, 4).tolist(), "normal": np.round(n, 4).tolist(), "planar": True}
    return dict(op=op, frac=frac, cover=cover, score=_score(cover, frac) * 0.9, mode="phang", part=part, rest=rest,
                tip=tip, anchor=c, mask=None)
