"""Buoc 3a - CHUAN BI: model Tripo -> cac KHOI KIN, muot, moi mat mot mau bang.

1. Nap file, xoay mat truoc ve -Y, chuan hoa: tam X/Y = 0, day Z = 0, canh dai nhat = 10 don vi
   (de Claude doc toa do tren anh luoi cho de).
2. Mau: gom cum mau texture cua model -> mau bang 28 slot (color.palette_labels, chep tu PrimForge).
3. Tach KHOI ROI (Tripo hay de mat, mu, do vat thanh khoi rieng). Moi khoi:
   - nho va kin -> giu nguyen luoi;
   - con lai -> voxel remesh (kin, deu, het nep gap/khoi chong), bo vo trong, giam con ~ngan sach mat,
     lam min Taubin, chuyen mau tu luoi goc theo diem gan nhat, loc da so.
4. Ghi work/<Ten>/prep.npz + prep.json va anh luoi toa do cho buoc lap ke hoach."""
import os, json, math, time, collections
import numpy as np
import bpy, bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from . import load, color, std, bl
from .tm import TM

SIZE = 10.0              # canh dai nhat sau chuan hoa
VOXELS = 170             # so o voxel theo canh dai nhat cua ca model
BUDGET = 19000           # tong tam giac cac khoi truoc khi cat (bo goc <= 38.6k ca model)
KEEP_SMALL = 0.06        # khoi kin nho hon muc nay (theo co model) giu nguyen luoi


def _shells(obj):
    """Tach object thanh cac khoi roi -> [(mang chi so mat goc)]."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    seen = np.zeros(len(bm.faces), bool)
    out = []
    for f0 in bm.faces:
        if seen[f0.index]:
            continue
        st, comp = [f0], []
        seen[f0.index] = True
        while st:
            f = st.pop()
            comp.append(f.index)
            for v in f.verts:
                for g in v.link_faces:
                    if not seen[g.index]:
                        seen[g.index] = True
                        st.append(g)
        out.append(np.sort(np.array(comp)))
    bm.free()
    return out


def _shell_object(obj, faces, name):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    keep = set(faces.tolist())
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _apply_mods(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=False, depsgraph=dg)
    ob.modifiers.clear()
    old = ob.data
    ob.data = me
    bpy.data.meshes.remove(old)


def _drop_inner(t):
    """Voxel remesh mot khoi ho/chong cho ra vo ngoai + vo trong: bo cac vo nam trong vo khac."""
    comps = t.split_components()
    if len(comps) <= 1:
        return t
    comps.sort(key=lambda c: -c.size)
    keep = []
    for c in comps:
        q = c.V[0]
        if any(k.contains(q) for k in keep):
            continue
        keep.append(c)
    if len(keep) == 1:
        return keep[0]
    V, F = [], []
    off = 0
    for c in keep:
        V.append(c.V)
        F.append(c.F + off)
        off += len(c.V)
    return TM(np.concatenate(V), np.concatenate(F))


def _close_loops(bm, max_edges=120):
    """Bit tung LO con sot (vong canh bien don) bang quat tam giac ve tam lo, dung chieu mat ke. holes_fill cua
    Blender bo qua lo co dinh 'no' (khung xe may Tripo 2026-10-02: 28 canh ho -> ca khung bi dung lai bang voxel,
    ong mong hon o voxel bien mat). Tra ve so lo da bit."""
    from mathutils import Vector
    bnd = [e for e in bm.edges if e.is_boundary]
    seen = set()
    made = 0
    for e0 in bnd:
        if e0 in seen:
            continue
        seen.add(e0)
        start, v = e0.verts[0], e0.verts[1]
        chain, ok = [e0], True
        while v is not start:
            nxt = [e for e in v.link_edges if e.is_boundary and e not in seen]
            if len(nxt) != 1 or len(chain) > max_edges:
                ok = False
                break
            seen.add(nxt[0])
            chain.append(nxt[0])
            v = nxt[0].other_vert(v)
        if not ok or len(chain) < 3:
            continue
        vs = list({x for e in chain for x in e.verts})
        cv = bm.verts.new(sum((x.co for x in vs), Vector()) / len(vs))
        for e in chain:
            l = e.link_loops[0]                         # mat ke di a -> b thi mat moi di b -> a
            a, b = l.vert, l.link_loop_next.vert
            try:
                bm.faces.new((b, a, cv))
            except ValueError:
                pass
        made += 1
    return made


def _drop_specks(bm, min_faces=4):
    """Bo cac thanh phan rac < min_faces mat (mang 2 mat chong nhau sinh ra khi tach canh khong da tap)."""
    bm.faces.ensure_lookup_table()
    seen, kill = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        st, comp = [f], []
        seen.add(f.index)
        while st:
            g = st.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        st.append(h)
        if len(comp) < min_faces:
            kill.extend(comp)
    if kill:
        bmesh.ops.delete(bm, geom=kill, context="FACES")
    return len(kill)


def _keep_surface(ob):
    """GIU NGUYEN be mat Tripo (nguoi dung 2026-10-01: "model tho dang dep"): chi han dinh trung, vá lo nho,
    tam giac hoa. Tra ve TM, hoac None neu van ho / khong da tap (de dung remesh du phong)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    size = max(ob.dimensions) or 1.0
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5 * size)
    bnd = [e for e in bm.edges if e.is_boundary]
    if bnd:
        bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
    # canh dinh 3-5 mat (Tripo dan cac khoi con chong len nhau): tach canh roi va lai tung khe -> da tap kin
    nm = [e for e in bm.edges if len(e.link_faces) > 2]
    if nm:
        bmesh.ops.split_edges(bm, edges=nm)
        bnd = [e for e in bm.edges if e.is_boundary]
        if bnd:
            bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
    # canh bien con lai (lo 1-2 canh suy bien): han dinh hai dau
    bnd = [e for e in bm.edges if e.is_boundary]
    if bnd:
        bmesh.ops.remove_doubles(bm, verts=list({v for e in bnd for v in e.verts}), dist=1e-3 * size)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7 * size)
    _drop_specks(bm)
    if any(e.is_boundary for e in bm.edges):
        _close_loops(bm)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.verts.ensure_lookup_table()
    V = np.array([v.co[:] for v in bm.verts], dtype=np.float64).reshape(-1, 3)
    F = np.array([[v.index for v in f.verts] for f in bm.faces], dtype=np.int64).reshape(-1, 3)
    bm.free()
    t = TM(V, F)
    used, inv = np.unique(t.F.ravel(), return_inverse=True)
    t = TM(t.V[used], inv.reshape(-1, 3))
    _, cnt = t.edge_faces()
    bad = int((cnt != 2).sum())
    return t, bad


