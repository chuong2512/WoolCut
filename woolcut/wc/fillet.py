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


STITCH_D = 2.2           # vung lay ban voxel: sau D x w tinh tu mat cat (voxel da ep ve be mat goc tu 1.6 w)
WHY = []                 # ly do ghep hong gan nhat (do loi)
STITCH_GAP = 0.35        # khe giua hai phan (x w) - dai noi co be rong that, khong suy bien


CHAMFER_W = 0.025        # vat 45 do kieu BearArt: be rong ~0,25% co model (co 10); BearArt do duoc 0,21%
CHAMFER_GAP = 0.02       # khe giua hai manh ke nhau (moi ben lui mot nua); BearArt 0,2-0,3% co
CHAMFER_ID = 6000        # ma "nap" cho vong vat -> do bong sac (canh sac giua nap | vat | be mat) nhu BearArt


def chamfer(t, width=CHAMFER_W, gap=CHAMFER_GAP, log=None):
    """MEP CAT KIEU BEARART (2026-10-08, nguoi dung: "phan tich vet cat BearArt... de giam mesh"): nap PHANG + MOT vong vat
    45 do (bmesh bevel 1 nac) + khe nho (nap lui vao gap/2). Do tren dau chia 3 lat: 2.644 tam giac (bo tron ghep lai
    5.828); sau xuat toi uu 0,2%: 1.254 vs 1.606. Hong (khong kin) -> giu mep vuong (van kin)."""
    import bmesh
    from mathutils import Vector
    if not (t.cap >= 0).any():
        return t
    bm = _bm_from_tm(t)
    lay = bm.faces.layers.int.new("cap")
    bm.faces.ensure_lookup_table()
    for i, f in enumerate(bm.faces):
        if i < len(t.cap):
            f[lay] = int(t.cap[i])
    rim = [e for e in bm.edges if len(e.link_faces) == 2 and (
        (e.link_faces[0][lay] >= 0) != (e.link_faces[1][lay] >= 0) or
        (e.link_faces[0][lay] >= 0 and e.link_faces[0][lay] != e.link_faces[1][lay]))]
    if not rim:
        bm.free()
        return t
    try:
        res = bmesh.ops.bevel(bm, geom=rim, offset=float(width), offset_type="OFFSET", segments=1, profile=0.5,
                              affect="EDGES", clamp_overlap=True)
    except Exception as e:
        bm.free()
        if log:
            log("  (vat mep loi: %s - giu mep vuong)" % e)
        return t
    for f in res.get("faces", []):
        f[lay] = CHAMFER_ID
    if gap > 0:                                       # khe: lui nap vao trong gap/2 theo phap tuyen nap
        bm.normal_update()
        for cid in set(int(c) for c in t.cap if c >= 0):
            fs = [f for f in bm.faces if f[lay] == cid]
            if not fs:
                continue
            n = sum((f.normal * f.calc_area() for f in fs), Vector())
            if n.length < 1e-12:
                continue
            n.normalize()
            for v in {v for f in fs for v in f.verts}:
                v.co -= n * (gap / 2)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.verts.index_update()
    V = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3)
    F = np.array([[v.index for v in f.verts] for f in bm.faces], dtype=np.int64).reshape(-1, 3)
    cap = np.array([f[lay] for f in bm.faces], dtype=np.int64)
    bm.free()
    out = TM(V, F, cap=cap)
    if not out.is_closed() or abs(out.volume()) < 0.5 * abs(t.volume()):
        if log:
            log("  (vat mep: khong kin - giu mep vuong)")
        return t
    if KDTree is not None:
        kd = KDTree(len(t.F))
        for i, c in enumerate(t.face_centers()):
            kd.insert(Vector(c), i)
        kd.balance()
        out.col = np.array([t.col[kd.find(Vector(c))[1]] for c in out.face_centers()], dtype=np.int64)
    return out


