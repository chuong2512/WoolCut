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