def solidify_shell(src_ob, faces, labels, rgbs, model_size, budget, name, surface="keep"):
    """Mot khoi roi -> TM kin + nhan mau tung mat. surface="keep": giu luoi Tripo (mac dinh);
    "remesh": voxel remesh + lam min (du phong khi luoi vo nat)."""
    ob = _shell_object(src_ob, faces, name)
    size = max(ob.dimensions)
    raw = bl.tm_from_mesh(ob.data)
    closed = raw.is_closed()
    kept = None
    kept_bad = None
    if surface == "keep":
        kept, bad = _keep_surface(ob)
        if bad > max(6, 0.002 * len(kept.F)):
            print("  khoi %s: %d canh ho/khong da tap sau khi va -> dung remesh du phong" % (name, bad))
            kept_bad, kept = kept, None
    lab_src = np.asarray(labels)
    # BVH tren da giac goc cua khoi (thu tu = thu tu `faces` da sap xep) de chuyen nhan mau
    bvh = BVHTree.FromPolygons([v.co.copy() for v in ob.data.vertices],
                               [tuple(p.vertices) for p in ob.data.polygons])
    if kept is not None:
        t = kept
    elif closed and size < KEEP_SMALL * model_size:
        t = raw
    else:
        vs = max(model_size / VOXELS, size / 45.0) if size < 0.25 * model_size else model_size / VOXELS
        vs = min(vs, size / 12.0)
        m = ob.modifiers.new("vox", "REMESH")
        m.mode = "VOXEL"
        m.voxel_size = vs
        m.adaptivity = 0.0
        _apply_mods(ob)
        t = _drop_inner(bl.tm_from_mesh(ob.data))
        if kept_bad is not None:
            # dung lai bang voxel lam MAT HINH (ong / tam mong hon o voxel bien mat: khung xe may vo 184 manh) ->
            # giu luoi da va du con vai canh ho (2026-10-02)
            ka, ta = kept_bad.face_areas().sum(), t.face_areas().sum()
            if len(t.split_components()) > 3 * max(1, len(kept_bad.split_components())) or ta < 0.6 * ka:
                print("  khoi %s: voxel lam mat hinh (%d manh, dien tich %.0f%%) -> giu luoi da va"
                      % (name, len(t.split_components()), 100 * ta / max(ka, 1e-12)))
                t = kept_bad
                kept_bad = "used"
        if kept_bad == "used":
            pass
        elif len(t.F) > budget:
            ob2 = bpy.data.objects.new(name + "_d", bl.mesh_from_tm(t, name + "_d", flat_caps=False))
            bpy.context.scene.collection.objects.link(ob2)
            d = ob2.modifiers.new("dec", "DECIMATE")
            d.decimate_type = "COLLAPSE"
            d.ratio = budget / len(t.F)
            d.use_collapse_triangulate = True
            _apply_mods(ob2)
            t2 = bl.tm_from_mesh(ob2.data)
            bpy.data.objects.remove(ob2, do_unlink=True)
            if t2.is_closed():
                t = t2
        if kept_bad != "used":                      # luoi goc da va: khong lam min
            t.taubin(iters=6)
    # nhan mau: tam moi mat moi -> mat gan nhat tren luoi goc (chi so mat cua ob, = thu tu faces)
    C = t.face_centers()
    lab = np.empty(len(C), np.int64)
    rgb = np.zeros((len(C), 3))
    rgb_src = np.asarray(rgbs)
    for i, c in enumerate(C):
        hit = bvh.find_nearest(Vector(c))
        j = hit[2] if hit[2] is not None else 0
        lab[i] = lab_src[j]
        rgb[i] = rgb_src[j]
    t.col = lab
    t.meta["rgb"] = rgb
    bpy.data.objects.remove(ob, do_unlink=True)
    return t, closed