def fillet(t, w, log=None, style=None):
    """Kieu mep cat: style "chamfer" (vat nhu BearArt, it mat) hoac "round" (bo tron ghep lai, mac dinh). Khong truyen
    style -> bien moi truong WOOLCUT_CUT_STYLE (panel dat cho tien trinh nen)."""
    import os
    style = (style or os.environ.get("WOOLCUT_CUT_STYLE") or "round").lower()
    if style == "chamfer":
        return chamfer(t, log=log) if w > 0 else t
    return fillet_round(t, w, log=log)


def fillet_round(t, w, log=None):
    """BO CONG MAC DINH = GHEP LAI (2026-10-08). Nguoi dung: "mat gan phan cat thi sua, khong lien quan thi giu nguyen"
    roi "chia manh xau hon truoc" khi doi sang fillet_geo cuc bo (vo mong: mep vuong, vanh rang cua). Nay: SAT mat cat lay
    ban voxel bo tron (fillet_voxel, nhu truoc), XA mat cat giu NGUYEN luoi goc, noi hai phan bang mot dai hep tren be mat
    (_stitch: cat theo duong dong muc khoang cach toi mat nap - dung ca nap cong cua cat theo nep). Ghep hong (khong
    kin, lech the tich, so vong lech) -> dung ban voxel nhu truoc. Do: SnowBearChef 10/10 nhat, xe may 4/6, giu 100%
    be mat xa mep; nut Chia 3 lat: dau giu 88% dinh goc, vo ao mong 75% (voxel: 0%)."""
    if w <= 0 or not (t.cap >= 0).any():
        return t
    v = fillet_voxel(t, w, log=log)
    if v is t:
        return t
    try:
        h = _stitch(t, v, w)
    except Exception as e:
        h, why = None, "loi %s" % e
    else:
        why = "" if h is not None else ("khong ghep duoc: " + (WHY[-1] if WHY else "?"))
    if h is None:
        if log:
            log("  (bo cong: %s - dung ban voxel ca manh)" % why)
        return v
    return h


def _bm_from_tm(t):
    import bmesh
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in t.V.tolist()]
    for f in t.F.tolist():
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    return bm


def _tm_from_bm(bm):
    import bmesh
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.verts.index_update()
    V = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3)
    F = np.array([[v.index for v in f.verts] for f in bm.faces], dtype=np.int64).reshape(-1, 3)
    return TM(V, F)


def _loops(bm, edges):
    """Canh bien -> cac vong (danh sach canh), moi vong lien thong qua dinh."""
    left, out = set(edges), []
    while left:
        st = [left.pop()]
        comp = [st[0]]
        while st:
            e = st.pop()
            for v in e.verts:
                for e2 in v.link_edges:
                    if e2 in left:
                        left.discard(e2)
                        comp.append(e2)
                        st.append(e2)
        out.append(comp)
    return out


def _ring(edges):
    """Danh sach canh cua MOT vong bien -> danh sach dinh theo thu tu di vong (None neu khong phai vong don)."""
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if any(len(x) != 2 for x in adj.values()):
        return None
    start = edges[0].verts[0]
    out, prev, cur = [start], None, start
    while True:
        nxt = adj[cur][0] if adj[cur][0] is not prev else adj[cur][1]
        if nxt is start:
            break
        out.append(nxt)
        prev, cur = cur, nxt
        if len(out) > len(adj):
            return None
    return out if len(out) == len(adj) else None


