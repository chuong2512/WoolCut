"""Mau: doc mau texture tung mat -> bang 28 mau (mau trong game Unity), don vung mau vun.

Da kiem tren 8 model Tripo (2026-09-30 .. 10-01):
- gom cum mau rieng cua model TRUOC roi moi chon mau bang (gan thang tung mat thi bong do cat mot vung
  thanh 2-3 mau loang lo);
- chon mau bang bang CIEDE2000 (kL=2), so voi mau trong game VA mau y do thiet ke trong FBX (slot co ten);
- don vung: vet bong / chuyen mau cung mot mau son thi gop, vun nho nhap vao vung ke - tru chi tiet that
  (mat, mui, nut). Do tuong phan / "cung mau son" tren MAU TEXTURE THAT, khong tren mau bang Unity.
Chay trong Blender (can bpy cho anh texture)."""
import math, collections
import numpy as np
from . import std, load as mesh


# So mau bang: trong game mau con nhan voi anh sang toon nen do sang lech co he thong
# voi texture AI -> giam trong so L mot nua (gom cum van dung L_WEIGHT thap hon)

PREFER_DE = 8.0          # mau goi y tu prompt duoc chon neu kem mau tot nhat <= 8 don vi dE2000


# ------------------------------------------------------------------ mau
def _to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def _to_lin(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))


def _lab(lin):
    lin = np.atleast_2d(lin)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


def palette_table_fbx(names):
    """Mau Y DO THIET KE cua tung slot (mau ghi trong FBX goc: Orange = cam, Cream = kem vang)."""
    return _lab(np.array([std.PALETTE_BY_MAT.get(n, (0.5, 0.5, 0.5)) for n in names]))


def palette_table(allowed=None):
    """(ten material, Lab) cac slot duoc TU CHON: chi slot CO TEN, co trong Unity; so bang mau DANH NGHIA
    (std.NOMINAL - mau ma ten slot goi len, cung la tu mau trong prompt). Xem ghi chu o std.NOMINAL."""
    names, cols = [], []
    for n, nm, rgb, _ in std.PALETTE:
        mn = std.mat_name(n, nm)
        if not nm or n not in std.NOMINAL:
            continue
        if std.UNITY and not std.in_unity(mn):
            continue
        if allowed and mn not in allowed:
            continue
        names.append(mn)
        cols.append(std._lin(std.NOMINAL[n]))
    return names, _lab(np.array(cols))


def shown_rgb(mn):
    """Mau hien thi (linear) cua slot: mau danh nghia."""
    return std.nominal_lin(mn)


def de2000(lab1, lab2, kL=1.0):
    """CIEDE2000 [N,M]. Khac Lab thuong: chenh do bao hoa o vung mau dam bi nen lai, sac do
    (hue) duoc uu tien - xanh reu nhat van gan xanh la hon xam (Lab thuong thi nguoc lai)."""
    L1, a1, b1 = [lab1[:, None, i] for i in range(3)]
    L2, a2, b2 = [lab2[None, :, i] for i in range(3)]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7)))
    a1p, a2p = a1 * (1 + G), a2 * (1 + G)
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh) / 2)
    Lm, Cmp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hm = np.where(C1p * C2p == 0, hs,
                  np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hm - 30)) + 0.24 * np.cos(np.radians(2 * hm))
         + 0.32 * np.cos(np.radians(3 * hm + 6)) - 0.20 * np.cos(np.radians(4 * hm - 63)))
    SL = 1 + 0.015 * (Lm - 50) ** 2 / np.sqrt(20 + (Lm - 50) ** 2)
    SC, SH = 1 + 0.045 * Cmp, 1 + 0.015 * Cmp * T
    RT = (-2 * np.sqrt(Cmp ** 7 / (Cmp ** 7 + 25.0 ** 7))
          * np.sin(np.radians(60 * np.exp(-((hm - 275) / 25) ** 2))))
    return np.sqrt((dLp / (kL * SL)) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                   + RT * (dCp / SC) * (dHp / SH))


def nearest_de(lin_rgb, labs, kL=2.0):
    return de2000(_lab(lin_rgb), labs, kL).argmin(axis=1)