PREP_VERSION = 10         # tang khi doi buoc chuan bi -> split tu chuan bi lai (8: + mesh lai part co vat mong)
BUMP_SCALES = (0.05, 0.08)   # ban kinh do (theo co model): nho = mat, mui, nut, duoi tron; vua = tay, tai
BUMP_REL = 0.22          # u = dinh nho cao hon mat phang khop vong lan can ban kinh R it nhat 0.22 R
BUMP_AREA = 0.04         # u <= 4% dien tich model
BUMP_SPAN = 4.0          # va kich thuoc vung nong <= 4 R


def _local_height(t, R):
    """Do nho cua tung dinh so voi MAT PHANG khop cac dinh trong ban kinh R quanh no (do cong o co R): u nho nhu
    mui, duoi, ban tay cao hon han; dau / than tron chi cong nhe. (Lam phang Laplace lam ca khoi tron co lai nen
    dau / than cung thanh 'u' - gau truc 2026-10-02.)"""
    from mathutils.kdtree import KDTree
    V, F = t.V, t.F
    fn = t.face_normals()
    vn = np.zeros_like(V)
    for j in range(3):
        np.add.at(vn, F[:, j], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    kd = KDTree(len(V))
    for i, v in enumerate(V):
        kd.insert(Vector(v), i)
    kd.balance()
    h = np.zeros(len(V))
    for i, v in enumerate(V):
        nb = [j for (_, j, _) in kd.find_range(Vector(v), R)]
        if len(nb) < 6:
            continue
        P = V[nb]
        c = P.mean(0)
        w_, U = np.linalg.eigh(np.cov((P - c).T))
        n = U[:, 0]
        if n @ vn[i] < 0:
            n = -n
        h[i] = (v - c) @ n
    return h


def find_bumps(t, model_size, total_area, R):
    """Vung nong (u nho) o co R -> danh sach mang chi so mat."""
    F = t.F
    h = _local_height(t, R)
    hot = (h > BUMP_REL * R)[F].all(1)
    if not hot.any():
        return []
    ef, _ = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    adj = [[] for _ in range(len(F))]
    for a, b in ef[ok]:
        adj[a].append(b)
        adj[b].append(a)
    ar = t.face_areas()
    seen = np.zeros(len(F), bool)
    out = []
    for s0 in np.where(hot)[0]:
        if seen[s0]:
            continue
        comp, st = [], [s0]
        seen[s0] = True
        while st:
            f = st.pop()
            comp.append(f)
            for g in adj[f]:
                if hot[g] and not seen[g]:
                    seen[g] = True
                    st.append(g)
        comp = np.array(comp)
        a = ar[comp].sum()
        P = t.V[np.unique(F[comp].ravel())]
        span = float((P.max(0) - P.min(0)).max())
        if a > BUMP_AREA * total_area or span > BUMP_SPAN * R or a < 0.00005 * total_area or len(comp) < 3:
            continue
        out.append(comp)
    return out


def _inside_frac(t, others):
    """Ti le dien tich cua t nam TRONG cac khoi kin `others` (tia theo 3 truc, da so)."""
    from mathutils.bvhtree import BVHTree
    C, A = t.face_centers(), t.face_areas()
    ins = np.zeros(len(C), bool)
    for o in others:
        lo, hi = o.V.min(0), o.V.max(0)
        m = np.all((C >= lo) & (C <= hi), axis=1) & ~ins
        if not m.any():
            continue
        bvh = BVHTree.FromPolygons([Vector(v) for v in o.V], [tuple(int(i) for i in f) for f in o.F], all_triangles=True)
        for k in np.where(m)[0]:
            votes = 0
            for d in (Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 1, 0))):
                p, cnt = Vector(C[k]), 0
                for _ in range(64):
                    h = bvh.ray_cast(p, d)
                    if h[0] is None:
                        break
                    cnt += 1
                    p = h[0] + d * 1e-5
                votes += cnt % 2
            ins[k] = votes >= 2
    return float(A[ins].sum() / max(A.sum(), 1e-12))


