"""CHONG LAN giua cac part (nguoi dung 2026-10-08, cao truot van: "cac part k nen overlap len nhau qua nhieu"; "overlap
nhieu thi nen can nhac gop lai"). Model Tripo nhieu khoi roi (cao: 73 khoi) cam CHONG vao nhau: ban tay cam vao ong tay
ao 24%, dui chui vao vat ao 43%, khan quang chim 45% trong than ao, de giay chim 78% trong luoi truot. Cat theo mat
phang giu nguyen cac khoi -> part ke thua phan CHIM. Trong game len quan tung part -> phan chim lo ra khi go part phu
ngoai, vien len hai part dam nhau.
Xu ly (plan.execute, truoc bo cong): A chim f trong B (ti le dien tich be mat A nam trong khoi B):
  f >= MERGE_FRAC, hoac f >= SAME_FRAC + cung mau + A <= nua B  -> GOP A vao B (Boolean hop, giu be mat ca hai)
  CUT_FRAC <= f < ...                               -> CAT phan chim: A := A - B (Boolean hieu) - nhin ngoai khong doi,
                                                       A ap sat mat B
Manh D (decor cam nua than vao be mat la co y) va hai manh cung mot nhat cat (chung ma nap) khong xet."""
import numpy as np
from .tm import TM

CUT_FRAC = 0.05           # chim < 5% dien tich: tiep xuc / sai so - bo qua
SAME_FRAC = 0.30          # chim >= 30% va CUNG MAU -> cung mot bo phan (dui + dau goi) -> gop
SAME_SIZE = 0.5          # ... va dien tich <= 50% manh bao
MERGE_FRAC = 0.60         # chim >= 60%: phan nhin thay < 40% (cat ra lat mong: luoi truot chim 67%) -> gop vao manh bao
MIN_KEEP = 0.15           # cat xong con < 15% dien tich -> gop thay vi cat


def _bvh(t):
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    return BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)


def inside_frac(a, b, bvh_b=None):
    """Ti le dien tich be mat a nam TRONG khoi kin b (diem gan nhat tren b + phap tuyen: nam phia sau mat = trong)."""
    from mathutils import Vector
    lo, hi = b.V.min(0), b.V.max(0)
    C = a.face_centers()
    m = np.all((C >= lo) & (C <= hi), axis=1)
    if not m.any():
        return 0.0
    bvh = bvh_b or _bvh(b)
    A = a.face_areas()
    eps = 1e-6 * float((hi - lo).max())
    ins = 0.0
    for i in np.where(m)[0]:
        loc, nrm, idx, d = bvh.find_nearest(Vector(C[i]))
        if loc is None or d is None or d < eps:
            continue
        if (Vector(C[i]) - loc).dot(nrm) < 0:
            ins += A[i]
    return float(ins / max(A.sum(), 1e-12))


def inside_mask(a, b, bvh_b=None):
    """Mat cua a co tam nam TRONG khoi kin b."""
    from mathutils import Vector
    lo, hi = b.V.min(0), b.V.max(0)
    C = a.face_centers()
    out = np.zeros(len(a.F), bool)
    m = np.all((C >= lo) & (C <= hi), axis=1)
    bvh = bvh_b or _bvh(b)
    for i in np.where(m)[0]:
        loc, nrm, idx, d = bvh.find_nearest(Vector(C[i]))
        if loc is not None and d and (Vector(C[i]) - loc).dot(nrm) < 0:
            out[i] = True
    return out


def _cut_faces(a, b, model_size):
    """Du phong khi Boolean hong (khoi Tripo tu cat nhau): bo cac MAT cua a nam trong b, va kin tai cho."""
    from . import trim
    kill = inside_mask(a, b)
    if not kill.any():
        return None
    t, why = trim._cut(a, kill, model_size, big=True)
    return t


def _siblings(a, b):
    ca, cb = set(np.unique(a.cap[a.cap >= 0]).tolist()), set(np.unique(b.cap[b.cap >= 0]).tolist())
    return bool(ca & cb)


