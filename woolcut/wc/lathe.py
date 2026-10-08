"""DUNG LAI DO TRON XOAY (nguoi dung 2026-10-08, cao dau bep: "cai bat thi nen thiet ke lai mesh... sau khi labeling va
tach part thi kiem tra lai hinh dang part da chuan logic chua"). Bat Tripo tach ra bi "sua part xau" cat mat vanh (thanh
bat mong -> excess.png to do 41%, Claude duyet "trim"), mesh lai voxel ra lom chom. Do tron xoay (bat, coc, dia, chau,
xo, binh, banh xe, mu) thi dung lai bang MAT CAT xoay quanh truc (nhu tien gom): sach, doi xung, it mat.

fit(t): voxel hoa -> thu cac truc (Z the gioi, 3 truc PCA) qua tam khoi -> moi o (r, h) cua mat cat: ti le voxel dac
qua moi goc -> vung >= 50% = mat cat -> IoU giua khoi xoay lai va khoi that. IoU du cao -> duong vien mat cat (marching
squares), lam tron (Chaikin), xoay 48 buoc -> TM kin."""
import math
import numpy as np
from .tm import TM

LATHE_IOU = 0.82          # khoi that trung khoi xoay >= 82% -> do tron xoay
SEGMENTS = 28
VOX = 96
PROFILE = 32           # so diem mat cat sau khi lay mau lai (32 x 28 ~ 1700 tam giac; bat goc 898)


def _region(occ, lo, h, c, a):
    """Mat cat (r, h) cua khoi dac occ quanh truc (c, a): o dac neu >= 50% voxel o cung (r, h) dac. -> (grid, r0, h0)."""
    idx = np.argwhere(np.ones_like(occ, bool))
    P = lo + (idx + 0.5) * h
    d = P - c
    hh = d @ a
    rr = np.linalg.norm(d - hh[:, None] * a[None, :], axis=1)
    ir = np.floor(rr / h).astype(int)
    h0 = hh.min()
    ih = np.floor((hh - h0) / h).astype(int)
    NR, NH = ir.max() + 2, ih.max() + 2
    tot = np.zeros((NR, NH))
    full = np.zeros((NR, NH))
    np.add.at(tot, (ir, ih), 1)
    np.add.at(full, (ir, ih), occ.ravel().astype(float))
    reg = (tot > 0) & (full >= 0.5 * np.maximum(tot, 1))
    return reg, ir, ih, h0


def _iou(occ, reg, ir, ih):
    pred = reg[ir, ih].reshape(occ.shape)
    inter = (pred & occ).sum()
    uni = (pred | occ).sum()
    return float(inter) / max(float(uni), 1.0)


def _contour(reg):
    """Duong vien NGOAI cua vung (luoi o vuong) -> da giac kin [(r, h)] theo o (goc o = dinh luoi). Lan theo canh bien."""
    R, H = reg.shape
    g = np.zeros((R + 2, H + 2), bool)
    g[1:-1, 1:-1] = reg
    # canh bien co huong (vung ben trai): tu dinh -> dinh
    nxt = {}
    for i in range(R + 1):
        for j in range(H + 1):
            if g[i + 1, j + 1] and not g[i + 1, j]:        # mat duoi cua o (i, j) la bien
                nxt[(i, j)] = (i + 1, j)
            if g[i + 1, j + 1] and not g[i + 2, j + 1]:    # mat phai
                nxt[(i + 1, j)] = (i + 1, j + 1)
            if g[i + 1, j + 1] and not g[i + 1, j + 2]:    # mat tren
                nxt[(i + 1, j + 1)] = (i, j + 1)
            if g[i + 1, j + 1] and not g[i, j + 1]:        # mat trai
                nxt[(i, j + 1)] = (i, j)
    if not nxt:
        return None
    loops, seen = [], set()
    for s in list(nxt):
        if s in seen:
            continue
        loop, p = [], s
        while p not in seen and p in nxt:
            seen.add(p)
            loop.append(p)
            p = nxt[p]
        if len(loop) > 8:
            loops.append(np.array(loop, float))
    if not loops:
        return None
    area = lambda L: 0.5 * abs(np.dot(L[:, 0], np.roll(L[:, 1], -1)) - np.dot(L[:, 1], np.roll(L[:, 0], -1)))
    return max(loops, key=area)


def _smooth(L, iters=3):
    """Chaikin cho da giac kin, giu cac dinh nam tren truc (r = 0) o r = 0."""
    for _ in range(iters):
        A, B = L, np.roll(L, -1, axis=0)
        Q, Rr = 0.75 * A + 0.25 * B, 0.25 * A + 0.75 * B
        L = np.empty((2 * len(A), 2))
        L[0::2], L[1::2] = Q, Rr
        L[:, 0] = np.where(L[:, 0] < 0.35, 0.0, L[:, 0])
    return L