def _fin_frac(t, size):
    """Ti le dien tich VAT KHONG DO DAY (tia vao trong cham mat doi dien < 1.5% co part): yen xe may co vat mong
    lom chom thua 4.6%, part binh thuong < 4%."""
    bvh = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)
    C, N, A = t.face_centers(), t.face_normals(), t.face_areas()
    thin = np.zeros(len(C), bool)
    for k in range(len(C)):
        n = Vector(N[k])
        if n.length < 1e-9:
            continue
        n.normalize()
        h = bvh.ray_cast(Vector(C[k]) - n * 1e-5 * size, -n, 0.015 * size)
        thin[k] = h[0] is not None
    return float(A[thin].sum() / max(A.sum(), 1e-12))


def _all_bvh(tms):
    V, F, off = [], [], 0
    for t in tms:
        V.append(t.V)
        F.append(t.F + off)
        off += len(t.V)
    V, F = np.concatenate(V), np.concatenate(F)
    return BVHTree.FromPolygons([Vector(v) for v in V], [tuple(int(i) for i in f) for f in F], all_triangles=True)


def _visible_frac(t, bvh, rays=6):
    """Ti le dien tich cua t NHIN THAY tu ngoai: tia tu mat theo phap tuyen (+ vai tia lech) thoat ra khong cham gi."""
    rng = np.random.default_rng(7)
    C, N, A = t.face_centers(), t.face_normals(), t.face_areas()
    eps = 1e-4 * float((t.V.max(0) - t.V.min(0)).max())
    vis = np.zeros(len(C), bool)
    for k in range(len(C)):
        n = N[k] / (np.linalg.norm(N[k]) or 1.0)
        for j in range(rays):
            d = n if j == 0 else n + rng.normal(size=3) * 0.5
            d = d / (np.linalg.norm(d) or 1.0)
            if d @ n <= 0.05:
                continue
            if bvh.ray_cast(Vector(C[k] + d * eps), Vector(d))[0] is None:
                vis[k] = True
                break
    return float(A[vis].sum() / max(A.sum(), 1e-12))