def _boolean(a, b, op):
    """Boolean EXACT a (op) b -> TM kin hoac None."""
    from . import shell
    obs = []
    try:
        oa = shell._obj(a, "_ov_a")
        obs.append(oa)
        ob = shell._obj(b, "_ov_b")
        obs.append(ob)
        ob.hide_viewport = True
        m = oa.modifiers.new("ov", "BOOLEAN")
        m.operation, m.object, m.solver = op, ob, "EXACT"
        t = shell._evaluated_tm(oa)
        if not len(t.F):
            return None
        comps = t.split_components(min_faces=4)
        if not comps:
            return None
        big = max(float(c.face_areas().sum()) for c in comps)
        keep = [c for c in comps if float(c.face_areas().sum()) >= 0.1 * big]      # vun vat mong sau khi cat -> bo
        if len(keep) < len(comps):
            V, F, off = [], [], 0
            for c in keep:
                V.append(c.V)
                F.append(c.F + off)
                off += len(c.V)
            t = TM(np.concatenate(V), np.concatenate(F))
        if not t.is_closed():                           # khoi Tripo tu cat nhau -> vai canh ho: va tai cho
            from . import prep
            t = prep.local_close(t)
        return t
    except Exception:
        return None
    finally:
        shell._drop(*obs)


def _union_ok(u, a, b, f):
    """Hop hop ly: dien tich ~ phan noi cua a + phan lon cua b (Boolean hong ra mot manh vun hoac nhan doi)."""
    if u is None:
        return False
    au, aa, ab = float(u.face_areas().sum()), float(a.face_areas().sum()), float(b.face_areas().sum())
    return 0.6 * max(ab, aa * (1 - f)) <= au <= 1.05 * (aa + ab)


def _carry(src_list, dst, keep_cap_from=None):
    """Mau (col) theo mat gan nhat cua cac luoi nguon; ma nap (cap) chi giu cho mat TRUNG mat goc cua keep_cap_from
    (mat moi o mat tiep xuc khong phai nhat cat -> khong bo cong)."""
    from mathutils import Vector
    from mathutils.kdtree import KDTree
    V = [s for s in src_list]
    cen = np.concatenate([s.face_centers() for s in V])
    col = np.concatenate([np.asarray(s.col) for s in V])
    cap = np.concatenate([np.asarray(s.cap) for s in V])
    kd = KDTree(len(cen))
    for i, c in enumerate(cen):
        kd.insert(Vector(c), i)
    kd.balance()
    size = float((dst.V.max(0) - dst.V.min(0)).max()) or 1.0
    out_col = np.empty(len(dst.F), np.int64)
    out_cap = np.full(len(dst.F), -1, np.int64)
    for k, c in enumerate(dst.face_centers()):
        _, j, d = kd.find(Vector(c))
        out_col[k] = col[j]
        if d < 1e-3 * size:
            out_cap[k] = cap[j]
    dst.col, dst.cap = out_col, out_cap
    return dst


