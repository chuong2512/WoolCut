"""BANG CHAM DIEM CHUAN GAME truoc khi xuat (2026-10-07, nguoi dung: "tao FBX chuan va dep theo so luong lon").

Ba nhom, moi dong ok / canh bao / loi:
  GAMEPLAY  luat cua level Wooler (std.LEVEL_*): 17-39 manh M (quan len), 8-14 mau, M khong qua to, M phai kin.
  HINH      so voi 108 FBX goc cung dang (sep.TARGET): bo phan mau (manh cung mau cham nhau gop lai), mang cung mau
            lon nhat, cap doi xung trai/phai cung mau, manh khong cham gi, decor lo lung khoi manh chu.
  KY THUAT  material co trong Unity, so mesh / tam giac trong khoang bo goc, manh S/M li ti.
Diem = 100 - 25 x loi - 8 x canh bao (>= 85 Dat, >= 60 Can xem, con lai Truot).

Do tren MESH THAT (toa do the gioi), dung chung cho panel (canh dang sua, truoc khi xuat) va export.run (sau khi dung
cay S/M/D). measure() can bpy; verdict / text khong can."""
import json, os, time
import numpy as np
from . import std, sep

TOUCH_REL = 0.015         # hai manh cach nhau < 1.5% co model = cham (giong phan tich bo goc, scratchpad)
MIRROR_REL = 0.04         # cap doi xung: tam lech < 4% co model sau khi lat qua truc X
FLOAT_REL = 0.06          # decor cach manh chu > 6% co model = lo lung (3% thi 29/88 file goc bi bao)
TINY_REL = 0.03           # manh S/M canh dai nhat < 3% co model = vun
LEVEL = {"info": -1, "ok": 0, "warn": 1, "err": 2}
VI_LEVEL = {"info": "tham khảo", "ok": "đạt", "warn": "cảnh báo", "err": "LỖI"}


def _geom(o):
    """(V the gioi [n,3], F tam giac [m,3]) cua object mesh."""
    me = o.data
    me.calc_loop_triangles()
    V = np.empty(len(me.vertices) * 3, np.float64)
    me.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    M = np.array(o.matrix_world)
    V = V @ M[:3, :3].T + M[:3, 3]
    F = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", F)
    return V, F.reshape(-1, 3)


def _closed(o):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(o.data)
    ok = len(bm.edges) > 0 and all(len(e.link_faces) == 2 for e in bm.edges)
    bm.free()
    return ok


def items_from_scene(objs):
    """Manh trong canh (panel) -> hang cham diem, cung luat voi export.build: loai wc_kind > wc_kind_auto > luat co;
    M ho thi xuat thanh S; mau = material (nguoi dung doi) > wc_color; D: manh chu = wc_host."""
    from . import export
    import bpy
    bpy.context.view_layer.update()
    W = [_geom(o)[0] for o in objs if len(o.data.vertices)]
    if not W:
        return []
    lo = np.min([w.min(0) for w in W], 0)
    hi = np.max([w.max(0) for w in W], 0)
    side = float((hi - lo).max()) or 1.0
    out = []
    for o in objs:
        if not len(o.data.polygons):
            continue
        k = export.kind_of(o, side)
        opened = k == "M" and not _closed(o)
        out.append(dict(obj=o, name=o.name, kind="S" if opened else k, mat=export.color_of(o), host=o.get("wc_host"),
                        demoted=opened))
    return out


UV_ANGLE_MAX = 8