def _clean_parts(tms, model_size):
    """KHOI NAO RA KHOI DO (nguoi dung 2026-10-02): (1) part co >= 4% co model nam KHUAT >= 50% trong part kin khac
    (moay-o / vanh long trong lop xe: chi lo vai manh vun) -> BO; (2) part HO (luoi loi, vat mong) co >= 4% -> dung
    lai bang voxel theo co rieng cua no (bl.voxel_rebuild). Decor nho cam nua than vao be mat (oc, dinh tan) giu."""
    from . import bl
    out, dropped, fixed = [], 0, 0
    closed = [t for t in tms if t.is_closed()]
    all_bvh = _all_bvh(tms)
    for t in tms:
        size = float((t.V.max(0) - t.V.min(0)).max())
        if size >= 0.04 * model_size:
            others = [o for o in closed if o is not t and float((o.V.max(0) - o.V.min(0)).max()) > size * 0.8]
            f = _inside_frac(t, others) if others else 0.0
            if f >= 0.5:
                # mat / mui gau truc 2026-10-05: cam nua than vao dau (khuat 53%) nhung NHIN THAY 46% -> phai giu;
                # moay-o trong lop xe: thay 5-7% -> bo. Chi bo khi gan nhu khong nhin thay tu ngoai.
                vf = _visible_frac(t, all_bvh)
                if vf < 0.12:
                    print("  [don part] bo part khuat %.0f%%, chi thay %.0f%% (%d mat, co %.2f, tam %s)" % (
                        100 * f, 100 * vf, len(t.F), size, np.round((t.V.min(0) + t.V.max(0)) / 2, 2).tolist()))
                    dropped += 1
                    continue
            fin = _fin_frac(t, size)
            if not t.is_closed() or fin >= 0.04:
                why = "part ho" if not t.is_closed() else "vat mong %.0f%%" % (100 * fin)
                for div in (70.0, 140.0):                 # ong mong (phuoc): o voxel min gap doi neu lan dau vo
                    t2 = bl.voxel_rebuild(t, voxel=size / div)
                    if t2 is not None and len(t2.split_components()) <= 4 and \
                            t2.face_areas().sum() >= 0.5 * t.face_areas().sum():
                        print("  [don part] mesh lai %s (%d -> %d mat, co %.2f)" % (why, len(t.F), len(t2.F), size))
                        t = t2
                        fixed += 1
                        break
        out.append(t)
    if dropped or fixed:
        print("[don part] bo %d part khuat, mesh lai %d part loi" % (dropped, fixed))
    return out


def split_bumps(t, model_size, total_area, cut_base=900):
    """Tach moi u nho ra khoi rieng TRUOC moi nhat cat khac (nguoi dung 2026-10-02: "tai, mat, duoi... can duoc tach
    ra truoc khi cat"). U nho truoc (mui tach khoi mom truoc), roi u vua. Nhat cat: mat phang qua vung nong, roi DO
    VAO TRONG toi tiet dien hep nhat (co duoi, co tay) - khong xen ngon."""
    pieces = [t]
    made = 0
    k = 0
    for scale in BUMP_SCALES:
        R = scale * model_size
        for host0 in list(pieces):
            if float((host0.V.max(0) - host0.V.min(0)).max()) < 3 * R:
                continue
            for comp in find_bumps(host0, model_size, total_area, R):
                cen = host0.face_centers()[comp].mean(0)
                host = min(pieces, key=lambda p: p.dist(cen))
                P = host0.V[np.unique(host0.F[comp].ravel())]
                c = P.mean(0)
                w_, U = np.linalg.eigh(np.cov((P - c).T))
                nrm = U[:, 0]
                vn = host0.face_normals()[comp].sum(0)
                if nrm @ vn < 0:
                    nrm = -nrm
                # do vao trong (nguoc phap tuyen) toi 1.5 R, nghieng <= 20 do: tiet dien hep nhat = co cua u
                p0 = c - nrm * 0.75 * R
                pp, nn, area = host.snap(p0, nrm, 0.75 * R, q=p0)
                k += 1
                res = host.plane_cut(pp, nn, cut_base + k, mode="local", q=pp, grow=False)
                if not res:
                    continue
                # chi xet manh VUA bi nhat nay cat ra (co mat nap ma cut nay): khoi "than" cua Tripo thuong gom
                # nhieu manh roi (tap de, can bot...) - truoc day ca cac manh roi do bi coi la "phan cat ra", to qua
                # gioi han -> huy luon nhat cat tai / ban tay (gau dau bep 2026-10-02)
                touched = sorted([p for p in res if (p.cap == cut_base + k).any()], key=lambda p: -len(p.F))
                small = touched[1:]
                if not small or any(float((p.V.max(0) - p.V.min(0)).max()) > 3.5 * R for p in small):
                    continue                        # cat lan vao khoi chinh -> bo
                pieces.remove(host)
                pieces.extend(res)
                made += 1
    return pieces, made