def _zipper(bm, ea, eb):
    """NOI hai vong bien gan song song (vong luoi goc a, vong voxel b) bang dai tam giac kieu KHOA KEO: cung chieu (Newell),
    bat dau o cap dinh gan nhau nhat, tien theo ti le chieu dai cung -> khong xoan (bmesh bridge_loops xoan tren vali chia
    luoi 3x3 -> tam giac lon bi gap). Tra ve True neu noi xong."""
    import numpy as np
    from mathutils import Vector
    A, B = _ring(ea), _ring(eb)
    if not A or not B or len(A) < 3 or len(B) < 3:
        return False

    def newell(L):
        n = Vector()
        for i in range(len(L)):
            p, q = L[i].co, L[(i + 1) % len(L)].co
            n += Vector(((p.y - q.y) * (p.z + q.z), (p.z - q.z) * (p.x + q.x), (p.x - q.x) * (p.y + q.y)))
        return n
    if newell(A).dot(newell(B)) < 0:
        B = B[::-1]
    k = min(range(len(B)), key=lambda i: (B[i].co - A[0].co).length)
    B = B[k:] + B[:k]

    def params(L):
        d = [(L[(i + 1) % len(L)].co - L[i].co).length for i in range(len(L))]
        tot = sum(d) or 1.0
        t = np.concatenate([[0.0], np.cumsum(d)]) / tot
        return t                                       # len(L)+1, t[-1] = 1
    ta, tb = params(A), params(B)
    na, nb_ = len(A), len(B)
    i = j = 0
    while i < na or j < nb_:
        a0, b0 = A[i % na], B[j % nb_]
        if j >= nb_ or (i < na and ta[i + 1] <= tb[j + 1]):
            tri = (a0, A[(i + 1) % na], b0)
            i += 1
        else:
            tri = (a0, B[(j + 1) % nb_], b0)
            j += 1
        if len(set(tri)) == 3:
            try:
                bm.faces.new(tri)
            except ValueError:
                pass
    return True


def _folds(t, min_area):
    """So mat GAP (phap tuyen nguoc huong trung binh cac mat ke) co dien tich > min_area."""
    import numpy as np
    N, A = t.face_normals(), t.face_areas()
    N = N / np.maximum(np.linalg.norm(N, axis=1), 1e-20)[:, None]
    ef, cnt = t.edge_faces()
    E, FE = t.edges()
    acc = np.zeros((len(t.F), 3))
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    a, b = ef[ok, 0], ef[ok, 1]
    np.add.at(acc, a, N[b] * A[b, None])
    np.add.at(acc, b, N[a] * A[a, None])
    nrm = np.linalg.norm(acc, axis=1)
    good = nrm > 1e-12
    dot = np.zeros(len(t.F))
    dot[good] = (N[good] * acc[good]).sum(1) / nrm[good]
    return int(((dot < -0.5) & (A > min_area)).sum())


def _iso_keep(t, s, level, above):
    """Cat luoi tam giac theo DUONG DONG MUC s = level (s = gia tri tai dinh, noi suy tuyen tinh tren canh); giu phan
    s >= level (above) hoac s <= level. Tra ve TM HO, bien nam dung tren duong dong muc."""
    V = [tuple(x) for x in t.V.tolist()]
    ins = (s >= level) if above else (s <= level)
    cut = {}

    def mid(i, j):
        k = (i, j) if i < j else (j, i)
        if k not in cut:
            d = s[j] - s[i]
            u = 0.5 if abs(d) < 1e-12 else min(1.0, max(0.0, (level - s[i]) / d))
            V.append(tuple(t.V[i] + u * (t.V[j] - t.V[i])))
            cut[k] = len(V) - 1
        return cut[k]
    F = []
    for f in t.F.tolist():
        m = [bool(ins[x]) for x in f]
        n = sum(m)
        if n == 3:
            F.append(f)
        elif n == 0:
            continue
        else:
            r = next(q for q in range(3) if (m[q] if n == 1 else not m[q]))      # dinh "le" dua len dau, giu chieu
            a, b_, c = f[r], f[(r + 1) % 3], f[(r + 2) % 3]
            if n == 1:                              # a trong, b c ngoai
                F.append([a, mid(a, b_), mid(a, c)])
            else:                                   # a ngoai, b c trong
                mab, mac = mid(a, b_), mid(a, c)
                F.append([mab, b_, c])
                F.append([mab, c, mac])
    if not F:
        return TM(np.zeros((0, 3)), np.zeros((0, 3), np.int64))
    F = np.array(F, dtype=np.int64)
    used, inv = np.unique(F.ravel(), return_inverse=True)
    return TM(np.array(V)[used], inv.reshape(-1, 3))