def uv_distortion(objs):
    """Meo UV cua cac mesh (theo dien tich): (goc trung binh do, phan dien tich lech > 2x so voi mat do cua mesh)."""
    import bmesh
    import math
    s_ang = s_bad = s_a = 0.0
    for o in objs:
        me = o.data
        if not me.uv_layers:
            continue
        bm = bmesh.new()
        bm.from_mesh(me)
        uvl = bm.loops.layers.uv.active
        A3, AU, ANG = [], [], []
        for f in bm.faces:
            ls = f.loops
            for j in range(1, len(ls) - 1):
                tri = (ls[0], ls[j], ls[j + 1])
                p = [l.vert.co for l in tri]
                u = [l[uvl].uv for l in tri]
                A3.append((p[1] - p[0]).cross(p[2] - p[0]).length / 2)
                AU.append(abs((u[1].x - u[0].x) * (u[2].y - u[0].y) - (u[2].x - u[0].x) * (u[1].y - u[0].y)) / 2)
                da = 0.0
                for q in range(3):
                    e1, e2 = p[(q + 1) % 3] - p[q], p[(q + 2) % 3] - p[q]
                    f1, f2 = u[(q + 1) % 3] - u[q], u[(q + 2) % 3] - u[q]
                    if min(e1.length, e2.length, f1.length, f2.length) > 1e-12:
                        da += abs(e1.angle(e2) - f1.angle(f2))
                ANG.append(da / 3)
        bm.free()
        A3, AU, ANG = np.array(A3), np.array(AU), np.array(ANG)
        tot = A3.sum()
        if tot <= 1e-14 or AU.sum() <= 1e-14:
            continue
        r = np.log2(np.maximum(AU, 1e-20) / np.maximum(A3 * AU.sum() / tot, 1e-20))
        s_ang += float((ANG * A3).sum())
        s_bad += float(A3[np.abs(r) > 1].sum())
        s_a += float(tot)
    if s_a <= 0:
        return 0.0, 0.0
    return math.degrees(s_ang / s_a), s_bad / s_a