def resolve(R, kinds, log=print):
    """Cat phan CHIM / gop manh chim sau giua cac manh M/S cua R.pieces (sua tai cho). -> (so cat, so gop)."""
    ps = [p for p in R.pieces if (p.kind or kinds.get(p.id)) != "D" and p.tm.is_closed()]
    bv = {p.id: _bvh(p.tm) for p in ps}
    bb = {p.id: (p.tm.V.min(0), p.tm.V.max(0)) for p in ps}
    pairs = []
    for a in ps:
        for b in ps:
            if a is b or (bb[a.id][1] < bb[b.id][0]).any() or (bb[b.id][1] < bb[a.id][0]).any() or _siblings(a.tm, b.tm):
                continue
            f = inside_frac(a.tm, b.tm, bv[b.id])
            if f >= CUT_FRAC:
                pairs.append([f, a, b])
    pairs.sort(key=lambda x: -x[0])
    gone, ncut, nmer = set(), 0, 0
    for f0, a, b in pairs:
        if a.id in gone or b.id in gone:
            continue
        f = inside_frac(a.tm, b.tm)                    # do lai: lan cat truoc co the da go phan chong
        if f < CUT_FRAC:
            continue
        # cung mau + chim nhieu + NHO hon han manh bao (dau goi tren dui) = chi tiet cua cung bo phan -> gop; mu va vanh
        # mu (cung do, chim 31-36%, co gan bang nhau) la hai bo phan -> cat
        same = (R.piece_color(a) == R.piece_color(b)
                and float(a.tm.face_areas().sum()) <= SAME_SIZE * float(b.tm.face_areas().sum()))
        an, bn = a.label or "#%d" % a.id, b.label or "#%d" % b.id
        if f >= MERGE_FRAC or (same and f >= SAME_FRAC):
            t = _boolean(b.tm, a.tm, "UNION")
            if _union_ok(t, a.tm, b.tm, f):
                b.tm = _carry([b.tm, a.tm], t)
                b.cache = {}
                R.pieces.remove(a)
                gone.add(a.id)
                for p in R.pieces:                     # decor dan tren a -> dan tren b
                    if getattr(p, "host", None) == a.id:
                        p.host = b.id
                nmer += 1
                log("  [chong lan] gop %s (chim %.0f%%%s) vao %s" % (an, 100 * f, ", cung mau" if same else "", bn))
                continue
        t = _boolean(a.tm, b.tm, "DIFFERENCE")
        aa = max(float(a.tm.face_areas().sum()), 1e-12)
        keep = float(t.face_areas().sum()) / aa if t is not None else 0.0
        how = ""
        # con lai = phan noi (1 - f) + mat tiep xuc moi; it hon han -> Boolean hong (luoi tu cat / phap tuyen lat), KHONG
        # gop nham (ban dau: dui chim 41% "cat xong con 0%" -> bi gop vao vat ao) -> bo mat chim + va tai cho
        if t is None or keep < 0.6 * (1.0 - f):
            t = _cut_faces(a.tm, b.tm, R.model_size)
            keep = float(t.face_areas().sum()) / aa if t is not None else 0.0
            how = ", bo mat chim + va"
            if t is None or keep < 0.6 * (1.0 - f):
                log("  [chong lan] %s chim %.0f%% trong %s: cat hong - giu" % (an, 100 * f, bn))
                continue
        if keep < MIN_KEEP:
            u = _boolean(b.tm, a.tm, "UNION")
            if _union_ok(u, a.tm, b.tm, f):
                b.tm = _carry([b.tm, a.tm], u)
                b.cache = {}
                R.pieces.remove(a)
                gone.add(a.id)
                nmer += 1
                log("  [chong lan] gop %s vao %s (cat xong chi con %.0f%%)" % (an, bn, 100 * keep))
            continue
        n0 = len(a.tm.F)
        a.tm = _carry([a.tm], t)
        a.cache = {}
        ncut += 1
        log("  [chong lan] cat phan chim cua %s trong %s: %.0f%% (%d -> %d mat%s)" % (an, bn, 100 * f, n0, len(t.F), how))
    if ncut or nmer:
        log("[chong lan] cat phan chim %d manh, gop %d manh" % (ncut, nmer))
    return ncut, nmer


def scan(objs, kind_of, log=print, min_frac=CUT_FRAC):
    """Bao cao chong lan giua cac object trong canh (khong sua) -> [(f, ten A, ten B)]."""
    from . import bl
    items = []
    for o in objs:
        if kind_of(o) == "D":
            continue
        t = bl.tm_from_mesh(o.data, o.matrix_world)
        if t.is_closed():
            items.append((o.name, t, _bvh(t)))
    out = []
    for na, ta, _ in items:
        for nb, tb, bvb in items:
            if na == nb:
                continue
            f = inside_frac(ta, tb, bvb)
            if f >= min_frac:
                out.append((f, na, nb))
    out.sort(reverse=True)
    return out


# ------------------------------------------------------------------ manh CHIM BEN TRONG / TRUNG / VUN (2026-10-08)
# Nguoi dung (gau truc truot van): "cac mesh bi overlap o phia trong can duoc xoa". Sau khi cat phan chim van con:
# vo mong ap sat duoi manh khac (P01 duoi chop mu: nhin thay 2%), ban TRUNG khit (hai ong tay ao cung hop bao, cung the
# tich), long trang mat nam sau quang mat chi lo mot vet, vo lot trong mu trum, khoi vun 4 mat nam tren van truot.
JUNK_FACES = 12           # < 12 tam giac (it hon mot cai hop) -> vun
DUP_TOL = 0.005           # sat be mat manh kia trong 0,5% co model
DUP_NEAR = 0.9            # >= 90% be mat MOI ben nam sat ben kia -> hai ban trung nhau, giu ban lon
BURIED_VIS = 0.08         # nhin tu ngoai thay < 8% be mat -> chim (gau truc: long trang mat sau quang 4-6%, vo lot mu
                          # trum 0-4%, chop mu lot 4%; MIENG 11% - giu)
BURIED_BIG = 0.03         # M/S chim ma >= 3% the tich model -> GIU (bo phan nen: go manh phu ngoai se lo ra)
VIS_SAMPLES = 200


