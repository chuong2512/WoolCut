"""Chuan cau tao do tu 108 file FBX goc (quet 2026-09-30).

Moi con so o day la SO DO, khong phai doan - tru nhung cho ghi ro "doan".
Tool dung chung de dung model moi VA de cham file bat ky (ke ca file goc).
"""
import re

# ---------------------------------------------------------------- bang mau
# (so, ten, mau goc linear trong FBX, so file dung). Ten material phai giu
# NGUYEN VAN: Unity cua bo asset tim material theo ten (materialSearch=1), nen
# dat dung ten la model moi tu an vao material san co trong project.
PALETTE = [
    (1,  "Beige",         (0.9453, 0.4993, 0.3147), 23),
    (2,  "Black",         (0.0291, 0.0296, 0.0323), 31),
    (3,  "Blue",          (0.1333, 0.1805, 1.0000), 35),
    (4,  "Brown",         (0.2628, 0.1677, 0.1082), 58),
    (5,  "Cyan",          (0.3788, 1.0000, 1.0000), 14),
    (6,  "DarkGreen",     (0.0586, 0.1178, 0.0439), 20),
    (7,  "Gray",          (0.1059, 0.0966, 0.1302), 19),
    (8,  "Green",         (0.1879, 0.3879, 0.0883), 59),
    (9,  "Orange",        (0.5400, 0.1757, 0.0529), 43),
    (10, "Pink",          (1.0000, 0.2506, 0.3374), 60),
    (11, "Purple",        (0.2981, 0.1536, 1.0000), 37),
    (12, "Red",           (0.4110, 0.0976, 0.0966), 69),
    (13, "Violet",        (0.2086, 0.0443, 1.0000), 11),
    (14, "DeepOcean",     (0.1770, 0.3344, 0.2349), 17),
    (15, "White",         (0.5043, 0.5043, 0.5043), 70),
    (16, "Yellow",        (0.6900, 0.4909, 0.1214), 48),
    (17, "Magenta",       (0.2253, 0.0699, 0.2270), 7),
    (18, "Charcoal",      (0.1031, 0.1189, 0.1430), 14),
    (19, "yellow02",      (1.0000, 1.0000, 0.1122), 80),
    (20, None,            (0.5687, 0.6022, 0.4124), 2),
    (21, "Forest",        (0.1429, 0.2370, 0.1346), 12),
    (22, "Sky",           (0.2511, 0.5429, 1.0000), 40),
    (23, None,            (0.0471, 0.0692, 0.0728), 2),
    (24, "Crimson",       (0.2370, 0.0659, 0.0372), 18),
    # FBX goc ghi "Color_25_Gray02_mat" nhung project Unity chi co "Color_25_Gray_mat"
    # (kiem 2026-09-30) -> ten cu KHONG gan duoc material. Tool xuat ten cua Unity.
    (25, "Gray",          (0.5000, 0.5000, 0.5000), 15),
    (26, "Cream",         (1.0000, 1.0000, 0.5587), 55),
    (27, "TurquoiseMint", (0.3718, 1.0000, 0.7069), 11),
    # FBX chi ghi xam 0.5 mac dinh cua Maya -> mau that nam trong Unity. Mau
    # preview duoi day la DOAN theo ten.
    (28, "LightLavender", (0.5500, 0.4500, 0.9000), 6),
]


def mat_name(num, name):
    return "Color_%d_%s_mat" % (num, name) if name else "Color_%d_mat" % num


PALETTE_BY_MAT = {mat_name(n, nm): rgb for n, nm, rgb, _ in PALETTE}

# Bien the ten gap trong bo goc: "Material_Source1:Color_15_White_mat",
# "pasted__Color_19_yellow02_mat", "Color_10_Pink_mat1", "Deco_mat.001".
_VARIANT = re.compile(r"^(?:Material_Source\d*:|pasted__)?(.*?_mat)(?:\d+|\.\d{3})?$")


_DECO_VARIANT = re.compile(r"^(?:Material_Source\d*:|pasted__)?(Deco_mat\d*)(?:\.\d{3})?$")


