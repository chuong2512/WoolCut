"""Luoi tam giac numpy va cac nhat CAT MAT PHANG - loi hinh hoc cua woolcut.

Moi manh la mot khoi KIN (moi canh dung 2 mat). Mot nhat cat:
  1. tinh giao tuyen cua mat phang voi luoi -> cac VONG kin nam tren mat phang;
  2. chon vong can cat (cuc bo: vong quanh diem chi dinh, nhu cai co; toan bo: moi vong);
  3. chia tam giac doc theo vong, nhan doi dinh tren vong (moi ben mot ban) -> luoi tach doi;
  4. bit NAP PHANG hai ben bang cung mot phep tam giac hoa (CDT 2D) -> hai manh kin, khit nhau.
Vi nap phang va hai ben dung chung mot luoi nap, hai manh ghep lai lien mach nhu bo goc (dau gau
BearArt chia 8 mui bang 3 mat phang qua tam).
Can mathutils (Blender) cho CDT; phan con lai la numpy thuan."""
import math, collections
import numpy as np

try:
    from mathutils import Vector
    from mathutils.geometry import delaunay_2d_cdt
except ImportError:          # chay ngoai Blender: chi khong bit nap duoc
    Vector = delaunay_2d_cdt = None


def piece_axes(V, F=None):
    """Truc rieng cua khoi (PCA be mat co trong so dien tich): (truc, phuong sai) giam dan - dai, giua, ngan.
    Moi truc quay ve phia duong cua truc the gioi gan no nhat."""
    V = np.asarray(V, dtype=np.float64)
    if F is not None and len(F):
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        P, w = (a + b + c) / 3.0, np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2.0
    else:
        P, w = V, np.ones(len(V))
    w = w / (w.sum() or 1.0)
    m = (P * w[:, None]).sum(0)
    D = P - m
    lam, U = np.linalg.eigh((D * w[:, None]).T @ D)
    axes = []
    for k in (2, 1, 0):
        u = U[:, k]
        j = int(np.argmax(np.abs(u)))
        axes.append(u if u[j] >= 0 else -u)
    return axes, lam[::-1]


TILT_MIN = 12.0       # do: khoi nghieng it hon -> giu truc the gioi (cat chuan nhu BearArt)
ELONG_MIN = 1.4       # do dai / do day (theo do lech chuan) - duoi muc nay la khoi tron, truc PCA vo nghia


def piece_frame(V, F=None):
    """Ma tran xoay R (cot j = truc j MOI) dua he truc the gioi theo khoi DAI NAM NGHIENG (ong kinh, chan may, tay
    gio cheo): truc the gioi gan truc dai nhat -> truc dai, xoay nho nhat (Rodrigues). Khoi tron / dung thang /
    nghieng < TILT_MIN -> I. Moi kieu chia (split, slices, sectors, grid) dung R: 'axis z' cua ong nghieng = truc ong."""
    (u, _, _), lam = piece_axes(V, F)
    I = np.eye(3)
    if lam[0] <= 0 or math.sqrt(lam[0] / max(lam[1], 1e-12)) < ELONG_MIN:
        return I
    k = int(np.argmax(np.abs(u)))
    c = float(np.clip(u[k], -1.0, 1.0))
    if math.degrees(math.acos(c)) < TILT_MIN:
        return I
    v = np.cross(I[k], u)
    s2 = float(v @ v)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return I + K + K @ K * ((1.0 - c) / s2)


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def basis(n):
    """Hai truc u, w vuong goc voi n sao cho (u, w, n) thuan tay phai."""
    n = unit(n)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = unit(np.cross(a, n))
    w = np.cross(n, u)
    return u, w