def blur_colors(t, rgb, iters=3):
    """Trung binh mau texture voi mat ke (khuech tan nhe) - xoa vet bong / nhieu texture truoc khi gom cum."""
    ef, _ = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    A, B = ef[ok, 0], ef[ok, 1]
    ar = t.face_areas()
    c = np.asarray(rgb, dtype=np.float64).copy()
    for _ in range(iters):
        L = color._lab(np.clip(c, 0, 1))
        dl = np.sqrt(((L[A] - L[B]) ** 2).sum(1))
        k = np.exp(-(dl / 14.0) ** 2)                 # giu canh: mat ke khac mau han (mat den / mat cam) khong tron
        S = c * ar[:, None] * 2.0
        W = ar * 2.0
        np.add.at(S, A, c[B] * (ar[B] * k)[:, None])
        np.add.at(S, B, c[A] * (ar[A] * k)[:, None])
        W = W + np.bincount(A, weights=ar[B] * k, minlength=len(c)) + np.bincount(B, weights=ar[A] * k, minlength=len(c))
        c = S / np.maximum(W, 1e-12)[:, None]
    return c


NOISE = 0.004        # vung mau nho hon 0.4% dien tich model ...
SAME_PAINT_DE = 22   # ... va mau texture gan vung ke (bong do, chuyen sac) -> nhap
TINY = 0.0003        # vung nho hon nua: nhap bat ke mau


def clean_labels(t, lab, rgb, total_area):
    """Don dom mau: vung nho cung mau son voi vung ke (chi khac do sang/bong) thi nhap vao vung ke; vung
    tuong phan manh (mat, mui, nut) giu. So tren MAU TEXTURE THAT trung binh tung vung."""
    lab = np.asarray(lab).copy()
    ar = t.face_areas()
    ef, _ = t.edge_faces()
    ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    A, B = ef[ok, 0], ef[ok, 1]
    for _ in range(12):
        diff = lab[A] != lab[B]
        # vung = thanh phan lien thong cung nhan
        par = np.arange(len(lab))

        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]
                x = par[x]
            return x
        for a, b in zip(A[~diff], B[~diff]):
            ra, rb = find(a), find(b)
            if ra != rb:
                par[ra] = rb
        rid = np.array([find(i) for i in range(len(lab))])
        _, rid = np.unique(rid, return_inverse=True)
        R = rid.max() + 1
        rarea = np.bincount(rid, weights=ar, minlength=R)
        rcol = np.stack([np.bincount(rid, weights=ar * rgb[:, k], minlength=R) for k in range(3)], 1)             / np.maximum(rarea, 1e-12)[:, None]
        rlab = color._lab(np.clip(rcol, 0, 1))
        border = collections.defaultdict(collections.Counter)
        for a, b in zip(A[diff], B[diff]):
            border[rid[a]][rid[b]] += 1
            border[rid[b]][rid[a]] += 1
        changed = 0
        taken = set()
        for r in np.argsort(rarea):
            if rarea[r] >= NOISE * total_area:
                break
            if r in taken or not border[r]:
                continue
            h = border[r].most_common(1)[0][0]
            if h in taken:
                continue
            de = float(color.de2000(rlab[r][None], rlab[h][None], 1.0)[0, 0])
            if rarea[r] < TINY * total_area or de < SAME_PAINT_DE:
                lab[rid == r] = lab[rid == h][0]
                taken.add(r)
                changed += 1
        if not changed:
            break
    return lab


