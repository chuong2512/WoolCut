"""Do "de tach" cua model sau prep, so voi 108 FBX goc (phan tich 2026-10-07).

Bo phan mau = vung mat CUNG MAU lien nhau tren mot khoi (tool tach duoc theo mau hoac theo khoi). Bo goc: nhan vat
~26 bo phan, 9 mau, vung cung mau lon nhat ~24% dien tich - vi quan ao / gang / giay / phu kien chia than ra. Model
Tripo don gian (gau dau bep, cao, tho 2026-10) ra 37-65%: mot mang da lien tu dau xuong chan -> chi duoc 8-10 manh M.
Khong can bpy (chay duoc o python he thong de soat lai prep.npz)."""
import numpy as np

# trung vi (tu phan vi duoi / tren) cua bo goc: scratchpad fbx_parts_stats.py + agg_stats.py
TARGET = {
    "char": dict(parts=26, parts_lo=21, parts_hi=29, colors=9, colors_lo=8, largest=0.24, largest_hi=0.32, M=24),
    "object": dict(parts=26, parts_lo=19, parts_hi=40, colors=8, colors_lo=6, largest=0.32, largest_hi=0.39, M=22),
    "food": dict(parts=21, parts_lo=11, parts_hi=31, colors=8, colors_lo=3, largest=0.26, largest_hi=0.38, M=22),
    "scene": dict(parts=30, parts_lo=28, parts_hi=49, colors=9, colors_lo=8, largest=0.19, largest_hi=0.29, M=28),
    "plant": dict(parts=10, parts_lo=10, parts_hi=27, colors=7, colors_lo=7, largest=0.32, largest_hi=0.39, M=18),
}
MIN_AREA = 0.005          # vung < 0.5% dien tich = mat / ma / cuc nho -> thanh D, khong tinh bo phan


def _regions(t):
    """Nhan vung cung mau lien nhau (qua canh chung) cua mot khoi -> (nhan tung mat, so vung)."""
    ef, _ = t.edge_faces()
    m = len(t.F)
    par = np.arange(m)

    def find(x):
        r = x
        while par[r] != r:
            r = par[r]
        while par[x] != r:
            par[x], x = r, par[x]
        return r
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    a, b = ef[ok, 0], ef[ok, 1]
    same = t.col[a] == t.col[b]
    for x, y in zip(a[same].tolist(), b[same].tolist()):
        rx, ry = find(x), find(y)
        if rx != ry:
            par[rx] = ry
    roots = np.array([find(i) for i in range(m)])
    _, lab = np.unique(roots, return_inverse=True)
    return lab, int(lab.max()) + 1 if m else 0


def measure(tms):
    """{"parts": so bo phan mau, "colors": so mau dang ke, "largest": ti le dien tich vung cung mau lon nhat}."""
    areas, cols = [], []
    for t in tms:
        if not len(t.F):
            continue
        lab, n = _regions(t)
        ar = np.bincount(lab, weights=t.face_areas(), minlength=n)
        col = np.zeros(n, np.int64)
        col[lab] = t.col
        areas += ar.tolist()
        cols += col.tolist()
    if not areas:
        return dict(parts=0, colors=0, largest=1.0)
    areas = np.array(areas)
    tot = float(areas.sum()) or 1.0
    big = areas / tot >= MIN_AREA
    cols = np.array(cols)
    cw = {}
    for c, a in zip(cols.tolist(), areas.tolist()):
        cw[c] = cw.get(c, 0.0) + a
    return dict(parts=int(big.sum()), colors=int(sum(1 for c, a in cw.items() if c >= 0 and a / tot >= MIN_AREA)),
                largest=round(float(areas.max()) / tot, 3))


def verdict(m, kind="char"):
    """So voi bo goc cung dang -> (muc "ok"/"kho"/"rat kho", [cau giai thich tieng Viet])."""
    g = TARGET.get(kind, TARGET["char"])
    why, bad = [], 0
    if m["largest"] > g["largest_hi"]:
        bad += 2 if m["largest"] > 0.45 else 1
        why.append("Mảng cùng màu lớn nhất %.0f%% (mẫu %.0f%%): thân liền một màu, cần quần áo / phụ kiện chia ra"
                   % (100 * m["largest"], 100 * g["largest"]))
    if m["parts"] < g["parts_lo"]:
        bad += 2 if m["parts"] < 0.6 * g["parts_lo"] else 1
        why.append("Chỉ %d bộ phận màu (mẫu %d): thiếu viền, nẹp, túi, đồ cầm tay" % (m["parts"], g["parts"]))
    if m["colors"] <= 1:                     # Tripo xuat "parts" khong texture: chi tach theo khoi, Claude to sau
        why.append("Model không có màu: chỉ tách được theo khối, Claude tô màu sau")
    elif m["colors"] < g["colors_lo"]:       # thieu mau khong lam kho tach (buoc to mau bu duoc) -> chi ghi chu
        why.append("Chỉ %d màu (mẫu %d): bước tô màu sẽ phải thêm" % (m["colors"], g["colors"]))
    return ("ok" if bad == 0 else "kho" if bad <= 2 else "rat kho"), why


def line(m, kind="char"):
    """Mot dong cho log: [do tach] ..."""
    lvl, why = verdict(m, kind)
    g = TARGET.get(kind, TARGET["char"])
    head = "%d bo phan mau (mau %d), %d mau (mau %d), mang lon nhat %.0f%% (mau %.0f%%)" % (
        m["parts"], g["parts"], m["colors"], g["colors"], 100 * m["largest"], 100 * g["largest"])
    return "%s -> %s" % (head, {"ok": "DE TACH", "kho": "KHO TACH", "rat kho": "RAT KHO TACH"}[lvl])