def poly_area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def in_poly(Q, P):
    """Diem Q [k,2] nam trong da giac P [m,2]? (tia ngang, chan/le)."""
    Q = np.atleast_2d(Q)
    x, y = Q[:, 0][:, None], Q[:, 1][:, None]
    x1, y1 = P[:, 0][None], P[:, 1][None]
    x2, y2 = np.roll(P[:, 0], -1)[None], np.roll(P[:, 1], -1)[None]
    cond = (y1 > y) != (y2 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
    return ((cond & (x < xi)).sum(1) % 2) == 1


def seg_dist(q, P):
    """Khoang cach tu diem q [2] toi duong vien da giac P."""
    A, B = P, np.roll(P, -1, axis=0)
    AB = B - A
    t = np.clip(((q - A) * AB).sum(1) / np.maximum((AB * AB).sum(1), 1e-30), 0, 1)
    C = A + AB * t[:, None]
    return float(np.sqrt(((C - q) ** 2).sum(1)).min())


class TM:
    """V [n,3], F [m,3] (tam giac, pháp tuyen ra ngoai), col [m] (chi so mau, -1 = chua co),
    cap [m] (ma nhat cat neu la mat nap, -1 = mat that)."""

    def __init__(self, V, F, col=None, cap=None):
        self.V = np.asarray(V, dtype=np.float64).reshape(-1, 3)
        self.F = np.asarray(F, dtype=np.int64).reshape(-1, 3)
        m = len(self.F)
        self.col = np.full(m, -1, np.int64) if col is None else np.asarray(col, np.int64).copy()
        self.cap = np.full(m, -1, np.int64) if cap is None else np.asarray(cap, np.int64).copy()
        self.meta = {}
        self._E = None

    # ------------------------------------------------------------ co ban
    def copy(self):
        t = TM(self.V.copy(), self.F.copy(), self.col, self.cap)
        t.meta = dict(self.meta)
        return t

    @property
    def size(self):
        return float(np.linalg.norm(self.V.max(0) - self.V.min(0))) if len(self.V) else 0.0

    def bbox(self):
        return self.V.min(0), self.V.max(0)

    def face_areas(self):
        a, b, c = self.V[self.F[:, 0]], self.V[self.F[:, 1]], self.V[self.F[:, 2]]
        return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)

    def face_normals(self):
        a, b, c = self.V[self.F[:, 0]], self.V[self.F[:, 1]], self.V[self.F[:, 2]]
        return np.cross(b - a, c - a)

    def face_centers(self):
        return self.V[self.F].mean(1)

    def volume(self):
        a, b, c = self.V[self.F[:, 0]], self.V[self.F[:, 1]], self.V[self.F[:, 2]]
        return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    def centroid(self):
        """Tam khoi (the tich); khoi hong/vo thi lay tam dien tich."""
        a, b, c = self.V[self.F[:, 0]], self.V[self.F[:, 1]], self.V[self.F[:, 2]]
        v = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
        if abs(v.sum()) > 1e-12 * max(self.size, 1e-9) ** 3:
            return ((a + b + c) / 4.0 * v[:, None]).sum(0) / v.sum()
        ar = self.face_areas()
        return (self.face_centers() * ar[:, None]).sum(0) / max(ar.sum(), 1e-30)

    def edges(self):
        """(E [k,2] canh duy nhat, FE [m,3] canh cua tung mat theo thu tu (01),(12),(20))."""
        if self._E is None:
            F = self.F
            e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
            es = np.sort(e, axis=1)
            nv = max(len(self.V), 1)
            key = es[:, 0] * nv + es[:, 1]
            uk, inv = np.unique(key, return_inverse=True)
            E = np.stack([uk // nv, uk % nv], axis=1)
            FE = inv.reshape(3, -1).T
            self._E = (E, FE)
        return self._E

    def edge_faces(self):
        """Danh sach mat ke cua tung canh (mang [k,2], -1 neu thieu; canh > 2 mat danh dau -2)."""
        E, FE = self.edges()
        k = len(E)
        ef = np.full((k, 2), -1, np.int64)
        cnt = np.zeros(k, np.int64)
        m = len(self.F)
        for j in range(3):
            for f, e in zip(range(m), FE[:, j]):
                c = cnt[e]
                if c < 2:
                    ef[e, c] = f
                cnt[e] += 1
        ef[cnt > 2] = -2
        return ef, cnt

    def is_closed(self):
        _, cnt = self.edge_faces()
        return bool((cnt == 2).all())

    def components(self):
        """Nhan thanh phan lien thong cua MAT (qua canh chung)."""
        ef, cnt = self.edge_faces()
        m = len(self.F)
        par = list(range(m))

        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for a, b in ef[(ef[:, 0] >= 0) & (ef[:, 1] >= 0)]:
            ra, rb = find(int(a)), find(int(b))
            if ra != rb:
                par[ra] = rb
        roots = np.array([find(i) for i in range(m)])
        _, lab = np.unique(roots, return_inverse=True)
        return lab

    def subset(self, faces):
        """Manh moi gom cac mat chi dinh (dinh danh lai)."""
        faces = np.asarray(faces)
        F = self.F[faces]
        used, inv = np.unique(F.ravel(), return_inverse=True)
        t = TM(self.V[used], inv.reshape(-1, 3), self.col[faces], self.cap[faces])
        return t

    def split_components(self, min_faces=1):
        lab = self.components()
        out = []
        for k in range(lab.max() + 1 if len(lab) else 0):
            fs = np.where(lab == k)[0]
            if len(fs) >= min_faces:
                out.append(self.subset(fs))
        return out

    # ------------------------------------------------------------ trong / ngoai
    def ray_hits(self, q, d):
        """So lan tia q + t d (t > 0) cat luoi (Moller-Trumbore, vector hoa)."""
        a, b, c = self.V[self.F[:, 0]], self.V[self.F[:, 1]], self.V[self.F[:, 2]]
        e1, e2 = b - a, c - a
        p = np.cross(d, e2)
        det = (e1 * p).sum(1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        s = q - a
        u = (s * p).sum(1) * inv
        qv = np.cross(s, e1)
        v = (qv * d).sum(1) * inv
        t = (qv * e2).sum(1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-12)
        return int(hit.sum())

    def contains(self, q):
        q = np.asarray(q, dtype=np.float64)
        votes = 0
        for d in ((0.5773, 0.5774, 0.5775), (-0.31, 0.71, -0.63), (0.83, -0.42, 0.37)):
            votes += self.ray_hits(q, np.asarray(d)) % 2
        return votes >= 2

    def dist(self, q):
        """Khoang cach xap xi tu q toi be mat (dinh va tam mat)."""
        q = np.asarray(q, dtype=np.float64)
        d1 = np.sqrt(((self.V - q) ** 2).sum(1)).min() if len(self.V) else 1e9
        d2 = np.sqrt(((self.face_centers() - q) ** 2).sum(1)).min() if len(self.F) else 1e9
        return float(min(d1, d2))

    # ------------------------------------------------------------ lam min
    def taubin(self, iters=8, lam=0.5, mu=-0.53, keep=None):
        """Lam min Taubin (khong co lai). keep: mask dinh dung yen."""
        E, _ = self.edges()
        n = len(self.V)
        deg = np.bincount(E.ravel(), minlength=n).astype(np.float64)
        deg[deg == 0] = 1
        for _ in range(iters):
            for f in (lam, mu):
                S = np.zeros_like(self.V)
                np.add.at(S, E[:, 0], self.V[E[:, 1]])
                np.add.at(S, E[:, 1], self.V[E[:, 0]])
                L = S / deg[:, None] - self.V
                if keep is not None:
                    L[keep] = 0
                self.V = self.V + f * L

    def smooth_labels(self, labels, iters=2, weight_self=1.2):
        """Loc da so nhan mau tren mat (xoa rang cua do voxel)."""
        ef, _ = self.edge_faces()
        good = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
        A, B = ef[good, 0], ef[good, 1]
        lab = np.asarray(labels).copy()
        area = self.face_areas()
        K = lab.max() + 1 if len(lab) else 1
        for _ in range(iters):
            W = np.zeros((len(lab), K))
            np.add.at(W, (np.arange(len(lab)), lab), area * weight_self)
            np.add.at(W, (A, lab[B]), area[B])
            np.add.at(W, (B, lab[A]), area[A])
            new = W.argmax(1)
            new[lab < 0] = lab[lab < 0]
            lab = new
        return lab

    # ------------------------------------------------------------ giao tuyen
    def section(self, p, n):
        """Giao tuyen voi mat phang (p, n). Tra ve dict: p (da xe dich tranh dinh nam dung mat phang),
        n, u, w, d (khoang cach co dau tung dinh), loops: [{edges, faces, P3, P2, area, closed}]."""
        n = unit(n)
        p0 = np.asarray(p, dtype=np.float64).copy()
        E, FE = self.edges()
        # Diem giao khong duoc sat dinh (t < 3% hoac > 97% canh): nhieu diem giao gan trung nhau lam CDT
        # gop dinh -> nap ho. Xe mat phang di mot chut (vai % canh luoi, mat thuong khong thay) roi thu lai.
        el = np.linalg.norm(self.V[E[:, 0]] - self.V[E[:, 1]], axis=1)
        step = 0.031 * float(np.median(el)) if len(el) else 1e-6
        best = None
        for i in range(25):
            off = 0.0 if i == 0 else step * ((i + 1) // 2) * (1 if i % 2 else -1)
            p = p0 + n * off
            d = (self.V - p) @ n
            s = d > 0
            ec = s[E[:, 0]] != s[E[:, 1]]
            if not ec.any():
                best = (1.0, p, d, s, ec)
                break
            da, db = d[E[ec, 0]], d[E[ec, 1]]
            with np.errstate(divide="ignore", invalid="ignore"):
                t = da / (da - db)
            margin = float(np.nanmin(np.minimum(t, 1 - t))) if len(t) else 1.0
            if best is None or margin > best[0]:
                best = (margin, p, d, s, ec)
            if margin >= 0.03 and not (np.abs(d) < 1e-9 * max(self.size, 1e-9)).any():
                break
        _, p, d, s, ec = best
        fcnt = ec[FE].sum(1)
        cf = np.where(fcnt == 2)[0]
        u, w = basis(n)
        out = dict(p=p, n=n, u=u, w=w, d=d, loops=[])
        if len(cf) == 0:
            return out
        sub = FE[cf]
        pairs = sub[ec[sub]].reshape(-1, 2)
        e2f = collections.defaultdict(list)
        for i, (a, b) in enumerate(pairs):
            e2f[int(a)].append(i)
            e2f[int(b)].append(i)
        used = np.zeros(len(cf), bool)
        for st in range(len(cf)):
            if used[st]:
                continue
            faces, edges = [], []
            closed = True
            i = st
            prev_e = int(pairs[st][0])
            # di theo chieu: tu canh prev_e qua mat i sang canh kia
            while True:
                used[i] = True
                faces.append(int(cf[i]))
                a, b = int(pairs[i][0]), int(pairs[i][1])
                nxt = b if a == prev_e else a
                edges.append(nxt)
                cand = [j for j in e2f[nxt] if j != i]
                if len(e2f[nxt]) != 2 or not cand:
                    closed = False
                    break
                j = cand[0]
                if j == st:
                    break
                if used[j]:
                    closed = False
                    break
                prev_e, i = nxt, j
            ea = np.array(edges)
            va, vb = E[ea, 0], E[ea, 1]
            t = d[va] / (d[va] - d[vb])
            P3 = self.V[va] + (self.V[vb] - self.V[va]) * t[:, None]
            P2 = np.stack([(P3 - p) @ u, (P3 - p) @ w], axis=1)
            out["loops"].append(dict(edges=ea, faces=np.array(faces), P3=P3, P2=P2,
                                     area=abs(poly_area(P2)) if closed and len(ea) >= 3 else 0.0,
                                     closed=closed and len(ea) >= 3))
        # do sau long nhau (vong ngoai = 0, lo = 1, dao trong lo = 2 ...)
        L = [l for l in out["loops"] if l["closed"]]
        for l in L:
            l["depth"] = sum(1 for o in L if o is not l and o["area"] > l["area"] and in_poly(l["P2"][:1], o["P2"])[0])
        return out

    def region(self, sec, q=None, mode="local"):
        """Chon cac vong se cat. local: vung vat lieu chua (hoac gan nhat) diem q - vong ngoai + cac lo
        truc tiep cua no. all: moi vong kin. Tra ve (danh sach vong, dien tich vung) hoac (None, 0)."""
        L = [l for l in sec["loops"] if l["closed"]]
        if not L:
            return None, 0.0
        if mode == "all":
            area = sum(l["area"] * (1 if l["depth"] % 2 == 0 else -1) for l in L)
            return L, area
        q2 = np.array([(np.asarray(q) - sec["p"]) @ sec["u"], (np.asarray(q) - sec["p"]) @ sec["w"]])
        inside = [l for l in L if in_poly(q2[None], l["P2"])[0]]
        outer = None
        if inside:
            inner = min(inside, key=lambda l: l["area"])
            if inner["depth"] % 2 == 0:
                outer = inner
        if outer is None:
            outs = [l for l in L if l["depth"] % 2 == 0]
            if not outs:
                return None, 0.0
            outer = min(outs, key=lambda l: seg_dist(q2, l["P2"]))
        holes = [l for l in L if l["depth"] == outer["depth"] + 1 and l["area"] < outer["area"]
                 and in_poly(l["P2"][:1], outer["P2"])[0]]
        return [outer] + holes, outer["area"] - sum(h["area"] for h in holes)

    # ------------------------------------------------------------ cat
    def cut(self, sec, loops, cut_id):
        """Cat doc cac vong da chon va bit nap phang ca hai ben. Tra ve danh sach manh moi (>= 2),
        hoac None neu nhat cat khong tach roi luoi (vd vong quanh quai cam)."""
        if not loops or delaunay_2d_cdt is None:
            return None
        E, FE = self.edges()
        d = sec["d"]
        V, F = self.V, self.F
        nV = len(V)
        sel_e = np.unique(np.concatenate([l["edges"] for l in loops]))
        sel_f = np.unique(np.concatenate([l["faces"] for l in loops]))
        va, vb = E[sel_e, 0], E[sel_e, 1]
        t = d[va] / (d[va] - d[vb])
        P = V[va] + (V[vb] - V[va]) * t[:, None]          # diem giao tung canh, dung chung moi vong
        k = len(sel_e)
        eidx = {int(e): i for i, e in enumerate(sel_e)}
        # ---- nap: CDT 2D cua vung (vong ngoai + lo), dung chung cho hai ben
        u, w, p = sec["u"], sec["w"], sec["p"]
        P2 = np.stack([(P - p) @ u, (P - p) @ w], axis=1)
        cons, loop_polys = [], []
        for l in loops:
            ids = [eidx[int(e)] for e in l["edges"]]
            cons += [(ids[i], ids[(i + 1) % len(ids)]) for i in range(len(ids))]
            loop_polys.append(P2[ids])
        sc = max(float(np.abs(P2).max()), 1e-9)
        coords = [Vector((float(x / sc), float(y / sc))) for x, y in P2]
        res = delaunay_2d_cdt(coords, cons, [], 0, 1e-12)
        vo, fo, ov = res[0], res[2], res[3]
        vmap, extra = [], []
        if any(len(o) > 1 for o in ov):
            return None                                  # CDT gop hai diem vong -> nap se ho
        for i, orig in enumerate(ov):
            if orig:
                vmap.append(int(orig[0]))
            else:                                       # diem moi (canh vong cat nhau - hiem)
                vmap.append(k + len(extra))
                extra.append((vo[i][0] * sc, vo[i][1] * sc))
        X3 = (p + np.array([e[0] for e in extra])[:, None] * u + np.array([e[1] for e in extra])[:, None] * w
              if extra else np.zeros((0, 3)))
        blk = np.concatenate([P, X3])
        K = len(blk)

        def posv(i):
            return nV + i

        def negv(i):
            return nV + K + i
        newF, newC, newK = [], [], []
        for f in sel_f:
            vs = F[f]
            es = FE[f]                                  # canh (v0v1), (v1v2), (v2v0)
            sg = d[vs] > 0
            if sg[0] != sg[1] and sg[0] != sg[2]:       # dinh le loi: khac phia hai dinh kia
                r = 0
            elif sg[1] != sg[0] and sg[1] != sg[2]:
                r = 1
            else:
                r = 2
            x, y, z = vs[r], vs[(r + 1) % 3], vs[(r + 2) % 3]
            exy, ezx = int(es[r]), int(es[(r + 2) % 3])
            if exy not in eidx or ezx not in eidx:
                return None
            own, oth = (posv, negv) if sg[r] else (negv, posv)
            ixy, izx = eidx[exy], eidx[ezx]
            newF += [(x, own(ixy), own(izx)), (oth(ixy), y, z), (oth(ixy), z, oth(izx))]
            newC += [self.col[f]] * 3
            newK += [self.cap[f]] * 3
        # trong/ngoai cua tung tam giac CDT: loang tu bao loi (ngoai), qua canh rang buoc (canh vong) thi
        # doi chan/le. Chinh xac theo topo, khong phu thuoc sai so cua tam giac manh sat vien.
        tris = [tuple(t_) for t_ in fo if len(t_) == 3]
        cset = set()
        for a_, b_ in cons:
            cset.add((min(a_, b_), max(a_, b_)))
        ov_of = {}
        for i, orig in enumerate(ov):
            for o_ in orig:
                ov_of[o_] = i
        cset = {(min(ov_of[a_], ov_of[b_]), max(ov_of[a_], ov_of[b_])) for a_, b_ in cset}
        e2t = collections.defaultdict(list)
        for ti, tri in enumerate(tris):
            for j in range(3):
                a_, b_ = tri[j], tri[(j + 1) % 3]
                e2t[(min(a_, b_), max(a_, b_))].append(ti)
        par = [-1] * len(tris)
        dq = collections.deque()
        for e_, ts in e2t.items():
            if len(ts) == 1 and par[ts[0]] < 0:
                par[ts[0]] = 1 if e_ in cset else 0
                dq.append(ts[0])
        while dq:
            ti = dq.popleft()
            tri = tris[ti]
            for j in range(3):
                a_, b_ = tri[j], tri[(j + 1) % 3]
                e_ = (min(a_, b_), max(a_, b_))
                for tj in e2t[e_]:
                    if tj != ti and par[tj] < 0:
                        par[tj] = par[ti] ^ (1 if e_ in cset else 0)
                        dq.append(tj)
        ccount = 0
        for ti, tri in enumerate(tris):
            if par[ti] != 1:
                continue
            A, B, C = (np.array(vo[i][:2]) for i in tri)
            a, b, c = (vmap[i] for i in tri)
            if (B[0] - A[0]) * (C[1] - A[1]) - (B[1] - A[1]) * (C[0] - A[0]) < 0:
                b, c = c, b                             # ve CCW (phap tuyen +n)
            newF.append((posv(a), posv(c), posv(b)))    # manh phia +n: nap nhin ra -n
            newF.append((negv(a), negv(b), negv(c)))    # manh phia -n: nap nhin ra +n
            newC += [-1, -1]
            newK += [cut_id, cut_id]
            ccount += 1
        if ccount == 0:
            return None
        keep = np.ones(len(F), bool)
        keep[sel_f] = False
        V2 = np.concatenate([V, blk, blk.copy()])
        F2 = np.concatenate([F[keep], np.array(newF, dtype=np.int64)])
        C2 = np.concatenate([self.col[keep], np.array(newC, dtype=np.int64)])
        K2 = np.concatenate([self.cap[keep], np.array(newK, dtype=np.int64)])
        whole = TM(V2, F2, C2, K2)
        lab = whole.components()
        vf = np.full(len(V2), -1, np.int64)
        vf[F2.ravel()] = np.repeat(lab, 3)
        lp = vf[[posv(i) for i in range(k)]]
        ln = vf[[negv(i) for i in range(k)]]
        if (lp == ln).any() or (lp < 0).any() or (ln < 0).any():
            return None                                  # khong tach roi -> bo nhat cat
        return [whole.subset(np.where(lab == c)[0]) for c in range(lab.max() + 1)]

    def plane_cut(self, p, n, cut_id, mode="local", q=None, grow=True, shift_rel=0.013, attempts=4):
        """Cat bang mat phang. local: vung quanh q; neu khong tach roi (vd quai tui noi duoi voi than) thi
        lan luot them cac vung GAN NHAT tren cung mat phang cho toi khi tach duoc. Manh ra bi HO (nap loi)
        thi xe mat phang mot chut va thu lai; khong duoc thi tra None (giu nguyen manh)."""
        q = np.asarray(q if q is not None else p, dtype=np.float64)
        closed0 = self.is_closed()
        # xe mat phang khi ket: RAT NHO truoc (0.04%, 0.15%...) - xe 1.3% ngay tu dau lam cac nua cat lech nhau, mui khong
        # gap nhau o tam (dia chia 6, 2026-10-05)
        steps = [0.0, 0.0004, -0.0004, 0.0015, -0.0015, 0.005, -0.005, 0.013, -0.026, 0.039]
        for attempt in range(max(attempts, len(steps)) if shift_rel == 0.013 else attempts):
            if shift_rel == 0.013:
                if attempt >= len(steps):
                    break
                shift = steps[attempt] * self.size
            else:
                shift = 0.0 if attempt == 0 else shift_rel * self.size * attempt * (-1) ** attempt
            pp = np.asarray(p, dtype=np.float64) + unit(n) * shift
            sec = self.section(pp, n)
            if mode == "all":
                sets = [self.region(sec, q, "all")[0]]
            else:
                sets = self._grow_sets(sec, q) if grow else [self.region(sec, q, "local")[0]]
            bad = False
            for loops in sets:
                if not loops:
                    continue
                res = self.cut(sec, loops, cut_id)
                if res is None:
                    # vong SUY BIEN (gai ti hon canh ong phuoc xe may, dien tich ~0.0007): CDT gop dinh -> ca nhat
                    # cat hong. Bo chung roi thu lai - gai la nhanh cut thi khong noi hai ben (2026-10-02)
                    keep = [l for l in loops if l["area"] >= 2e-5 * self.size ** 2]
                    if keep and len(keep) < len(loops):
                        res = self.cut(sec, keep, cut_id)
                if res is None:
                    continue
                if closed0 and not all(r.is_closed() for r in res):
                    bad = True
                    break
                return res
            if not bad and attempt >= 1:
                break
        return None

    def _grow_sets(self, sec, q):
        """Cac tap vong de thu lan luot: vung quanh q, roi them dan cac vung ngoai gan q nhat."""
        first, _ = self.region(sec, q, "local")
        if not first:
            return []
        L = [l for l in sec["loops"] if l["closed"]]
        q2 = np.array([(q - sec["p"]) @ sec["u"], (q - sec["p"]) @ sec["w"]])
        outs = [l for l in L if l["depth"] % 2 == 0 and l is not first[0]]
        outs.sort(key=lambda l: seg_dist(q2, l["P2"]))
        sets = [first]
        cur = list(first)
        for o in outs[:6]:
            holes = [h for h in L if h["depth"] == o["depth"] + 1 and h["area"] < o["area"]
                     and in_poly(h["P2"][:1], o["P2"])[0]]
            cur = cur + [o] + [h for h in holes if all(h is not c for c in cur)]
            sets.append(list(cur))
        return sets

    def snap(self, p, n, dist, tilts=(0.0, 10.0, 20.0), steps=9, q=None, grow=(1.0,), fallback="min"):
        """Tim CHO THAT gan (p, n): co, chan tai, goc tay, ranh cam. Dich trong [-dist, dist] theo n, nghieng toi
        da max(tilts) do. Uu tien CUC TIEU TRONG cua tiet dien (hai ben deu phinh to hon >= 15%) - tai / tay / duoi
        thon dan ra ngoai nen tiet dien nho nhat la o CHOP, khong phai o chan (gau dau bep 2026-10-02: tai chi cat
        duoc chop; co dat z 6.0 trong khi ranh cam o 5.3). Khong thay cho that: noi khoang tim theo `grow` (x dist);
        van khong co -> fallback "min" = tiet dien nho nhat (cach cu), "keep" = giu mat phang duoc chi.
        Tra ve (p, n, dien tich)."""
        n = unit(n)
        u, w = basis(n)
        q = np.asarray(q if q is not None else p, dtype=np.float64)
        angs = sorted(set([0.0] + [s * a for a in tilts for s in (1, -1)]))
        cands = [n]
        for a in angs:
            if a == 0:
                continue
            r = math.radians(a)
            cands.append(unit(n * math.cos(r) + u * math.sin(r)))
            cands.append(unit(n * math.cos(r) + w * math.sin(r)))
        sec0 = self.section(p, n)
        _, a0 = self.region(sec0, q, "local")
        if dist <= 0:
            return np.asarray(p), n, a0
        best_min = best_any = None
        for g in grow:
            d = dist * g
            k = int(round(steps * g)) | 1
            ts = np.linspace(-d, d, k)
            for nn in cands:
                tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(nn @ n)))))
                A = np.full(k, np.nan)
                for i, t in enumerate(ts):
                    pp = np.asarray(p) + n * t
                    sec = self.section(pp, nn)
                    qq = q + n * t
                    loops, area = self.region(sec, qq, "local")
                    if not loops or area <= 0 or area < 0.35 * a0:
                        continue
                    q2 = np.array([(qq - sec["p"]) @ sec["u"], (qq - sec["p"]) @ sec["w"]])
                    if not in_poly(q2[None], loops[0]["P2"])[0]:
                        continue                # diem dich nam ngoai vung -> vong khac (quai, goc tui), bo
                    A[i] = area
                    if g == grow[0]:
                        score = area * (1 + 0.25 * abs(t) / max(dist, 1e-9) + 0.004 * tilt)
                        if best_any is None or score < best_any[0]:
                            best_any = (score, pp, nn, area)
                for i in range(1, k - 1):        # cuc tieu trong: hai ben deu cao hon
                    if np.isnan(A[i]) or np.isnan(A[i - 1]) or np.isnan(A[i + 1]):
                        continue
                    if not (A[i] <= A[i - 1] and A[i] <= A[i + 1]):
                        continue
                    ml, mr = np.nanmax(A[:i]), np.nanmax(A[i + 1:])
                    side = min(ml, mr)
                    if side < 1.12 * A[i]:
                        continue
                    score = (A[i] / side) * (1 + 0.15 * abs(ts[i]) / max(dist, 1e-9) + 0.004 * tilt)
                    if best_min is None or score < best_min[0]:
                        best_min = (score, np.asarray(p) + n * ts[i], nn, A[i])
            if best_min is not None:
                return best_min[1], best_min[2], best_min[3]
        if fallback == "min" and best_any is not None:
            return best_any[1], best_any[2], best_any[3]
        return np.asarray(p), n, a0

    # ------------------------------------------------------------ gop
    def merge_with(self, other, cut_ids=None, tol_rel=1e-5):
        """Gop hai manh; bo cac mat nap chung (ma nhat cat co o ca hai) roi han dinh trung."""
        shared = set(np.unique(self.cap[self.cap >= 0]).tolist()) & set(np.unique(other.cap[other.cap >= 0]).tolist())
        if cut_ids is not None:
            shared &= set(cut_ids)
        V = np.concatenate([self.V, other.V])
        F = np.concatenate([self.F, other.F + len(self.V)])
        C = np.concatenate([self.col, other.col])
        K = np.concatenate([self.cap, other.cap])
        drop = np.isin(K, list(shared)) if shared else np.zeros(len(F), bool)
        touched = np.unique(F[drop].ravel())
        F, C, K = F[~drop], C[~drop], K[~drop]
        K = np.where(np.isin(K, list(shared)), -1, K) if shared else K
        # han dinh trung vi tri trong cac dinh thuoc nap da bo
        tol = tol_rel * max(self.size, other.size, 1e-9)
        remap = np.arange(len(V))
        if len(touched):
            keyd = {}
            for v in touched:
                key = tuple(np.round(V[v] / tol).astype(np.int64))
                if key in keyd:
                    remap[v] = keyd[key]
                else:
                    keyd[key] = v
        F = remap[F]
        good = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
        t = TM(V, F[good], C[good], K[good])
        used, inv = np.unique(t.F.ravel(), return_inverse=True)
        t = TM(t.V[used], inv.reshape(-1, 3), t.col, t.cap)
        return t