# Trong so do sang khi so mau. Texture AI co bong do / AO: cung mot vung kem co cho
# L=82, cho L=70. So bang Lab day du thi phan toi bi keo ve Gray02 (do that tren
# hamster Tripo 2026-09-30: de kem 31% dien tich ra xam). Giam trong so L de sac do
# quyet dinh; den/xam/trang van tach duoc vi chenh L rat lon.
L_WEIGHT = 0.3


def quantize(C, A, k_max=12, merge_de=12.0, lw=L_WEIGHT):
    """Gom mau cac mat thanh cum (k-means co trong so dien tich, khoi tao xa-nhat),
    gop cum gan nhau. Tra ve (nhan cum moi mat, mau linear trung binh moi cum)."""
    X = _lab(C) * np.array([lw, 1.0, 1.0])
    order = np.argsort(-A)
    cand = X[order[:min(len(X), 6000)]]
    seeds = [cand[0]]
    d = ((cand - cand[0]) ** 2).sum(1)
    for _ in range(max(1, 2 * k_max) - 1):
        i = int(d.argmax())
        if d[i] < (0.6 * merge_de) ** 2:
            break
        seeds.append(cand[i])
        d = np.minimum(d, ((cand - cand[i]) ** 2).sum(1))
    cent = np.array(seeds)
    lab = np.zeros(len(X), dtype=int)
    for _ in range(30):
        lab = ((X[:, None, :] - cent[None]) ** 2).sum(2).argmin(1)
        new = cent.copy()
        for k in range(len(cent)):
            s = lab == k
            if s.any():
                new[k] = (X[s] * A[s, None]).sum(0) / A[s].sum()
        if np.allclose(new, cent, atol=1e-3):
            break
        cent = new
    # gop cum gan nhau (cum nho nhap vao cum to gan no)
    area = np.array([A[lab == k].sum() for k in range(len(cent))])
    alive = [k for k in np.argsort(-area) if area[k] > 0]
    parent = {k: k for k in alive}
    kept = []
    for k in alive:
        near = [j for j in kept if np.linalg.norm(cent[k] - cent[j]) < merge_de]
        parent[k] = min(near, key=lambda j: np.linalg.norm(cent[k] - cent[j])) if near else k
        if not near:
            kept.append(k)
    lab = np.array([parent.get(k, k) for k in lab])
    ids = sorted(set(lab.tolist()))
    remap = {k: i for i, k in enumerate(ids)}
    lab = np.array([remap[k] for k in lab])
    rgb = np.array([(C[lab == i] * A[lab == i, None]).sum(0) / A[lab == i].sum() for i in range(len(ids))])
    return lab, rgb


def smooth_labels(lab, nb, area, fixed, iters=3):
    lab = list(lab)
    for _ in range(iters):
        new = lab[:]
        for f in range(len(lab)):
            if fixed[f] or not nb[f]:
                continue
            w = collections.Counter()
            w[lab[f]] += area[f] * 1.5
            for g in nb[f]:
                w[lab[g]] += area[g]
            new[f] = w.most_common(1)[0][0]
        lab = new
    return lab


def components(lab, nb):
    seen = [False] * len(lab)
    comps = []
    for s in range(len(lab)):
        if seen[s]:
            continue
        stack, comp = [s], []
        seen[s] = True
        while stack:
            f = stack.pop()
            comp.append(f)
            for g in nb[f]:
                if not seen[g] and lab[g] == lab[s]:
                    seen[g] = True
                    stack.append(g)
        comps.append(comp)
    return comps


def merge_small(lab, nb, area, min_area, min_faces):
    for _ in range(6):
        changed = False
        for comp in components(lab, nb):
            a = sum(area[f] for f in comp)
            if a >= min_area and len(comp) >= min_faces:
                continue
            cs = set(comp)
            border = collections.Counter(lab[g] for f in comp for g in nb[f] if g not in cs)
            if not border:
                continue
            nl = border.most_common(1)[0][0]
            for f in comp:
                lab[f] = nl
            changed = True
        if not changed:
            break
    return lab