def _relax(L, iters=12):
    """Lam min duong vien (bac thang voxel thanh gon xoay quanh coc): trung binh lang gieng, dinh tren truc dung yen."""
    on_axis = L[:, 0] <= 1e-9
    for _ in range(iters):
        M = 0.5 * L + 0.25 * (np.roll(L, 1, axis=0) + np.roll(L, -1, axis=0))
        L = np.where(on_axis[:, None], np.stack([np.zeros(len(L)), M[:, 1]], 1), M)
        L[:, 0] = np.maximum(L[:, 0], 0.0)
    return L


def _resample(L, n=72):
    """Lay mau lai DEU theo chieu dai duong vien kin (giam mat, giu hinh); doan nam tren truc giu o r = 0."""
    P = np.vstack([L, L[:1]])
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    tot = s[-1]
    if tot <= 1e-9:
        return L
    q = np.linspace(0, tot, n, endpoint=False)
    out = np.stack([np.interp(q, s, P[:, 0]), np.interp(q, s, P[:, 1])], 1)
    out[:, 0] = np.where(out[:, 0] < 0.35, 0.0, out[:, 0])
    return out


def _revolve(L, c, a, h0, h, seg=SEGMENTS):
    """Da giac mat cat (o luoi, cot 0 = r, cot 1 = h) -> TM xoay quanh truc (c, a)."""
    e1 = np.cross(a, [0.0, 0.0, 1.0] if abs(a[2]) < 0.9 else [1.0, 0.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    ang = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    V, ring = [], []
    for r_, h_ in L:
        r = r_ * h
        z = h0 + h_ * h
        if r < 1e-9:
            ring.append([len(V)] * seg)
            V.append(c + a * z)
        else:
            base = len(V)
            ring.append(list(range(base, base + seg)))
            for t in ang:
                V.append(c + a * z + r * (math.cos(t) * e1 + math.sin(t) * e2))
    F = []
    n = len(L)
    for k in range(n):
        A, B = ring[k], ring[(k + 1) % n]
        if A[0] == A[1] and B[0] == B[1]:
            continue                                     # doan nam tren truc
        for j in range(seg):
            j2 = (j + 1) % seg
            q = [A[j], A[j2], B[j2], B[j]]
            if A[0] == A[1]:
                F.append([A[0], B[j2], B[j]])
            elif B[0] == B[1]:
                F.append([A[j], A[j2], B[0]])
            else:
                F += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
    t = TM(np.array(V), np.array(F))
    if t.volume() < 0:
        t = TM(t.V, t.F[:, ::-1])
    return t


def measure(t, vox=VOX):
    """-> (iou tot nhat, tam, truc, (reg, ir, ih, h0, occ, lo, h)) cho khoi kin t."""
    from . import trim
    occ, lo, h = trim.voxelize(t, vox)
    if occ.sum() < 50:
        return 0.0, None, None, None
    pts = lo + (np.argwhere(occ) + 0.5) * h
    c = pts.mean(0)
    w, U = np.linalg.eigh(np.cov((pts - c).T))
    cands = [np.array([0.0, 0.0, 1.0])] + [U[:, k] for k in range(3)]
    best = (0.0, None, None, None)
    for a in cands:
        a = a / np.linalg.norm(a)
        reg, ir, ih, h0 = _region(occ, lo, h, c, a)
        s = _iou(occ, reg, ir, ih)
        if s > best[0]:
            best = (s, c, a, (reg, ir, ih, h0, occ, lo, h))
    return best


def fit(t, min_iou=LATHE_IOU, seg=SEGMENTS):
    """Do tron xoay -> TM dung lai bang mat cat xoay (kin, sach). -> (TM hoac None, mo ta)."""
    if len(t.F) < 40 or not t.is_closed():
        return None, "ho / it mat"
    s, c, a, extra = measure(t)
    if c is None:
        return None, "rong"
    why = "tron xoay %.0f%%" % (100 * s)
    if s < min_iou:
        return None, why
    reg, ir, ih, h0, occ, lo, h = extra
    L = _contour(reg)
    if L is None:
        return None, why + ", khong lay duoc mat cat"
    L = _resample(_relax(_resample(_smooth(L, 2), 160)), PROFILE)
    t2 = _revolve(L, c, a, h0, h, seg)
    if not t2.is_closed():
        from . import prep
        t3 = prep.local_close(t2)
        if t3 is None:
            return None, why + ", xoay ra ho"
        t2 = t3
    if len(getattr(t, "col", [])) == len(t.F):
        from . import prep
        prep._copy_col(t, t2)
    return t2, why + ", %d -> %d mat" % (len(t.F), len(t2.F))


ROUND_WORDS = ("bát", "tô", "chén", "cốc", "ly", "tách", "đĩa", "chậu", "xô", "nồi", "bình", "lọ", "hũ", "bánh xe",
               "lốp", "vành", "khay", "nắp", "trống", "lon", "mâm", "thùng tròn", "đế tròn", "bowl", "cup", "plate",
               "pot", "wheel", "tire", "drum")
LABEL_IOU = 0.75          # ten la do tron xoay + khoi that trung khoi xoay >= 75% -> dung lai


def is_round_label(label):
    lab = (label or "").lower()
    return any(w in lab.split() or (" " in w and w in lab) for w in ROUND_WORDS)