def _fib_dirs(n=48):
    """n huong rai deu tren mat cau (xoan Fibonacci) - co dinh, chay lai ra y het."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)
    th = np.pi * (1.0 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], 1)


def _dist(hit):
    """Khoang cach cua BVH.find_nearest; KHONG viet `[3] or 1e9`: diem nam DUNG tren mat (0.0) thanh 1e9 = "xa nhat"."""
    return 1e9 if hit[3] is None else float(hit[3])


def _merged_bvh(tms):
    V, F, off = [], [], 0
    for t in tms:
        V.append(t.V)
        F.append(t.F + off)
        off += len(t.V)
    return _bvh(TM(np.concatenate(V), np.concatenate(F)))


def _sample_faces(t, n, seed=0):
    """Mat lay mau theo dien tich -> (chi so mat, trong so; tong trong so = 1)."""
    A = t.face_areas()
    s = float(A.sum())
    if s <= 0:
        return np.zeros(0, np.int64), np.zeros(0)
    if len(t.F) <= n:
        return np.arange(len(t.F)), A / s
    idx = np.random.default_rng(seed).choice(len(t.F), n, replace=True, p=A / s)
    u, c = np.unique(idx, return_counts=True)
    return u, c / float(n)


def visible_frac(t, occ, size, n=VIS_SAMPLES, dirs=None):
    """Ti le dien tich be mat t NHIN THAY tu ben ngoai: tu diem tren mat (nhich ra 0,1% co model) co it nhat mot tia
    thoat ra xa ma khong cham `occ` (BVH cac manh che, gom ca chinh t). Thu CA HAI phia mat: luoi Tripo lat phap tuyen
    khong bi tinh nham la chim (phia trong khoi kin thi khong tia nao thoat)."""
    from mathutils import Vector
    dirs = _fib_dirs() if dirs is None else dirs
    idx, w = _sample_faces(t, n)
    if not len(idx):
        return 0.0
    N = t.face_normals()[idx]
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]
    C = t.face_centers()[idx]
    eps, far = 1e-3 * size, 4.0 * size
    vis = 0.0
    for c, nv, wi in zip(C, N, w):
        seen = False
        for m in (nv, -nv):
            p = Vector(c + m * eps)
            for d in dirs[dirs @ m > 0.05]:
                if occ.ray_cast(p, Vector(d), far)[0] is None:
                    seen = True
                    break
            if seen:
                vis += wi
                break
    return float(vis)


def _near_frac(a, bvh_b, tol, n=120):
    """Ti le dien tich be mat a nam trong `tol` quanh be mat b."""
    from mathutils import Vector
    idx, w = _sample_faces(a, n, seed=1)
    C = a.face_centers()[idx]
    return float(sum(wi for c, wi in zip(C, w) if bvh_b.find_nearest(Vector(c), tol)[0] is not None))


def _bbox_iou(a, b):
    lo, hi = np.maximum(a[0], b[0]), np.minimum(a[1], b[1])
    inter = float(np.prod(np.clip(hi - lo, 0, None)))
    va, vb = float(np.prod(a[1] - a[0])), float(np.prod(b[1] - b[0]))
    return inter / max(va + vb - inter, 1e-12)


def find_buried(tms, kinds, size, names=None, keep=(), log=print):
    """Manh nen XOA -> ({chi so: ly do}, {chi so: ti le nhin thay}):
    - VUN: < JUNK_FACES tam giac;
    - TRUNG: ban sao gan khop manh khac (>= DUP_NEAR be mat moi ben sat nhau, hop bao + dien tich gan bang) -> bo ban nho;
    - CHIM: nhin tu ngoai thay < BURIED_VIS be mat. M/S chi bi M/S che (decor dan ngoai khong lam manh chinh thanh chim),
      D bi moi manh che. M/S to (>= BURIED_BIG the tich) thi giu.
    `keep`: chi so khong bao gio xoa (decor tu thu vien...) - van tinh la vat che."""
    n = len(tms)
    nm = (lambda i: names[i]) if names else (lambda i: "#%d" % i)
    out = {}
    for i, t in enumerate(tms):
        if i not in keep and len(t.F) < JUNK_FACES:
            out[i] = "vụn, chỉ %d tam giác" % len(t.F)
    bb = [(t.V.min(0), t.V.max(0)) for t in tms]
    area = [float(t.face_areas().sum()) for t in tms]
    bv, tol = {}, DUP_TOL * size
    for i in range(n):
        for j in range(i + 1, n):
            if i in out or j in out or (kinds[i] == "D") != (kinds[j] == "D"):
                continue
            if _bbox_iou(bb[i], bb[j]) < 0.6 or min(area[i], area[j]) < 0.5 * max(area[i], area[j]):
                continue
            for k in (i, j):
                if k not in bv:
                    bv[k] = _bvh(tms[k])
            if _near_frac(tms[i], bv[j], tol) >= DUP_NEAR and _near_frac(tms[j], bv[i], tol) >= DUP_NEAR:
                small, big = (i, j) if (area[i], len(tms[i].F)) < (area[j], len(tms[j].F)) else (j, i)
                if small in keep:
                    small, big = big, small
                if small not in keep:
                    out[small] = "trùng khít %s" % nm(big)
    alive = [i for i in range(n) if i not in out]
    solid = [i for i in alive if kinds[i] != "D"]
    if not alive:
        return out, {}
    vol = [abs(t.volume()) for t in tms]
    tot = sum(vol[i] for i in solid) or 1e-12
    occ_all = _merged_bvh([tms[i] for i in alive])
    occ_solid = _merged_bvh([tms[i] for i in solid]) if solid else occ_all
    dirs = _fib_dirs()
    vis = {}
    for i in alive:
        if i in keep:
            continue
        v = vis[i] = visible_frac(tms[i], occ_all if kinds[i] == "D" else occ_solid, size, dirs=dirs)
        if v >= BURIED_VIS:
            continue
        if kinds[i] != "D" and vol[i] / tot >= BURIED_BIG:
            log("  [chim trong] %s chim (thay %.0f%%) nhung to %.1f%% the tich - giu" % (nm(i), 100 * v, 100 * vol[i] / tot))
            continue
        out[i] = "chìm bên trong, nhìn từ ngoài chỉ thấy %.0f%% bề mặt" % (100 * v)
    return out, vis


def drop_buried(R, kinds, log=print):
    """plan.execute: xoa manh chim / trung / vun trong R.pieces (sau chong lan). -> so manh xoa."""
    ps = list(R.pieces)
    if len(ps) < 2:
        return 0
    ks = [(p.kind or kinds.get(p.id) or "S") for p in ps]
    names = [p.label or "#%d" % p.id for p in ps]
    out, vis = find_buried([p.tm for p in ps], ks, R.model_size, names=names, log=log)
    if not out:
        return 0
    for i in sorted(out):
        log("  [chim trong] xoa %s (%s, %d mat): %s" % (names[i], ks[i], len(ps[i].tm.F), out[i]))
    gone = {ps[i].id for i in out}
    R.pieces = [p for p in R.pieces if p.id not in gone]
    log("[chim trong] xoa %d manh (chim ben trong / trung khit / vun)" % len(out))
    return len(out)


def far_anchors(tms, size, n_cand=96):
    """Diem neo cho tung manh = tam mot MAT LON (uu tien mat that, khong phai nap cat) KHONG nam sat manh khac. Tam mat
    lon nhat hay nam dung mat tiep xuc (cat phan chim xong, mat lon nhat la mat ap sat manh ben canh) -> diem neo cach
    deu hai manh -> nhan / to mau trao nham manh (gau truc 2026-10-08: "tai trai" sang mui mu, P04 mat ten)."""
    from mathutils import Vector
    bb = [(t.V.min(0), t.V.max(0)) for t in tms]
    pad, enough = 0.02 * size, 0.01 * size
    bv = {}
    out = []
    for i, t in enumerate(tms):
        A = t.face_areas()
        cap = np.asarray(t.cap) if len(t.cap) == len(t.F) else np.full(len(t.F), -1)
        pool = np.where((cap < 0) & (A > 0))[0]
        if not len(pool):
            pool = np.arange(len(t.F))
        order = pool[np.argsort(-A[pool])]
        step = max(1, len(order) // (n_cand // 2))
        cand = list(dict.fromkeys(order[:n_cand // 2].tolist() + order[::step].tolist()))
        C = t.face_centers()
        lo, hi = bb[i]
        nb = [j for j in range(len(tms)) if j != i
              and not ((bb[j][1] < lo - pad).any() or (bb[j][0] > hi + pad).any())]
        for j in nb:
            if j not in bv:
                bv[j] = _bvh(tms[j])
        best, bd = C[cand[0]], -1.0
        for f in cand:
            if not nb:
                break
            d = min(_dist(bv[j].find_nearest(Vector(C[f]))) for j in nb)
            if d > bd:
                best, bd = C[f], d
            if bd >= enough:                      # mat lon dau tien da xa cac manh khac -> lay (on dinh)
                break
        out.append([float(x) for x in best])
    return out