def _roundness(bm, faces, area):
    """Do tron cua mot vung tren mat: can(lambda2/lambda1) cua phan tan tam mat (1 = tron deu, 0.1 =
    soi dai). Mat / mui / nut ~0.6-1; vet bong do va vien rang cua doc ranh gioi ~0.1-0.3."""
    if len(faces) < 3:
        return 0.0
    P = np.array([bm.faces[f].calc_center_median()[:] for f in faces])
    w = area[faces] / max(area[faces].sum(), 1e-12)
    c = (P * w[:, None]).sum(0)
    C = ((P - c).T * w) @ (P - c)
    ev = np.sort(np.linalg.eigvalsh(C))[::-1]
    return float(np.sqrt(max(ev[1], 0) / ev[0])) if ev[0] > 0 else 0.0


def _same_paint(l1, l2):
    """Hai mau Lab co phai CUNG MOT MAU SON bi bong do / chuyen sang khong. Bong chi doi do sang (va chut
    do bao hoa), giu sac: cung sac (lech < 15 do) va do bao hoa gan nhau; hai mau trung tinh (xam/den)
    thi do sang lech it. Kem nhat vs xam: mot co sac mot khong -> KHAC (mom kem cho cuu hoa bi nhap vao
    mat xam khi so bang dE thuong); den vs xam: lech sang lon -> KHAC (mat)."""
    c1, c2 = float(np.hypot(l1[1], l1[2])), float(np.hypot(l2[1], l2[2]))
    if abs(l1[0] - l2[0]) > 25:
        return False
    if c1 < 10 and c2 < 10:
        return abs(l1[0] - l2[0]) < 18
    if min(c1, c2) < 10 or abs(c1 - c2) > 0.35 * max(c1, c2):
        return False
    dh = abs(math.degrees(math.atan2(l1[2], l1[1]) - math.atan2(l2[2], l2[1]))) % 360
    return min(dh, 360 - dh) < 15


def clean_regions(bm, lab, nb, area, opts, col=None):
    """Don vung mau vun TRUOC khi dung manh (gau meo tho Tripo 2026-10-01: 78 vung, 3/4 la vun bong do ->
    yem xanh thung lo, mat lam nham). Lap lai toi khi on dinh, vung nho xet truoc:
      1. vung CUNG MAU SON voi vung ke tren TEXTURE (mau trung binh that, xem _same_paint: chi khac do
         sang - bong / chuyen mau) va chung bien dai -> nhap vao vung lon hon (xe vang bi chia
         Yellow / yellow02). So bang mau bang thi sai: yem xanh nhat va lop xam Unity gan nhau.
      2. vung NHO (< noise x dien tich) nhap vao vung ke chung bien dai nhat - tru khi la CHI TIET THAT:
         tuong phan manh tren texture (dE >= 30), khong qua vun (>= 0.02%) va tron (mat, mui, nut)
    Mau co dinh trong file (FBX dung chuan) khong dong vao."""
    F = len(lab)
    total = float(area.sum()) or 1.0
    noise = opts.get("noise", 0.004)
    bm.faces.ensure_lookup_table()
    elen = {}
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) == 2:
            a, b = lf[0].index, lf[1].index
            elen[(a, b)] = elen[(b, a)] = e.calc_length()
    labc = {}

    def color(n):
        if n not in labc:
            labc[n] = _lab(np.array([std.game_rgb(n)]))[0] if n in std.PALETTE_BY_MAT else None
        return labc[n]

    def de(a, b):
        ca, cb = color(a), color(b)
        if ca is None or cb is None:
            return 99.0
        return float(de2000(ca[None], cb[None], 2.0)[0, 0])

    def tex(comp):                                         # mau trung binh that cua vung tren texture
        w = area[comp]
        return _lab((col[comp] * w[:, None]).sum(0, keepdims=True) / max(w.sum(), 1e-12))[0]
    lab = list(lab)
    merged = 0
    for _ in range(12):
        changed = False
        comps = components(lab, nb)
        comp_of = np.empty(F, dtype=np.int64)
        for i, c in enumerate(comps):
            comp_of[c] = i
        carea = np.array([area[c].sum() for c in comps])
        for ci in np.argsort(carea):
            comp = comps[ci]
            me = lab[comp[0]]
            if any(lab[f] != me for f in comp[:1]):
                continue
            border = collections.Counter()
            for f in comp:
                for g in nb[f]:
                    if lab[g] != me:
                        border[comp_of[g]] += elen.get((f, g), 0.0)
            if not border:
                continue                                   # khoi rieng mot mau - giu nguyen
            per = sum(border.values()) or 1.0
            hi, blen = border.most_common(1)[0]
            host = lab[comps[hi][0]]
            a = carea[ci]
            # tuong phan do tren MAU TEXTURE that: trong game White la xam dam, gan Black -> mat den tren mat
            # xam bi coi la vet bong va nhap mat (gau meo 2026-10-01)
            d = float(de2000(tex(comp)[None], tex(comps[hi])[None], 1.0)[0, 0]) if col is not None else de(me, host)
            take = False
            if col is not None and blen >= 0.25 * per and a <= carea[hi] and _same_paint(tex(comp), tex(comps[hi])):
                take = True                                # bong / chuyen mau cung mot vat
            elif a < noise * total:
                feature = d >= 30 and a >= 0.0002 * total and _roundness(bm, comp, area) >= 0.35
                take = not feature
            if take:
                for f in comp:
                    lab[f] = host
                merged += 1
                changed = True
        if not changed:
            break
    n_after = len(components(lab, nb))
    print("[mau] don vung mau: nhap %d vung vun/giong mau -> con %d vung" % (merged, n_after))
    return lab