def prompt_colors(path, name, work=""):
    """Tu mau trong prompt cua model (work/prompt.txt hoac <Ten>.tripo.json canh file model) -> slot bang mau."""
    import re
    from . import prompt as pr
    text = pr.find_prompt(path, name, work)
    if not text:
        return []
    words = set(re.findall(r"[a-z]+", text.lower()))
    out = []
    for n, nm, _, _ in std.PALETTE:
        if nm and nm.lower() in words and n in std.NOMINAL:
            out.append(std.mat_name(n, nm))
    if "light" in words and "blue" in words:
        out.append(std.mat_name(22, "Sky"))
    return out


def run(path, name, out_dir, turn=0.0, opts=None):
    opts = dict(opts or {})
    surface = opts.get("surface", "keep")
    opts.setdefault("colors", 14)          # game cho 8-14 mau/level; it hon thi mat den bi gop vao xam
    if "prefer" not in opts:
        opts["prefer"] = prompt_colors(path, name, out_dir)
        if opts["prefer"]:
            print("[mau] uu tien mau theo prompt: %s" % ", ".join(c.replace("Color_", "") for c in opts["prefer"]))
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    srcs = load.load(path, turn, float(opts.get("tilt", 0.0)))
    # chuan hoa toa do
    lo = np.array([1e9] * 3); hi = -lo
    for o in srcs:
        V = np.array([v.co[:] for v in o.data.vertices])
        lo = np.minimum(lo, V.min(0)); hi = np.maximum(hi, V.max(0))
    s = SIZE / float((hi - lo).max())
    c = (lo + hi) / 2
    M = Matrix.Scale(s, 4) @ Matrix.Translation(Vector((-c[0], -c[1], -lo[2])))
    for o in srcs:
        o.data.transform(M)
        o.data.update()
    # mau bang tung mat
    raw = [load.face_colors(o) for o in srcs]
    rgb_all = np.concatenate([c for c, _, _ in raw])
    lab_idx = np.zeros(len(rgb_all), dtype=np.int64)        # nhan tam, gan bang sau khi lam min mau
    # khoi roi
    shells = []
    off = 0
    total_area = 0.0
    for o in srcs:
        nF = len(o.data.polygons)
        area = np.empty(nF); o.data.polygons.foreach_get("area", area)
        for fs in _shells(o):
            shells.append((o, fs, lab_idx[off + fs], rgb_all[off + fs], float(area[fs].sum())))
        total_area += area.sum()
        off += nF
    shells.sort(key=lambda x: -x[4])
    tms, info = [], []
    for i, (o, fs, labs, rgbs, a) in enumerate(shells):
        if a < 2e-4 * total_area and len(fs) < 40:
            continue                                   # vun
        budget = max(120, int(BUDGET * a / total_area))
        t, closed = solidify_shell(o, fs, labs, rgbs, SIZE, budget, "shell_%d" % i, surface)
        if len(t.F) < 4:
            continue

        tms.append(t)
        info.append(dict(id=len(tms) - 1, faces=int(len(t.F)), src_closed=bool(closed), closed=t.is_closed(),
                         lo=t.V.min(0).round(3).tolist(), hi=t.V.max(0).round(3).tolist(), color=None))
    # mau: lam min mau texture tren khoi kin -> gom cum + chon slot bang cho ca model -> don dom
    per = []
    for t in tms:
        t.meta["rgb"] = blur_colors(t, t.meta["rgb"], iters=4)
        per.append((None, t.meta["rgb"], [None] * len(t.F), t.face_areas()))
    _, lab_all = color.palette_labels(per, opts)
    names = sorted(set(l for l in lab_all if l))
    idx = {n: i for i, n in enumerate(names)}
    off = 0
    for t in tms:
        t.col = np.array([idx.get(l, -1) for l in lab_all[off:off + len(t.F)]], dtype=np.int64)
        off += len(t.F)
        if len(t.F) > 30:
            t.col = t.smooth_labels(t.col, iters=2)
        t.col = clean_labels(t, t.col, t.meta["rgb"], total_area)
    # chi tiet nho ra (mat, mui, tai, duoi, tay...) -> khoi rieng TRUOC moi nhat cat cua ke hoach
    bumps = opts.get("bumps", "auto")
    if bumps == "auto":
        # Model Tripo DA CHIA PART (xe may part 2026-10-02: 83 part, lon nhat 12% so mat): tach u nho chi bam nat part
        # (den pha thanh nhieu vong, dau ong xa roi ra) -> bo qua. Nhan vat lien khoi (than > 35% so mat) van tach.
        # 2026-10-05 xe may do choi: than xe lien 43% so mat -> nguong cu (35%) cho chay tach u -> bam den pha, ham bo,
        # moay-o thanh mieng vo nghia. Nay CHI tu tach khi model gan nhu MOT KHOI LIEN (part lon nhat >= 70% so mat);
        # con lai bat bang o "Tu tach u nho" o panel (--bumps).
        nf = sorted((len(fs) for _, fs, _, _, _ in shells), reverse=True)
        frac = nf[0] / max(1, sum(nf)) if nf else 1.0
        bumps = frac >= 0.7
        print("[chi tiet] part lon nhat %.0f%% so mat -> %s" % (100 * frac, "tach u nho (model lien khoi)" if bumps
                                                                else "KHONG tach u nho (model da chia part)"))
    if bumps:
        new, nb = [], 0
        for t in tms:
            ext = float((t.V.max(0) - t.V.min(0)).max())
            if ext > 0.3 * SIZE and t.is_closed():
                ps, made = split_bumps(t, SIZE, total_area)
                nb += made
                new.extend(ps)
            else:
                new.append(t)
        tms = sorted(new, key=lambda t: -len(t.F))
        print("[chi tiet] tach %d u nho ra khoi rieng (mat, mui, tai, duoi...) truoc khi cat" % nb)
    tms = _clean_parts(tms, SIZE)
    info = [dict(id=i, faces=int(len(t.F)), src_closed=True, closed=t.is_closed(),
                 lo=t.V.min(0).round(3).tolist(), hi=t.V.max(0).round(3).tolist(), color=None)
            for i, t in enumerate(tms)]
    for i, t in enumerate(tms):
        cnt = np.bincount(t.col[t.col >= 0], minlength=len(names))
        info[i]["color"] = names[int(cnt.argmax())] if cnt.sum() else None
    for o in srcs:                                      # bo model goc (khong render de len khoi kin)
        bpy.data.objects.remove(o, do_unlink=True)
    # luu
    arr = {}
    for i, t in enumerate(tms):
        arr["V%d" % i], arr["F%d" % i], arr["C%d" % i] = t.V, t.F, t.col
        if "rgb" in t.meta:
            arr["R%d" % i] = t.meta["rgb"]
    np.savez_compressed(os.path.join(out_dir, "prep.npz"), **arr)
    meta = dict(name=name, src=os.path.abspath(path), turn=turn, tilt=float(opts.get("tilt", 0.0)), scale=s, names=names, shells=info,
                prep_version=PREP_VERSION, bumps=bool(bumps),
                size=SIZE, tris=int(sum(len(t.F) for t in tms)))
    with open(os.path.join(out_dir, "prep.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, ensure_ascii=False)
    print("[prep] %d khoi, %d tam giac, %d mau, %.1fs" % (len(tms), meta["tris"], len(names), time.time() - t0))
    for d in info:
        print("  khoi %2d  %6d mat  %s  %s..%s  %s" % (d["id"], d["faces"], "kin" if d["closed"] else "HO ",
                                                    d["lo"], d["hi"], (d["color"] or "").replace("Color_", "")))
    return tms, names, meta


def load_prep(out_dir):
    with open(os.path.join(out_dir, "prep.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    z = np.load(os.path.join(out_dir, "prep.npz"))
    tms = []
    i = 0
    while "V%d" % i in z:
        t = TM(z["V%d" % i], z["F%d" % i], z["C%d" % i])
        if "R%d" % i in z:
            t.meta["rgb"] = z["R%d" % i]
        tms.append(t)
        i += 1
    return tms, meta["names"], meta