def _stitch(t, v, w):
    """t = manh goc (mat nap ma >= 0), v = ban voxel bo tron cua no. s = khoang cach toi MAT NAP (moi nhat cat, ca nap
    cong cua cat theo nep): giu t o s >= D (xa), giu v o s <= D - khe (gan), bac cau hai duong dong muc bang dai hep.
    Manh nho nam tron trong vung gan -> tra ve v. Tra ve TM kin hoac None."""
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    capf = np.where(t.cap >= 0)[0]
    if not len(capf):
        WHY.append("khong co nap")
        return None
    cb = BVHTree.FromPolygons([Vector(x) for x in t.V], [tuple(int(i) for i in t.F[f]) for f in capf], all_triangles=True)

    def dist(P):
        out = np.empty(len(P))
        for i, x in enumerate(P):
            h = cb.find_nearest(Vector(x))
            out[i] = h[3] if h[3] is not None else 1e9
        return out
    D, gap = STITCH_D * w, STITCH_GAP * w
    sO, sV = dist(t.V), dist(v.V)
    if sO.max() <= D + gap:                         # ca manh nam trong dai bo cong -> ban voxel la dung
        return v
    far = _iso_keep(t, sO, D, above=True)
    near = _iso_keep(v, sV, D - gap, above=False)
    if not len(far.F) or not len(near.F):
        WHY.append("cat rong far %d near %d" % (len(far.F), len(near.F)))
        return None
    bm = _bm_from_tm(TM(np.concatenate([far.V, near.V]), np.concatenate([far.F, near.F + len(far.V)])))
    nf = len(far.V)
    bm.verts.index_update()                            # chi so dinh moi tao chua dung -> vong nao cung "far"
    bnd = [e for e in bm.edges if e.is_boundary]
    ls = _loops(bm, bnd)
    lf = [l for l in ls if l[0].verts[0].index < nf]
    ln = [l for l in ls if l[0].verts[0].index >= nf]
    if not lf or len(lf) != len(ln):
        WHY.append("so vong far %d near %d" % (len(lf), len(ln)))
        bm.free()
        return None

    def cen(l):
        return sum((x.co for e in l for x in e.verts), Vector()) / (2 * len(l))
    used = set()
    for a in lf:
        ca = cen(a)
        j = min((k for k in range(len(ln)) if k not in used), key=lambda k: (cen(ln[k]) - ca).length)
        used.add(j)
        if not _zipper(bm, a, ln[j]):
            WHY.append("khong noi duoc vong")
            bm.free()
            return None
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    cur = _tm_from_bm(bm)
    bm.free()
    if not cur.is_closed():
        _, cnt_ = cur.edge_faces()
        WHY.append("sau bac cau khong kin: %d canh hong" % int((cnt_ != 2).sum()))
        return None
    nfold = _folds(cur, 0.05 * w * w)
    if nfold:                                          # 2026-10-08: vali chia luoi 3x3 - bridge_loops xoan -> tam giac gap
        WHY.append("%d mat gap" % nfold)
        return None
    if abs(abs(cur.volume()) - abs(v.volume())) > 0.03 * abs(v.volume()):
        WHY.append("lech the tich %.3f vs %.3f" % (cur.volume(), v.volume()))
        return None
    if len(cur.split_components()) != len(v.split_components()):
        WHY.append("so khoi %d vs %d" % (len(cur.split_components()), len(v.split_components())))
        return None
    if KDTree is not None:                                  # mau theo mat goc gan nhat; khong con nap
        kd = KDTree(len(t.F))
        for i, c in enumerate(t.face_centers()):
            kd.insert(Vector(c), i)
        kd.balance()
        cur.col = np.array([t.col[kd.find(Vector(c))[1]] for c in cur.face_centers()], dtype=np.int64)
    return cur


def fillet_voxel(t, w, log=None, face_mult=3.0, keep_surface=True, band=1.6):
    """(Cu, khong con mac dinh) BO CONG VOXEL (2026-10-05, thay fillet_geo hay that bai o vo mong / cho hep): dung lai
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