# ------------------------------------------------------------------ chinh
def palette_labels(srcs, opts):
    """Mau bang cho TUNG MAT cua cac object nguon: gom cum mau rieng cua model -> chon mau bang ->
    gop mau gan nhau. Tra ve (per [(obj, mau linear, nhan co dinh, dien tich)], nhan moi mat noi lien)."""
    allowed = None
    if opts.get("palette"):
        allowed = [std.resolve_color(c) for c in opts["palette"]]
    names, labs = palette_table(allowed)

    per = []                                   # (obj, mau, nhan co dinh, dien tich)
    for o in srcs:
        if isinstance(o, tuple):               # (None, mau, co dinh, dien tich) da tinh san
            per.append(o)
            continue
        col, fixed, area = mesh.face_colors(o)
        per.append((o, col, fixed, area))

    # Mau: GOM CUM TRUOC (mau rieng cua model), roi moi gan mau bang cho tung cum.
    # Gan thang tung mat vao bang lam bong do/AO cat mot vung thanh 2-3 mau loang lo.
    allarea = np.concatenate([a for _, _, _, a in per])
    allcol = np.concatenate([c for _, c, _, _ in per])
    is_fixed = []
    for o, col, fixed, area in per:
        is_fixed += [bool(x) for x in fixed]
    fixed_all = [x for _, _, fx, _ in per for x in fx]
    lab_all = list(fixed_all)
    free = np.array([not f for f in is_fixed])
    user_map = opts.get("map") or {}
    chosen = set()                                        # mau nguoi dung tu chon: khong gop
    if free.any():
        cl, crgb = quantize(allcol[free], allarea[free], k_max=opts.get("colors", 10) + 2,
                            merge_de=opts.get("merge_de", 12.0))
        # Gom cum dung L thap (bo bong do); CHON slot thi so tam cum (mau trung binh, da het bong) voi mau
        # DANH NGHIA cua slot bang CIEDE2000, kL=1.5 (texture AI toi/sang lech chut so voi mau goi trong prompt)
        dmat = de2000(_lab(crgb), labs, 1.5)
        best = dmat.argmin(axis=1)
        # Goi y mau tu prompt chi la UU TIEN MEM: prompt noi "green" nhung Tripo nan ga VANG
        # (2026-09-30: ep cung danh sach -> ga vang thanh xanh la). Chon mau goi y chi khi no
        # gan ngang mau tot nhat (+PREFER_DE); con khong thi theo mau that cua model.
        pref = [i for i, n in enumerate(names) if n in set(opts.get("prefer") or [])]
        if pref:
            bp = np.array(pref)[dmat[:, pref].argmin(axis=1)]
            use = dmat[np.arange(len(best)), bp] <= dmat[np.arange(len(best)), best] + PREFER_DE
            best = np.where(use, bp, best)
        auto = [names[i] for i in best]
        fa = allarea[free]
        order = list(np.argsort([-fa[cl == i].sum() for i in range(len(crgb))]))   # #1 = cum lon nhat
        cpal = list(auto)
        for k, v in user_map.items():
            k = k.strip()
            if k.startswith("#"):                         # "#9=Pink": doi RIENG cum thu 9
                r = int(k[1:]) - 1
                if 0 <= r < len(order):
                    cpal[order[r]] = std.resolve_color(v)
            else:                                         # "White=Cream": doi moi cum dang ra White
                src = std.resolve_color(k)
                cpal = [std.resolve_color(v) if a == src else c for a, c in zip(auto, cpal)]
        chosen = {c for a, c in zip(auto, cpal) if a != c}
        fidx = np.where(free)[0]
        for j, c in zip(fidx, cl):
            lab_all[j] = cpal[c]
        # Dong in nay la GIAO KEO voi addon (panel "Duyet mau" doc lai): giu dung dinh dang
        print("[mau] cum mau cua model -> mau bang:")
        for r, i in enumerate(order):
            print("  #%d  %5.1f%%  sRGB %.2f %.2f %.2f  -> %s%s" % (
                r + 1, 100 * fa[cl == i].sum() / fa.sum(), *_to_srgb(crgb[i]), auto[i],
                ("  => " + cpal[i]) if cpal[i] != auto[i] else ""))
    # Gon mau chi ap cho mau DO DOAN tu texture/mau dinh; mau da dat ten chuan
    # trong file (va Deco) giu nguyen. KHONG bo mau theo dien tich nho - dong tu den,
    # mieng do la mau nho nhat ma quan trong nhat. Thay vao do gop cac mau GAN NHAU
    # (bong do tren texture tach mot mang xanh thanh Green + DarkGreen + Forest).
    tot = collections.Counter()
    for l, a, fx in zip(lab_all, allarea, is_fixed):
        if not fx:
            tot[l] += a
    lab_of = dict(zip(names, labs))
    for n in tot:
        if n not in lab_of:                  # mau do --map ep ra nam ngoai danh sach so khop
            lab_of[n] = _lab(np.array([std.game_rgb(n)]))[0]
    merge_de = opts.get("merge_pal", 10.0)
    target = {}
    kept = []
    for l, _ in tot.most_common():
        near = [k for k in kept if np.linalg.norm(lab_of[l] - lab_of[k]) < merge_de]
        if near and l not in chosen:
            target[l] = min(near, key=lambda k: np.linalg.norm(lab_of[l] - lab_of[k]))
        else:
            kept.append(l)
            target[l] = l
    kept = [k for k in kept if k in lab_of]
    cap = opts.get("colors", 10)
    while len([k for k in kept if k not in chosen]) > cap:   # van qua nhieu: nhap mau nho nhat
        area_k = collections.Counter()
        for l, t in target.items():
            area_k[t] += tot[l]
        small = min([k for k in kept if k not in chosen], key=lambda k: area_k[k])
        kept.remove(small)
        dest = min(kept, key=lambda k: np.linalg.norm(lab_of[small] - lab_of[k]))
        for l, t in list(target.items()):
            if t == small:
                target[l] = dest
    for i, l in enumerate(lab_all):
        if not is_fixed[i] and l in target:
            lab_all[i] = target[l]
    merged = {l: t for l, t in target.items() if l != t}
    print("[mau] mau giu: %s" % ", ".join(k.replace("Color_", "").replace("_mat", "") for k in kept))
    if merged:
        print("[mau] mau gop: %s" % ", ".join("%s->%s" % (l.replace("Color_", "").replace("_mat", ""),
                                                             t.replace("Color_", "").replace("_mat", ""))
                                                 for l, t in merged.items()))

    return per, lab_all