ALIAS = {"Color_25_Gray02_mat": "Color_25_Gray_mat"}


def canonical(name):
    """Ten material -> ten chuan trong bang mau, hoac Deco_mat/Deco_mat1/2/3 (co the la
    texture khac nhau trong Unity nen KHONG gop), None neu la."""
    d = _DECO_VARIANT.match(name or "")
    if d:
        return d.group(1)
    m = _VARIANT.match(name or "")
    base = m.group(1) if m else name
    base = ALIAS.get(base, base)
    if base in PALETTE_BY_MAT:
        return base
    return None


# ---------------------------------------------------------------- mau THAT trong Unity
# `run.py unity` doc tu file .mat: shader Toony Colors Pro 2, Albedo = texture len dan
# (gan trang), mau thay duoc = Highlight Color (_HColor) / Shadow Color (_SColor).
# Mau ghi trong FBX KHONG phai mau trong game (vd Cream FBX vang nhat, Unity la be hong).
import json as _json, os as _os
_DATA = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data")
UNITY = {}
try:
    with open(_os.path.join(_DATA, "unity_palette.json"), encoding="utf-8") as _fh:
        UNITY = _json.load(_fh)
except (OSError, ValueError):
    pass
KNIT_PNG = _os.path.join(_DATA, "knit_basecolor.png")
DECO_PNG = _os.path.join(_DATA, "Deco_Texture.png")