def measure(items, kind="char", uv=False):
    """items: [{obj, name, kind S/M/D, mat, host(ten), demoted}] -> ket qua cham (dict, luu duoc JSON)."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    P = []
    for it in items:
        V, F = _geom(it["obj"])
        if not len(F):
            continue
        a = V[F]
        area = float(np.linalg.norm(np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]), axis=1).sum() / 2)
        P.append(dict(it, V=V, F=F, lo=V.min(0), hi=V.max(0), area=area, tris=len(F),
                      tree=BVHTree.FromPolygons(V.tolist(), F.tolist())))
    if not P:
        return dict(score=0, grade="Trượt", kind=kind, counts={}, checks=[], when=time.strftime("%Y-%m-%d %H:%M"))
    lo = np.min([p["lo"] for p in P], 0)
    hi = np.max([p["hi"] for p in P], 0)
    side = float((hi - lo).max()) or 1.0
    for p in P:
        p["ext"] = float((p["hi"] - p["lo"]).max()) / side
    SM = [p for p in P if p["kind"] != "D"]
    D = [p for p in P if p["kind"] == "D"]
    eps = TOUCH_REL * side

    def touch(a, b):
        if np.any(a["hi"] + eps < b["lo"]) or np.any(b["hi"] + eps < a["lo"]):
            return False
        s, big = (a, b) if len(a["V"]) <= len(b["V"]) else (b, a)
        for v in s["V"][::max(1, len(s["V"]) // 200)]:
            if big["tree"].find_nearest(Vector(v), eps)[0] is not None:
                return True
        return False
    n = len(SM)
    par_col, par_all = list(range(n)), list(range(n))
    deg = [0] * n

    def root(par, x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for i in range(n):
        for j in range(i + 1, n):
            if touch(SM[i], SM[j]):
                deg[i] += 1
                deg[j] += 1
                par_all[root(par_all, i)] = root(par_all, j)
                if SM[i]["mat"] == SM[j]["mat"]:
                    par_col[root(par_col, i)] = root(par_col, j)
    groups = {}
    for i in range(n):
        groups.setdefault(root(par_col, i), []).append(i)
    tot = sum(p["area"] for p in SM) or 1.0
    garea = sorted((sum(SM[i]["area"] for i in g) / tot, g) for g in groups.values())[::-1]
    big_parts = sum(1 for a, _ in garea if a >= sep.MIN_AREA)
    largest = garea[0][0] if garea else 0.0
    largest_who = SM[max(garea[0][1], key=lambda i: SM[i]["area"])]["name"] if garea else ""
    isolated = [SM[i]["name"] for i in range(n) if deg[i] == 0] if n > 1 else []
    # cap doi xung qua mat phang X = tam model (mat truoc -Y nen trai/phai la truc X)
    mx = float((lo[0] + hi[0]) / 2)
    tol = MIRROR_REL * side
    mism, seen = [], set()
    for i in range(n):
        a = SM[i]
        ca = (a["lo"] + a["hi"]) / 2
        if abs(ca[0] - mx) < tol or i in seen:
            continue
        ea = np.sort(a["hi"] - a["lo"])
        for j in range(n):
            if j == i or j in seen:
                continue
            b = SM[j]
            cb = (b["lo"] + b["hi"]) / 2
            if abs(cb[0] + ca[0] - 2 * mx) > tol or abs(cb[1] - ca[1]) > tol or abs(cb[2] - ca[2]) > tol:
                continue
            eb = np.sort(b["hi"] - b["lo"])
            if np.any(np.minimum(ea, eb) < 0.7 * np.maximum(ea, eb)):
                continue
            seen.update((i, j))
            if a["mat"] != b["mat"]:
                mism.append("%s / %s" % (a["name"], b["name"]))
            break
    # decor lo lung: cach manh chu (hoac manh S/M gan nhat) qua xa
    by_name = {p["name"]: p for p in SM}
    floating = []
    for d in D:
        hosts = [by_name[d["host"]]] if d.get("host") in by_name else SM
        best = 1e18
        for v in d["V"][::max(1, len(d["V"]) // 40)]:
            for h in hosts:
                r = h["tree"].find_nearest(Vector(v))
                if r[0] is not None:
                    best = min(best, r[3])
        if best > FLOAT_REL * side:
            floating.append(d["name"])
    mats = sorted({p["mat"] for p in SM})
    nM = sum(1 for p in SM if p["kind"] == "M")
    g = sep.TARGET.get(kind, sep.TARGET["char"])
    lim = sep.SCORE_LIMITS.get(kind, sep.SCORE_LIMITS["char"])
    C = []

    def add(group, label, value, want, level, detail=""):
        C.append(dict(group=group, label=label, value=value, want=want, level=level, detail=detail))
    # Cham thu 88 FBX goc (2026-10-07): moi muc chi "loi" khi ngoai han ro (choi khong duoc / Unity khong nhan);
    # muc bo goc cung hay pham (cap trai/phai khac mau 56/88, manh khong cham 35/88, M > 50% co 27/88) = "tham khao".
    lm = std.LEVEL_M
    add("GAMEPLAY", "Mảnh M (quấn len)", nM, "%d–%d" % lm,
        "ok" if lm[0] <= nM <= lm[1] else "err" if nM < 10 or nM > 48 else "warn",
        "ít M quá: chia thêm bộ phận to / đổi S kín thành M" if nM < lm[0] else
        "nhiều M quá: đổi mảnh nhỏ / dẹt sang S" if nM > lm[1] else "")
    lc = std.LEVEL_COLORS
    nc = len(mats)
    add("GAMEPLAY", "Số màu (S + M)", nc, "%d–%d" % lc,
        "ok" if lc[0] <= nc <= lc[1] else "err" if nc < lim["colors_p10"] or nc > lc[1] + 3 else "warn",
        "thêm màu cho viền, phụ kiện" if nc < lc[0] else "gộp các màu gần nhau" if nc > lc[1] else "")
    dem = [p["name"] for p in P if p.get("demoted")]
    add("GAMEPLAY", "Mảnh M hở (sẽ thành S)", len(dem), "0", "warn" if dem else "ok", ", ".join(dem[:4]))
    huge = [p["name"] for p in SM if p["kind"] == "M" and p["ext"] > std.LEVEL_M_BIG]
    add("GAMEPLAY", "Mảnh M to > %d%% cỡ" % (100 * std.LEVEL_M_BIG), len(huge), "tham khảo", "info", ", ".join(huge[:4]))
    add("HÌNH", "Bộ phận màu", big_parts, "≥ %d (mẫu %d)" % (lim["parts_p10"], g["parts"]),
        "ok" if big_parts >= lim["parts_p10"] else "warn",
        "thiếu viền, nẹp, phụ kiện khác màu" if big_parts < lim["parts_p10"] else "")
    add("HÌNH", "Mảng cùng màu lớn nhất", "%.0f%%" % (100 * largest), "≤ %.0f%% (mẫu %.0f%%)" % (
        100 * lim["largest_p90"], 100 * g["largest"]), "ok" if largest <= lim["largest_p90"] else "warn",
        ("gồm %s - đổi màu một phần (áo, viền) cho tách mảng" % largest_who) if largest > lim["largest_p90"] else "")
    add("HÌNH", "Decor lơ lửng", len(floating), "0", "warn" if floating else "ok", ", ".join(floating[:4]))
    add("HÌNH", "Cặp trái/phải khác màu", len(mism), "tham khảo", "info", "; ".join(mism[:3]))
    add("HÌNH", "Mảnh không chạm gì", len(isolated), "tham khảo", "info", ", ".join(isolated[:4]))
    bad = [m for m in mats if not std.in_unity(m)]
    add("KỸ THUẬT", "Material không có trong Unity", len(bad), "0", "err" if bad else "ok", ", ".join(bad))
    nmesh = len(P)
    add("KỸ THUẬT", "Số mesh", nmesh, "%d–%d" % std.MESH_RANGE,
        "ok" if std.MESH_RANGE[0] <= nmesh <= std.MESH_RANGE[1] else "warn")
    tris = sum(p["tris"] for p in P)
    add("KỸ THUẬT", "Tam giác", tris, "≤ %d" % std.TRIS_RANGE[1], "ok" if tris <= std.TRIS_RANGE[1] else "warn",
        "nặng hơn mọi model gốc - giảm số mặt khi tạo / Mesh lại mảnh to" if tris > std.TRIS_RANGE[1] else "")
    if uv:                                       # chi khi xuat (UV cuoi); bo goc 3-6 do, unwrap cu 10-14 do
        ua, ub = uv_distortion([p["obj"] for p in SM])
        add("KỸ THUẬT", "Méo UV (góc trung bình)", "%.1f°" % ua, "≤ %d° (gốc 3–6°)" % UV_ANGLE_MAX,
            "ok" if ua <= UV_ANGLE_MAX else "warn",
            "lệch diện tích > 2× ở %.0f%% bề mặt - dùng Xuất FBX tối ưu (UV mới)" % (100 * ub) if ua > UV_ANGLE_MAX else "")
    tiny = [p["name"] for p in SM if p["ext"] < TINY_REL]
    add("KỸ THUẬT", "Mảnh S/M vụn (< %d%% cỡ)" % (100 * TINY_REL), len(tiny), "0", "warn" if tiny else "ok",
        ", ".join(tiny[:4]))
    ne = sum(1 for c in C if c["level"] == "err")
    nw = sum(1 for c in C if c["level"] == "warn")
    sc = max(0, 100 - 25 * ne - 8 * nw)
    return dict(score=sc, grade=grade(sc), kind=kind, errors=ne, warnings=nw, when=time.strftime("%Y-%m-%d %H:%M"),
                counts=dict(M=nM, S=sum(1 for p in SM if p["kind"] == "S"), D=len(D), colors=len(mats),
                            parts=big_parts, largest=round(largest, 3), meshes=nmesh, tris=tris),
                checks=C)


def grade(score):
    return "Đạt" if score >= 85 else "Cần xem" if score >= 60 else "Trượt"


def lines(res):
    """Bang cho log / terminal."""
    out = ["[cham diem] %d/100 - %s (%d loi, %d canh bao) - so voi mau '%s'" % (
        res["score"], res["grade"], res.get("errors", 0), res.get("warnings", 0), res.get("kind", "char"))]
    for c in res.get("checks", []):
        out.append("  %-9s %-34s %8s  can %-18s %s%s" % (c["group"], c["label"], c["value"], c["want"],
                                                       VI_LEVEL[c["level"]], ("  - " + c["detail"]) if c["detail"]
                                                       and c["level"] != "ok" else ""))
    return out


def save(res, *paths):
    for p in paths:
        if p:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1, ensure_ascii=False)


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None