def _lin(c):
    return tuple((x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c)


def game_rgb(mat):
    """Mau nguoi choi thay (linear): Highlight Color cua Unity neu da dong bo, khong thi mau FBX."""
    u = UNITY.get(mat)
    if u and u.get("h"):
        return _lin(u["h"])
    return PALETTE_BY_MAT.get(mat, (0.5, 0.5, 0.5))


def in_unity(mat):
    return not UNITY or mat in UNITY


# Mau DANH NGHIA (sRGB) - mau ma TEN slot goi len, cung la cac tu mau Claude dung trong prompt ("white
# muzzle", "black eyes", "orange fox") nen Tripo to dung mau do. Dung de SO MAU texture -> slot va de HIEN
# trong viewport. Khong so voi mau Unity: trong game "Black" la xam 0.44, "White" xam 0.57 (mat den goc la
# Deco_mat) -> so voi mau game thi mat den ra Gray, mom trang ra Color_20 xanh la (cao dua thu 2026-10-01).
# Slot khong ten (20, 23) khong bao gio tu chon (chi 2 file goc dung).
NOMINAL = {
    1: (0.97, 0.74, 0.62),   # Beige: FBX goc dao/hong ca hoi, game hong ca hoi
    2: (0.07, 0.07, 0.08),   # Black
    3: (0.20, 0.40, 0.88),   # Blue
    4: (0.55, 0.33, 0.18),   # Brown
    5: (0.32, 0.82, 0.90),   # Cyan
    6: (0.13, 0.42, 0.18),   # DarkGreen
    7: (0.42, 0.42, 0.46),   # Gray (dam)
    8: (0.42, 0.75, 0.28),   # Green
    9: (0.96, 0.55, 0.14),   # Orange
    10: (0.96, 0.58, 0.72),  # Pink
    11: (0.52, 0.28, 0.78),  # Purple
    12: (0.88, 0.16, 0.16),  # Red
    13: (0.62, 0.42, 0.95),  # Violet
    14: (0.15, 0.48, 0.52),  # DeepOcean
    15: (0.95, 0.95, 0.94),  # White
    16: (0.97, 0.75, 0.18),  # Yellow (vang dam / vang cam)
    17: (0.82, 0.22, 0.62),  # Magenta
    18: (0.22, 0.25, 0.32),  # Charcoal
    19: (1.00, 0.92, 0.25),  # yellow02 (vang chanh)
    21: (0.25, 0.55, 0.25),  # Forest
    22: (0.50, 0.76, 0.96),  # Sky
    24: (0.62, 0.08, 0.18),  # Crimson
    25: (0.70, 0.70, 0.70),  # Gray (nhat)
    26: (0.98, 0.93, 0.76),  # Cream
    27: (0.42, 0.90, 0.76),  # TurquoiseMint
    28: (0.80, 0.70, 0.95),  # LightLavender
}
NOMINAL_BY_MAT = {mat_name(n, nm): NOMINAL[n] for n, nm, _, _ in PALETTE if n in NOMINAL and nm}


def nominal_lin(mat):
    """Mau danh nghia (linear) cua slot - hien trong viewport. Slot la -> mau game."""
    c = NOMINAL_BY_MAT.get(mat)
    return _lin(c) if c else game_rgb(mat)


# Mat do UV: bo goc dung DUNG mot texel density - 2.148 o UV / 1 met (don vi Blender sau
# import), do tren 27 file, p25-p75 = 2.145-2.297. Texture len lap lai nen UV quyet dinh
# co mui dan; cot mui dan (truc V) chay DOC tren mat dung.
UV_DENSITY = 2.148

DECO_MAT = "Deco_mat"
DECO_RE = re.compile(r"^Deco_mat\d*$")
# Deco_mat to mau bang UV: moi manh D_ dong UV vao MOT diem tren Deco_Texture.png
# (83% manh Deco co UV rong < 0.01). File texture khong co trong thu muc FBX nen
# chua biet diem nao mau gi; day la 20 diem bo goc dung nhieu nhat (u, v, so manh).
DECO_CELLS = [
    (0.70, 0.74, 201), (0.99, 0.76, 158), (0.30, 0.29, 155), (0.08, 0.21, 147),
    (0.64, 0.34, 146), (0.71, 0.49, 116), (0.86, 0.74, 112), (0.17, 0.74, 112),
    (0.05, 0.40, 112), (0.30, 0.28, 110), (0.04, 0.47, 104), (0.26, 0.72, 104),
    (0.92, 0.96, 104), (0.74, 0.49, 100), (0.08, 0.20, 97), (0.89, 0.06, 96),
    (0.70, 0.36, 82), (0.07, 0.21, 69), (0.95, 0.62, 56), (0.77, 0.74, 49),
]


def resolve_color(c):
    """'Pink' | 'pink' | 10 | '10' | 'Color_10_Pink_mat' -> ten material chuan."""
    if c is None:
        return None
    s = str(c).strip()
    if s in PALETTE_BY_MAT:
        return s
    for n, nm, _, _ in PALETTE:
        if s == str(n) or (nm and s.lower() == nm.lower()):
            return mat_name(n, nm)
    raise KeyError("Mau '%s' khong co trong bang 28 mau. Xem: python woolcut/run.py palette" % c)


# ---------------------------------------------------------------- loai S / M / D
# QUY TAC CUA NGUOI DUNG (2026-09-30), dung cho model MOI:
#   M_ = manh SCALE NHO DUOC: to, tron, ti le gan 1:1:1
#   S_ = manh ghep, manh scale nho qua hoac khong can scale (det, dai, noi)
#   D_ = vat nho de trang tri
# Do tren bo goc: D_ khop ro (79% D_ < 8% co model). M_ va S_ goc lai co hinh
# gan nhu nhau (canh ngan/dai trung vi 0.52 vs 0.49; dau meo Vocalist tron ma la S_)
# -> file cu khong theo chat; lay quy tac cua nguoi dung lam chuan, khong hoc file cu.
# Gameplay (50 level trong D:\BlenderTool\Level, do 2026-10-01): moi level can so manh quan len
# (M_, Type 1) p10-p90 = 17-39, trung vi 27; so mau 8-14, trung vi 12; manh quan len thuong
# 15-24% co model. Duoi 8 manh M thi gan nhu khong choi duoc.
LEVEL_M = (17, 39)
LEVEL_M_MIN = 8
LEVEL_COLORS = (8, 14)
LEVEL_M_BIG = 0.5          # 17% manh quan len that > 35% co model -> chi bao khi > 50%
# Do tren 108 file goc (2026-10-01, 10791 mesh): S va M CO HINH NHU NHAU - co so voi model trung vi
# M 23% / S 20%, ngan/dai trung vi 0.52 / 0.49 -> moi luat hinh dang doan S/M dung ~50%. Chon M la
# quyet dinh THIET KE (manh nao quan len). D thi khop: 90% D < 9% co model.
# Luat tu dong = luat loi cua nguoi dung (M to, tron, scale nho duoc; S manh ghep / dep / khong can;
# D vat nho trang tri) + CAN SO M ve khoang level (auto_kinds). Nguoi dung chinh tay o buoc 3.
KIND_D_MAX = 0.08         # co (canh dai nhat / canh dai nhat model) duoi muc nay -> D
KIND_M_MIN = 0.08          # M khong qua nho (nho hon la D) ...
KIND_M_COMPACT = 0.25      # ... va khong mong det: canh ngan / canh dai >= muc nay


def classify(dims, model_side):
    """dims: kich thuoc 3 truc cua manh; model_side: canh dai nhat ca model."""
    d = sorted(abs(x) for x in dims)
    if d[2] <= 0 or model_side <= 0:
        return "S"
    rel = d[2] / model_side
    if rel < KIND_D_MAX:
        return "D"
    if rel >= KIND_M_MIN and d[0] / d[2] >= KIND_M_COMPACT:
        return "M"
    return "S"


def auto_kinds(dims, closed=None, m_range=LEVEL_M, side=None):
    """Loai tu dong cho CA BO manh: luat tung manh (classify) roi can so M ve khoang level.
    Qua nhieu M -> ha manh nho / det nhat xuong S; qua it -> nang manh S kin, to, tron nhat len M.
    Manh HO khong bao gio la M (M co nho dan, ho thi lo ruot)."""
    n = len(dims)
    closed = list(closed) if closed is not None else [True] * n
    side = side or max((max(abs(x) for x in d) for d in dims), default=0) or 1.0
    kinds, score = [], []
    for d, c in zip(dims, closed):
        k = classify(d, side)
        if k == "M" and not c:
            k = "S"
        e = sorted(abs(x) for x in d)
        kinds.append(k)
        score.append((e[2] / side) * (0.5 + (e[0] / e[2] if e[2] > 0 else 0)))
    nm = kinds.count("M")
    if nm > m_range[1]:
        for i in sorted((i for i in range(n) if kinds[i] == "M"), key=lambda i: score[i])[:nm - m_range[1]]:
            kinds[i] = "S"
    elif nm < m_range[0]:
        cand = sorted((i for i in range(n) if kinds[i] == "S" and closed[i]), key=lambda i: -score[i])
        for i in cand[:m_range[0] - nm]:
            kinds[i] = "M"
    return kinds


# ---------------------------------------------------------------- cau tao
UV_NAME = "map1"                   # 99.5% mesh goc: layer UV ten map1 (Maya)
ROOT_ROT_X_DEG = 90.0                 # empty goc khi mo trong Blender: xoay X 90
ROOT_SCALE = 0.01                     # ... va scale 0.01 = Maya, don vi cm, Y-up
NAME_RE = re.compile(r"^(S|M|D|DL|D\d)_[A-Za-z0-9_]+?(\.\d{3})?$")
SHARP_ANGLE_DEG = 60.0                # canh gay hon goc nay thi chia normal (ong 8 canh = 45 do van muot)

# ---------------------------------------------------------------- so do
SIZE_TARGET = 6.1                     # canh dai nhat, trung vi 108 file (don vi Blender)
SIZE_RANGE = (2.8, 10.8)              # min..max bo goc (bo file IceCream hong)
SIZE_OK = (4.2, 8.6)                  # ~p10..p90
MESH_RANGE = (9, 630)
MESH_OK = (35, 260)                   # ~p10..p90, trung vi 90
TRIS_RANGE = (2680, 38610)
FACES_PER_MESH_MED = 54
QUAD_SHARE = 0.835                    # ti le mat tu giac cua ca bo
MATS_PER_FILE = (3, 23)               # trung vi 9
CENTER_TOL = 0.15                     # tam hop bao lech goc, theo canh dai nhat (68/108 < 8%)
