"""Buoc 3c - THUC THI KE HOACH CAT (plan.json) tren cac khoi da chuan bi (prep.npz).

Ke hoach do Claude viet sau khi nhin anh luoi toa do (hoac nguoi dung sua tay). Moi thao tac chi muc
tieu bang mot DIEM trong toa do model (khong bang so thu tu manh) nen chay lai van dung:

  {"op": "cut",     "at": [x,y,z], "normal": [nx,ny,nz], "snap": 0.5}
        cat CUC BO: chi vong giao tuyen bao quanh `at` (cai co, goc tai, goc tay). snap > 0: tu tim
        trong +-snap don vi (va nghieng <= 20 do) cho tiet dien HEP NHAT. snap = 0: cat dung cho.
  {"op": "split",   "target": [x,y,z], "axes": ["x","y","z"], "center": [x,y,z]?}
        chia MUI: cat ca khoi bang cac mat phang qua tam (2/4/8 mui nhu dau gau BearArt).
        "normals": [[...],...] thay cho axes neu can nghieng.
  {"op": "slices",  "target": [x,y,z], "axis": "z", "n": 3}         cat khoanh deu theo truc
  {"op": "sectors", "target": [x,y,z], "n": 4, "start": 0}          cat cung quanh truc dung (de tron)
  {"op": "merge",   "targets": [[x,y,z], [x,y,z], ...]}
  {"op": "decal",   "target": [x,y,z], "color": "Black"}            vung mau -> mieng dan D
  {"op": "color",   "target": [x,y,z], "color": "Orange"}
  {"op": "kind",    "target": [x,y,z], "kind": "S|M|D"}
  {"op": "drop",    "target": [x,y,z]}                               bo manh rac

Sau cac thao tac: tu tach vung mau nho thanh D (mat, mui, nut), to mot mau moi manh, can so manh S/M
ve [min, max], gan loai S/M/D, xuat parts.blend + parts.json + anh."""
import os, json, math, time, collections
import numpy as np
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree
from . import std, bl, render, prep, look, uv as uvmod
from .tm import TM, unit, basis as basis_of, piece_frame, piece_axes

AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
DECAL_MAX_MODEL = 0.012      # vung mau khac nho hon 1.2% dien tich model ...
FEATURE_MAX = 0.006          # truoc khi cat: chi tach chi tiet <= 0.6% (mat, mui, long tai) - vanh mu 1.5% la khoi
BUMP_R = 0.8                 # ban kinh do u khi Claude cat tai / sung / duoi (= prep BUMP_SCALES[1] x canh 10)
SPLIT_MIN_VOL = 0.03         # chi CHIA MUI khoi >= 3% the tich model (nguoi dung 2026-10-02: "chi cat manh to")
BEVEL = 0.15                 # bo cong mep cat (wc/fillet.py voxel + lam tron dai mep); 0.3 ranh rong qua (2026-10-05); 0 = tat
PATCH_MAX = 0.03             # ... rieng mang mau PHANG (quang mat gau truc) toi 3% (nguoi dung 2026-10-02)
PATCH_FLAT = 0.12            # phang = do cao / duong kinh vung <= 0.12 (vanh mu 0.26, mat bi 0.2-0.27)
DECAL_MAX_PIECE = 0.30       # ... va < 30% dien tich manh -> mieng dan D
DECAL_MIN_MODEL = 0.0004     # nho hon nua la vet nhieu -> to theo mau manh (mat cao 0.13%)
DECAL_ROUND = 0.3            # mieng dan phai tron gon (can(l2/l1) phan tan tam mat); vet dai = nhieu
DECAL_T = 0.05               # be day mieng dan (don vi model, model dai 10)
DECAL_DE = 22.0              # vung mau phai khac han mau manh (dE2000 danh nghia) moi thanh D


class Piece:
    _n = 0

    def __init__(self, tm, src=None, parent=None):
        Piece._n += 1
        self.id = Piece._n
        self.tm = tm
        self.src = src
        self.parent = parent           # (ma nhat cat, id manh cha) - de hoan tac khi gop
        self.kind = None               # chon tay
        self.color = None              # chon tay
        self.host = None               # D: id manh duoc dan len
        self.decal = False
        self.label = ""
        self.hidden = ""               # ly do AN (part xau / khong ro - nguoi dung 2026-10-08): khong xuat FBX
        self.cache = {}

    @property
    def size(self):
        return self.tm.size

    def dims(self):
        lo, hi = self.tm.bbox()
        return (hi - lo).tolist()


def real_col(col):
    """Mau goc cua mat, ke ca mat nam duoi mieng dan D (ma hoa -2 - c)."""
    col = np.asarray(col)
    return np.where(col <= -2, -2 - col, col)


def roundness(t, comp, ar):
    """1 = vung tron deu, ~0.1 = vet dai (vien bong do, soc)."""
    if len(comp) < 3:
        return 0.0
    P = t.face_centers()[comp]
    w = ar[comp] / max(ar[comp].sum(), 1e-12)
    c = (P * w[:, None]).sum(0)
    ev = np.sort(np.linalg.eigvalsh(((P - c).T * w) @ (P - c)))[::-1]
    return float(np.sqrt(max(ev[1], 0) / ev[0])) if ev[0] > 0 else 0.0


def flatness(t, comp):
    """Do cao lon nhat cua vung so voi mat phang khop vien / duong kinh vung (mang dan phang ~0.03-0.1)."""
    F = t.F[comp]
    vs = np.unique(F.ravel())
    P = t.V[vs]
    if len(P) < 4:
        return 1.0
    c = P.mean(0)
    w_, U = np.linalg.eigh(np.cov((P - c).T))
    h = np.abs((P - c) @ U[:, 0]).max() * 2
    d = np.sqrt(((P - c) ** 2).sum(1)).max() * 2
    return float(h / max(d, 1e-9))


class Run:
    def __init__(self, tms, names, verbose=True):
        self.names = list(names)
        self.pieces = []
        for i, t in enumerate(tms):
            for c in t.split_components(min_faces=4):
                self.pieces.append(Piece(c, src="khoi %d" % i))
        self.cut_id = 100
        self.parents = {}              # cut_id -> (Piece cha, [id con])
        self.verbose = verbose
        lo = np.min([p.tm.V.min(0) for p in self.pieces], axis=0)
        hi = np.max([p.tm.V.max(0) for p in self.pieces], axis=0)
        self.lo, self.hi = lo, hi
        self.model_size = float((hi - lo).max())
        self.total_area = float(sum(p.tm.face_areas().sum() for p in self.pieces))
        self.model_vol = float(sum(abs(p.tm.volume()) for p in self.pieces)) or 1e-9
        self.log = []
        self.warn = []
        self.trace = None              # dry_run: {chi so thao tac: [(mat phang [(diem, phap tuyen)], TM manh)]}
        self._cur = None

    def _rec(self, planes, piece):
        if self.trace is not None and self._cur is not None and piece is not None:
            cur = self.trace.get(self._cur)
            if cur and len(cur) == 1 and not cur[0][0]:     # thay muc mac dinh (chi manh, chua co mat phang)
                self.trace[self._cur] = []
            self.trace.setdefault(self._cur, []).append(
                ([(np.asarray(c, float), np.asarray(n, float)) for c, n in planes], piece.tm))

    def say(self, *a):
        s = " ".join(str(x) for x in a)
        self.log.append(s)
        if self.verbose:
            print(s)

    def color_index(self, name):
        mn = std.resolve_color(name)
        if mn not in self.names:
            self.names.append(mn)
        return self.names.index(mn)

    # ------------------------------------------------------------ tim manh theo diem
    def find(self, q, solid_only=False):
        q = np.asarray(q, dtype=np.float64)
        cands = [p for p in self.pieces if not (solid_only and p.decal)]
        inside = [p for p in cands if np.all(q >= p.tm.V.min(0) - 1e-6) and np.all(q <= p.tm.V.max(0) + 1e-6)
                  and p.tm.contains(q)]
        if inside:
            return min(inside, key=lambda p: abs(p.tm.volume()))
        return min(cands, key=lambda p: p.tm.dist(q)) if cands else None

    def find_color(self, q, cis):
        """Manh co mat mau thuoc cis gan q nhat (khong can q nam trong manh)."""
        q = np.asarray(q, dtype=np.float64)
        best = None
        for p in self.pieces:
            if p.decal:
                continue
            m = np.isin(real_col(p.tm.col), cis) & (p.tm.cap < 0)
            if not m.any():
                continue
            d = float(np.sqrt(((p.tm.face_centers()[m] - q) ** 2).sum(1)).min())
            if best is None or d < best[0]:
                best = (d, p)
        return best[1] if best else None

    def replace(self, old, new_list, cid=None):
        i = self.pieces.index(old)
        for n in new_list:
            n.parent = (cid, old.id) if cid is not None else old.parent
            n.kind, n.color = old.kind, old.color
            n.src = old.src
        if cid is not None:
            self.parents[cid] = (old, [n.id for n in new_list])
        self.pieces[i:i + 1] = new_list

    def next_cut(self):
        self.cut_id += 1
        return self.cut_id

    # ------------------------------------------------------------ thao tac
    def op_cut(self, o):
        at = np.asarray(o["at"], dtype=np.float64)
        n = unit(o.get("normal", (0, 0, 1)))
        p = self.find(at, solid_only=True)
        snap = float(o.get("snap", 0.5))
        pp, nn = at, n
        if snap > 0:
            pp, nn, area = p.tm.snap(at, n, snap, q=at, grow=(1.0, 2.0, 3.0, 4.0), fallback="keep")
            moved = float(np.linalg.norm(pp - at))
            tilt = math.degrees(math.acos(max(-1, min(1, float(nn @ n)))))
            self.say("  snap: dich %.2f, nghieng %.0f do, tiet dien %.2f" % (moved, tilt, area))
        cid = self.next_cut()
        res = None
        bump = self._bump_plane(p, at, n) if snap > 0 and o.get("bump", True) else None
        used = None
        if bump is not None:
            res = p.tm.plane_cut(bump[0], bump[1], cid, mode="local", q=bump[0], grow=False)
            touched = sorted([x for x in (res or []) if (x.cap == cid).any()], key=lambda x: -len(x.F))
            if len(touched) >= 2 and all(float((x.V.max(0) - x.V.min(0)).max()) <= 3.5 * BUMP_R for x in touched[1:]):
                self.say("  theo u noi (chan u, huong moc that): tam %s huong %s" % (
                    np.round(bump[0], 2).tolist(), np.round(bump[1], 2).tolist()))
                used = (bump[0], bump[1])
            else:
                res = None
        if not res:
            res = p.tm.plane_cut(pp, nn, cid, mode="local", q=pp)
            used = (pp, nn) if res else None
        if not res and snap > 0:                      # thu lai dung cho Claude chi
            used = (at, n)
            res = p.tm.plane_cut(at, n, cid, mode="local", q=at)
        if res and len(res) > 2:
            self.say("  (cung mat phang con %d vung khac phai cat theo de tach roi)" % (len(res) - 2))
        if not res:
            self.say("  !! cut %s khong tach duoc manh (vong khong khep / khong tach roi) - bo qua" % o.get("label", at.tolist()))
            self.warn.append("cut %s that bai" % o.get("label", at.tolist()))
            return False
        self._rec([used or (pp, nn)], p)
        new = [Piece(t) for t in res]
        self.replace(p, new, cid)
        self.say("  cut %-14s -> %d manh %s" % (o.get("label", ""), len(new), [len(x.tm.F) for x in new]))
        return True

    def _bump_plane(self, p, at, n):
        """Nhat cut cua Claude nham vao mot U NHO RA (tai, sung, duoi): neu cach `at` < BUMP_R co vung u (prep.find_bumps)
        moc cung huong (lech < 50 do) thi cat o CHAN u theo huong moc that cua u (nhu prep.split_bumps). Mat phang
        Claude chi thuong gan thang dung -> lan sang suon dau (gau dau bep 2026-10-02: tai kem mot mang bau duc)."""
        try:
            tot = sum(float(x.tm.face_areas().sum()) for x in self.pieces)
            comps = prep.find_bumps(p.tm, 10.0, tot, BUMP_R)
        except Exception as e:                       # khong de loi do u lam hong ca ke hoach
            self.say("  (bo qua do u: %s)" % e)
            return None
        best = None
        fc = p.tm.face_centers()
        fn = p.tm.face_normals()
        for comp in comps:
            P = p.tm.V[np.unique(p.tm.F[comp].ravel())]
            c = P.mean(0)
            d = float(np.linalg.norm(c - at))
            if d > BUMP_R:
                continue
            w_, U = np.linalg.eigh(np.cov((P - c).T))
            nrm = U[:, 0]
            if nrm @ fn[comp].sum(0) < 0:
                nrm = -nrm
            if float(nrm @ n) < math.cos(math.radians(50)):
                continue
            if best is None or d < best[0]:
                best = (d, c, nrm)
        if best is None:
            return None
        _, c, nrm = best
        p0 = c - nrm * 0.75 * BUMP_R
        pp, nn, _ = p.tm.snap(p0, nrm, 0.75 * BUMP_R, q=p0, fallback="keep")   # khong troi ra giua u
        return pp, nn

    def _rebuild(self, x):
        """Khoi co BE MAT TU GIAO (vanh / moay-o long xuyen trong lop - xe may Tripo 2026-10-02: 161 cap mat cat nhau)
        -> moi mat phang qua vung do deu cat hong. Dung lai RIENG khoi nay bang voxel remesh (gop phan long nhau
        thanh mot vo kin), giam ve so mat tuong duong, mau / ma nap lay theo mat goc gan nhat. None neu khong can /
        khong dung duoc."""
        from mathutils.bvhtree import BVHTree
        t = x.tm
        x.rebuilt = True
        bvh = BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)
        Fs = [set(f.tolist()) for f in t.F]
        nx = sum(1 for a, b in bvh.overlap(bvh) if a < b and not (Fs[a] & Fs[b]))
        if nx == 0:
            return None
        made = []
        try:
            me = bpy.data.meshes.new("_rb")
            me.from_pydata(t.V.tolist(), [], t.F.tolist())
            me.update()
            ob = bpy.data.objects.new("_rb", me)
            bpy.context.scene.collection.objects.link(ob)
            made.append(ob)
            r = ob.modifiers.new("vx", "REMESH")
            r.mode = "VOXEL"
            r.voxel_size = max(float(t.size) / 110.0, 1e-3)
            n_now = None
            dg = bpy.context.evaluated_depsgraph_get()
            me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
            n_now = 2 * len(me2.polygons)
            ob2 = bpy.data.objects.new("_rb2", me2)
            bpy.context.scene.collection.objects.link(ob2)
            made.append(ob2)
            if n_now > 1.3 * len(t.F):
                d = ob2.modifiers.new("dc", "DECIMATE")
                d.ratio = 1.3 * len(t.F) / n_now
            dg = bpy.context.evaluated_depsgraph_get()
            me3 = bpy.data.meshes.new_from_object(ob2.evaluated_get(dg))
            t2 = bl.tm_from_mesh(me3)
            bpy.data.meshes.remove(me3)
        except Exception as e:
            self.say("  (dung lai khoi tu giao loi: %s)" % e)
            return None
        finally:
            for o in made:
                m = o.data
                bpy.data.objects.remove(o, do_unlink=True)
                if m is not None and m.users == 0:
                    bpy.data.meshes.remove(m)
        if not t2.is_closed() or len(t2.F) < 20:
            return None
        kd = KDTree(len(t.F))
        for i, cc in enumerate(t.face_centers()):
            kd.insert(Vector(cc), i)
        kd.balance()
        idx = np.array([kd.find(Vector(cc))[1] for cc in t2.face_centers()], dtype=np.int64)
        t2.col, t2.cap = t.col[idx].copy(), t.cap[idx].copy()
        y = Piece(t2)
        y.kind, y.color, y.src, y.parent = x.kind, x.color, x.src, x.parent
        y.rebuilt = True
        self.say("  (khoi tu giao %d cap mat -> dung lai bang voxel %d mat roi cat lai)" % (nx, len(t2.F)))
        return y

    def _full_cuts(self, p, planes, label, force=False):
        v = abs(p.tm.volume())
        if not force and v < SPLIT_MIN_VOL * self.model_vol:
            self.say("  bo qua %s: khoi nho (%.1f%% the tich model) - chi chia khoi to; them \"force\": true de ep"
                     % (label, 100 * v / self.model_vol))
            return [p]
        self._rec(planes, p)
        parts = [p]
        for (c, n) in planes:
            cid = self.next_cut()
            nxt = []
            for x in parts:
                res = x.tm.plane_cut(c, n, cid, mode="all")
                if not res and getattr(x, "rebuilt", False) is False and x.tm.section(c, n)["loops"]:
                    x2 = self._rebuild(x)                    # be mat tu giao -> dung lai roi cat lai
                    if x2 is not None:
                        res = x2.tm.plane_cut(c, n, cid, mode="all")
                        x = x2
                if res:
                    kids = [Piece(t) for t in res]
                    for k in kids:
                        k.parent = (cid, x.id)
                    self.parents[cid] = self.parents.get(cid, (None, []))
                    nxt += kids
                else:
                    nxt.append(x)
            parts = nxt
        for k in parts:
            k.kind, k.color, k.src = p.kind, p.color, p.src
        v0 = abs(p.tm.volume()) or 1e-9
        big = [k for k in parts if abs(k.tm.volume()) >= 0.01 * v0]
        tiny = [k for k in parts if abs(k.tm.volume()) < 0.01 * v0]
        if big and tiny:                                 # vun o truc / goc do mat phang xe lech -> nhap vao manh ke
            for t in tiny:
                host = min(big, key=lambda b: b.tm.dist(t.tm.centroid()))
                j = big.index(host)
                tm2 = host.tm.merge_with(t.tm)
                if not tm2.is_closed():
                    tm2 = TM(np.concatenate([host.tm.V, t.tm.V]), np.concatenate([host.tm.F, t.tm.F + len(host.tm.V)]),
                             np.concatenate([host.tm.col, t.tm.col]), np.concatenate([host.tm.cap, t.tm.cap]))
                nb = Piece(tm2)
                nb.kind, nb.color, nb.src, nb.parent = host.kind, host.color, host.src, host.parent
                big[j] = nb
            parts = big
        i = self.pieces.index(p)
        self.pieces[i:i + 1] = parts
        self.say("  %s -> %d manh" % (label, len(parts)))
        return parts

    # ------------------------------------------------------------ chia mui: doc / ngang / mui cam / luoi
    def _target(self, o, solid_only=True):
        """Manh dich: 'anchor' (diem tren be mat, do panel ghi) > 'target' (diem bat ky)."""
        if o.get("anchor"):
            return self.find_surface(o["anchor"])
        return self.find(o["target"], solid_only=solid_only)

    def _frame(self, p, o):
        """Xoay he truc theo khoi dai nam nghieng (tm.piece_frame); "world": true de giu truc the gioi; "rot": [do x,y,z]
        = nguoi dung xoay them mat cat quanh truc THE GIOI (panel, 2026-10-06)."""
        Ru = np.eye(3)
        if o.get("rot") and any(abs(float(x)) > 1e-6 for x in o["rot"]):
            from mathutils import Euler
            Ru = np.array(Euler([math.radians(float(x)) for x in o["rot"]]).to_matrix())
        if o.get("world") or o.get("rot_world"):
            return Ru
        R = Ru @ piece_frame(p.tm.V, p.tm.F)
        if not np.allclose(R, np.eye(3)):
            u = piece_axes(p.tm.V, p.tm.F)[0][0]
            self.say("  (khoi nghieng %.0f do: truc cat xoay theo truc khoi %s)"
                     % (math.degrees(math.acos(min(1.0, float(np.abs(u).max())))), np.round(u, 2).tolist()))
        return R

    def _axis(self, v, p=None, R=None, default="z"):
        """'x'/'y'/'z' = truc the gioi (xoay theo khoi nghieng neu co R); 'long'/'mid'/'short' = truc rieng cua
        khoi (dai, giua, ngan); vector = dung nguyen."""
        v = default if v is None else v
        if isinstance(v, str):
            s = v.lower()
            if s in ("long", "mid", "short") and p is not None:
                return piece_axes(p.tm.V, p.tm.F)[0][("long", "mid", "short").index(s)]
            e = np.array(AXES[s[-1]], dtype=np.float64) * (-1 if s.startswith("-") else 1)
            return R @ e if R is not None else e
        return unit(v)

    def op_split(self, o):
        """Chia doi / 4 / 8 mui bang mat phang QUA TAM theo cac truc (x: trai/phai, y: truoc/sau, z: tren/duoi)."""
        p = self._target(o)
        c = np.asarray(o["center"], dtype=np.float64) if o.get("center") else p.tm.centroid()
        R = self._frame(p, o) if not o.get("normals") else None
        normals = [unit(n) for n in o.get("normals", [])] or [self._axis(a, p, R) for a in o.get("axes", ["x"])]
        self._full_cuts(p, [(c, n) for n in normals], "split %s" % (o.get("label", "")), force=o.get("force"))

    def op_slices(self, o):
        """Lat / tang song song: n phan deu, hoac "at": [0.3, 0.7] vi tri (0..1 theo chieu khoi)."""
        p = self._target(o)
        ax = self._axis(o.get("axis", "z"), p, self._frame(p, o))
        d = p.tm.V @ ax
        lo, hi = d.min(), d.max()
        c0 = p.tm.centroid()
        fr = o.get("at") or [i / int(o.get("n", 2)) for i in range(1, int(o.get("n", 2)))]
        planes = [(c0 + ax * (lo + (hi - lo) * float(f) - c0 @ ax), ax) for f in fr]
        self._full_cuts(p, planes, "slices %s" % o.get("label", ""), force=o.get("force"))

    def op_grid(self, o):
        """Luoi: "grid": [nx, ny, nz] lat deu theo ca 3 truc (vd [2,2,3] = 12 manh)."""
        p = self._target(o)
        R = self._frame(p, o)
        c0 = p.tm.centroid()
        planes = []
        for k, n in enumerate(o.get("grid", [2, 2, 1])):
            ax = R[:, k]
            d = p.tm.V @ ax
            for i in range(1, int(n)):
                planes.append((c0 + ax * (d.min() + (d.max() - d.min()) * i / int(n) - c0 @ ax), ax))
        self._full_cuts(p, planes, "grid %s" % o.get("label", ""), force=o.get("force"))

    def op_sectors(self, o):
        """MUI CAM: n mui quanh mot truc qua tam (mac dinh truc dung z; "axis": "x"/"y"/vector cho khoi nam ngang).
        n chan: cac mat phang qua truc; n le (3, 5...): moi mui la giao hai nua khong gian (nem)."""
        p = self._target(o)
        k = max(2, int(o.get("n", 4)))
        c = np.asarray(o["center"], dtype=np.float64) if o.get("center") else p.tm.centroid()
        ax = self._axis(o.get("axis", "z"), p, self._frame(p, o))
        e1, e2 = basis_of(ax)
        start = math.radians(float(o.get("start", 0)))

        def m(a):                                       # phap tuyen mat phang chua truc, huong ve phia goc tang
            d = math.cos(a) * e1 + math.sin(a) * e2
            return unit(np.cross(ax, d))
        layers = int(o.get("layers", 1))
        dz = p.tm.V @ ax
        layer_planes = [(c + ax * (dz.min() + (dz.max() - dz.min()) * i / layers - c @ ax), ax) for i in range(1, layers)]
        if k % 2 == 0 and not o.get("exact", True):
            planes = [(c, m(start + math.pi * i / (k // 2))) for i in range(k // 2)]
            self._full_cuts(p, planes + layer_planes, "sectors %s" % o.get("label", ""), force=o.get("force"))
            return
        if not o.get("force") and abs(p.tm.volume()) < SPLIT_MIN_VOL * self.model_vol:
            self.say("  bo qua sectors %s: khoi nho" % o.get("label", ""))
            return
        # MOI so mui (chan / le): GIAO Boolean (Exact) voi tung khoi nem -> moi mui mot khoi, khong phai gop (gop 2 nem hay hong vi mat
        # phang tu xe lech khac nhau hai ben -> dia chia 3 ra 6 ranh, 2026-10-05). Hong thi quay ve cach cu.
        res = self._boolean_sectors(p, c, ax, e1, e2, start, k) if k >= 3 else None
        if not res and k >= 3 and not getattr(p, "rebuilt", False):
            p2 = self._rebuild(p)                    # khoi tu giao (vanh long trong lop) -> dung lai roi chia lai
            if p2 is not None:
                self.pieces[self.pieces.index(p)] = p2
                p = p2
                res = self._boolean_sectors(p, c, ax, e1, e2, start, k)
        if not res and k % 2 == 0:                   # chan: k/2 mat phang qua truc (khong phai ghep nem)
            planes = [(c, m(start + math.pi * i / (k // 2))) for i in range(k // 2)]
            self._full_cuts(p, planes + layer_planes, "sectors %s" % o.get("label", ""), force=True)
            return
        if res:
            if layer_planes:
                out = []
                for x in res:
                    out += self._full_cuts(x, layer_planes, "  tang", force=True)
                res = out
            self.say("  sectors %s -> %d manh (%d mui, boolean chinh xac)" % (o.get("label", ""), len(res), k))
            return
        if k == 2:                                   # hai mui = mot mat phang qua truc
            self._full_cuts(p, [(c, m(start))] + layer_planes, "sectors %s" % o.get("label", ""), force=o.get("force"))
            return
        planes = [(c, m(start + 2 * math.pi * i / k)) for i in range(k)]
        kids = self._full_cuts(p, planes + layer_planes, "sectors %s (%d mui le)" % (o.get("label", ""), k),
                               force=o.get("force"))
        if len(kids) < 2:
            return
        edges = [pl[0] @ ax for pl in layer_planes]
        groups = collections.defaultdict(list)
        for kd in kids:
            v = kd.tm.centroid() - c
            ang = (math.atan2(v @ e2, v @ e1) - start) % (2 * math.pi)
            lay = sum(1 for e in edges if kd.tm.centroid() @ ax > e)
            groups[(int(ang // (2 * math.pi / k)) % k, lay)].append(kd)
        for g in groups.values():
            base = g[0]
            for x in g[1:]:
                base = self.merge(base, x)
        self.say("  -> %d manh (%d mui x %d tang)" % (len(groups), k, layers))

    def _boolean_sectors(self, p, c, ax, e1, e2, start, k):
        """Chia khoi thanh k MUI (k le) bang Boolean INTERSECT voi k lang tru nem. Mat nap = mat cua nem (gan ma nhat cat
        theo DUONG BIEN goc: hai mui ke nhau chung ma). Tra ve danh sach Piece hoac None."""
        from mathutils.kdtree import KDTree
        t = p.tm
        size = float(t.size) or 1.0
        R, H = 4.0 * size, 4.0 * size
        dirs = [math.cos(start + 2 * math.pi * i / k) * e1 + math.sin(start + 2 * math.pi * i / k) * e2 for i in range(k)]
        ids = [self.next_cut() for _ in range(k)]
        made, pieces = [], []
        try:
            me = bpy.data.meshes.new("_bs")
            me.from_pydata(t.V.tolist(), [], t.F.tolist())
            me.update()
            ob = bpy.data.objects.new("_bs", me)
            bpy.context.scene.collection.objects.link(ob)
            made.append(ob)
            kd = KDTree(len(t.F))
            for i, cc in enumerate(t.face_centers()):
                kd.insert(Vector(cc), i)
            kd.balance()
            for i in range(k):
                d0, d1 = dirs[i], dirs[(i + 1) % k]
                ring = [c, c + R * d0, c + R * (d0 + d1), c + R * d1]
                Vw = [q - ax * H for q in ring] + [q + ax * H for q in ring]
                Fw = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
                mw = bpy.data.meshes.new("_wd")
                mw.from_pydata([list(v) for v in Vw], [], Fw)
                mw.update()
                if (np.cross(d0, d1) @ ax) < 0:
                    mw.flip_normals()
                wo = bpy.data.objects.new("_wd", mw)
                bpy.context.scene.collection.objects.link(wo)
                made.append(wo)
                mod = ob.modifiers.new("b", "BOOLEAN")
                mod.operation = "INTERSECT"
                mod.solver = "EXACT"
                mod.object = wo
                dg = bpy.context.evaluated_depsgraph_get()
                me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
                ob.modifiers.remove(mod)
                t2 = bl.tm_from_mesh(me2)
                bpy.data.meshes.remove(me2)
                if not len(t2.F) or not t2.is_closed():
                    return None
                n0 = unit(np.cross(ax, d0))           # phap tuyen mat bien goc i va i+1
                n1 = unit(np.cross(ax, d1))
                C2, N2 = t2.face_centers(), t2.face_normals()
                N2 = N2 / np.maximum(np.linalg.norm(N2, axis=1, keepdims=True), 1e-12)
                cap = np.full(len(t2.F), -1, np.int64)
                for nn, cid in ((n0, ids[i]), (n1, ids[(i + 1) % k])):
                    on = (np.abs((C2 - c) @ nn) < 1e-4 * size) & (np.abs(N2 @ nn) > 0.999)
                    cap[on] = cid
                idx = np.array([kd.find(Vector(cc))[1] for cc in C2], dtype=np.int64)
                t2.col = np.where(cap >= 0, -1, t.col[idx])
                old = t.cap[idx]
                t2.cap = np.where(cap >= 0, cap, old)
                for comp in t2.split_components(min_faces=4):
                    q = Piece(comp)
                    q.kind, q.color, q.src = p.kind, p.color, p.src
                    pieces.append(q)
        except Exception as e:
            self.say("  (boolean mui le loi: %s)" % e)
            return None
        finally:
            for o_ in made:
                m_ = o_.data
                bpy.data.objects.remove(o_, do_unlink=True)
                if m_ is not None and m_.users == 0:
                    bpy.data.meshes.remove(m_)
        v0 = abs(t.volume()) or 1e-9
        pieces = [q for q in pieces if abs(q.tm.volume()) >= 0.005 * v0]
        if len(pieces) < 2:
            return None
        i = self.pieces.index(p)
        self.pieces[i:i + 1] = pieces
        return pieces

    # ------------------------------------------------------------ KHOET theo khoi bao (nguoi dung 2026-10-05: vanh mu xuyen
    # ngang dau - mat phang nao cung cat ca dau). Boolean INTERSECT voi khoi bao -> manh moi; DIFFERENCE -> phan con lai.
    @staticmethod
    def _cutter(o):
        """Khoi bao (V, F) theo toa do model: ring (vanh khan), cylinder, box, sphere."""
        shape = o.get("shape", "cylinder")
        c = np.asarray(o.get("center", [0, 0, 0]), float)
        ax = unit(np.asarray(o.get("axis", [0, 0, 1]), float))
        e1, e2 = basis_of(ax)
        V, F = [], []
        if shape in ("cylinder", "ring"):
            R = float(o.get("radius", 1.0))
            r = float(o.get("inner_radius", 0.0)) if shape == "ring" else 0.0
            h = float(o.get("height", 1.0))
            n = 48
            for zz in (-h / 2, h / 2):
                for rad in ((R, r) if r > 0 else (R,)):
                    for i in range(n):
                        a = 2 * math.pi * i / n
                        V.append(c + ax * zz + rad * (math.cos(a) * e1 + math.sin(a) * e2))
            if r > 0:                                  # 4 vong: duoi-ngoai, duoi-trong, tren-ngoai, tren-trong
                bo, bi, to, ti = 0, n, 2 * n, 3 * n
                for i in range(n):
                    j = (i + 1) % n
                    F += [(bo + i, bo + j, to + j, to + i), (bi + j, bi + i, ti + i, ti + j),
                          (to + i, to + j, ti + j, ti + i), (bo + j, bo + i, bi + i, bi + j)]
            else:
                b, t_ = 0, n
                for i in range(n):
                    j = (i + 1) % n
                    F.append((b + i, b + j, t_ + j, t_ + i))
                F.append(tuple(range(n - 1, -1, -1)))
                F.append(tuple(range(n, 2 * n)))
        elif shape == "box":
            sx, sy, sz = [float(x) / 2 for x in o.get("size", [1, 1, 1])]
            rot = o.get("rot", [0, 0, 0])
            from mathutils import Euler
            Rm = np.array(Euler([math.radians(float(x)) for x in rot]).to_matrix())
            for dz in (-sz, sz):
                for dy in (-sy, sy):
                    for dx in (-sx, sx):
                        V.append(c + Rm @ np.array([dx, dy, dz]))
            F = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        else:                                          # sphere / ellipsoid
            sz = np.asarray(o.get("size", [o.get("radius", 1.0) * 2] * 3), float) / 2
            nu, nv = 32, 16
            V.append(c + np.array([0, 0, -sz[2]]))
            for i in range(1, nv):
                th = math.pi * i / nv - math.pi / 2
                for j in range(nu):
                    ph = 2 * math.pi * j / nu
                    V.append(c + np.array([sz[0] * math.cos(th) * math.cos(ph), sz[1] * math.cos(th) * math.sin(ph),
                                           sz[2] * math.sin(th)]))
            V.append(c + np.array([0, 0, sz[2]]))
            top = len(V) - 1
            for j in range(nu):
                F.append((0, 1 + (j + 1) % nu, 1 + j))
            for i in range(nv - 2):
                for j in range(nu):
                    a, b = 1 + i * nu + j, 1 + i * nu + (j + 1) % nu
                    F.append((a, b, b + nu, a + nu))
            base = 1 + (nv - 2) * nu
            for j in range(nu):
                F.append((base + j, base + (j + 1) % nu, top))
        return [list(map(float, v)) for v in V], F

    def _bool(self, t, cut_vf, operation):
        """Boolean EXACT giua TM t va khoi bao -> TM (hoac None)."""
        made = []
        try:
            me = bpy.data.meshes.new("_bt")
            me.from_pydata(t.V.tolist(), [], t.F.tolist())
            me.update()
            ob = bpy.data.objects.new("_bt", me)
            bpy.context.scene.collection.objects.link(ob)
            made.append(ob)
            mc = bpy.data.meshes.new("_bc")
            mc.from_pydata(cut_vf[0], [], cut_vf[1])
            mc.update()
            mc.validate()
            oc = bpy.data.objects.new("_bc", mc)
            bpy.context.scene.collection.objects.link(oc)
            made.append(oc)
            mod = ob.modifiers.new("b", "BOOLEAN")
            mod.operation = operation
            mod.solver = "EXACT"
            mod.object = oc
            dg = bpy.context.evaluated_depsgraph_get()
            m2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
            t2 = bl.tm_from_mesh(m2)
            bpy.data.meshes.remove(m2)
        except Exception as e:
            self.say("  (boolean loi: %s)" % e)
            return None
        finally:
            for o_ in made:
                m_ = o_.data
                bpy.data.objects.remove(o_, do_unlink=True)
                if m_ is not None and m_.users == 0:
                    bpy.data.meshes.remove(m_)
        return t2 if len(t2.F) and t2.is_closed() else None

    def op_carve(self, o):
        """KHOET: manh moi = manh dich GIAO khoi bao (ring / cylinder / box / sphere); phan con lai = HIEU. Mat moi tren
        khoi bao gan ma nhat cat chung (bo cong duoc). Khoi tu giao -> dung lai voxel roi thu lai."""
        from mathutils.bvhtree import BVHTree
        p = self._target(o)
        if p is None:
            return
        cut = self._cutter(o)
        for attempt in range(2):
            t = p.tm
            a = self._bool(t, cut, "INTERSECT")
            b = self._bool(t, cut, "DIFFERENCE")
            if a is not None and b is not None:
                break
            if attempt == 0 and not getattr(p, "rebuilt", False):
                p2 = self._rebuild(p)
                if p2 is None:
                    break
                self.pieces[self.pieces.index(p)] = p2
                p = p2
        if a is None or b is None:
            self.say("  !! carve %s: boolean hong" % o.get("label", ""))
            return
        v0 = abs(p.tm.volume()) or 1e-9
        cid = self.next_cut()
        bvh = BVHTree.FromPolygons([Vector(v) for v in p.tm.V], [tuple(int(i) for i in f) for f in p.tm.F],
                                   all_triangles=True)
        kd_c = p.tm.face_centers()
        from mathutils.kdtree import KDTree
        kd = KDTree(len(kd_c))
        for i, cc in enumerate(kd_c):
            kd.insert(Vector(cc), i)
        kd.balance()
        tol = 2e-4 * float(p.tm.size)
        out = []
        for res in (a, b):
            C = res.face_centers()
            idx = np.array([kd.find(Vector(cc))[1] for cc in C], dtype=np.int64)
            d = np.array([bvh.find_nearest(Vector(cc))[3] for cc in C])
            newcap = d > tol
            res.col = np.where(newcap, -1, p.tm.col[idx])
            res.cap = np.where(newcap, cid, p.tm.cap[idx])
            for comp in res.split_components(min_faces=4):
                if abs(comp.volume()) >= 0.004 * v0:
                    q = Piece(comp)
                    q.kind, q.color, q.src = p.kind, p.color, p.src
                    out.append(q)
        if len(out) < 2:
            self.say("  !! carve %s: khoi bao khong cat qua manh" % o.get("label", ""))
            return
        i = self.pieces.index(p)
        self.pieces[i:i + 1] = out
        self.say("  carve %s -> %d manh" % (o.get("label", ""), len(out)))

    def op_crease(self, o):
        """CAT THEO NEP GAP (wc/crease.py, tach sau 2026-10-06): "part"+"rest" = diem hai phia (ung vien tool ghi ca vanh
        mat sat bien -> tai hien dung nhat cat Claude da xem; Claude tu chi thi vai diem) hoac "at"+"normal" (+"planar").
        Manh dich = manh co BE MAT gan "anchor" nhat (diem ngay tai nep)."""
        from . import crease
        p = self.find_surface(o["anchor"]) if o.get("anchor") else (
            self.find_surface(o["part"][0]) if o.get("part") else self.find(o["at"], solid_only=True))
        if p is None:
            return
        cid = self.next_cut()
        res = crease.apply(p.tm, o, cid, log=self.say)
        if not res or len(res) < 2:
            self.say("  !! crease %s: khong tach duoc" % o.get("label", ""))
            self.warn.append("crease %s that bai" % o.get("label", ""))
            return
        new = [Piece(t) for t in res]
        self.replace(p, new, cid)
        self.say("  crease %-14s -> %d manh %s" % (o.get("label", ""), len(new), [len(x.tm.F) for x in new]))

    def op_merge(self, o):
        """Gop manh: "targets" (diem bat ky) hoac "anchors" (diem tren be mat - nut Ghep o panel ghi)."""
        ps = []
        for q in o.get("anchors", []):
            x = self.find_surface(q)
            if x is not None and x not in ps:
                ps.append(x)
        for q in o.get("targets", []):
            x = self.find(q)
            if x is not None and x not in ps:
                ps.append(x)
        if len(ps) < 2:
            return
        base = ps[0]
        for x in ps[1:]:
            base = self.merge(base, x)
        self.say("  merge %d manh" % len(ps))

    def merge(self, a, b):
        """Gop hai manh. Chi bo MAT CAT TIEP GIAP (ma nhat cat co dien tich hai ben khop nhau nhat): hai nem sat truc cung
        cham ca 3 mat phang, bo het ma chung -> thung, gop that bai -> giu ca mat cat giua (dia chia 3 ra 6 ranh, 2026-10-05)."""
        def area(t, i):
            return float(t.face_areas()[t.cap == i].sum())
        shared = sorted(set(np.unique(a.tm.cap[a.tm.cap >= 0]).tolist()) & set(np.unique(b.tm.cap[b.tm.cap >= 0]).tolist()),
                        key=lambda i: -min(area(a.tm, i), area(b.tm, i)))
        tries = [[i] for i in shared[:2]] + [None]
        t = None
        for ids in tries:
            for tr in (1e-5, 1e-3, 5e-3):
                c = a.tm.merge_with(b.tm, cut_ids=ids, tol_rel=tr)
                if c.is_closed():
                    t = c
                    break
            if t is not None:
                break
        if t is None:
            t = a.tm.merge_with(b.tm)
        if not t.is_closed():                        # nap khong khop -> giu hai vo trong mot mesh
            t = TM(np.concatenate([a.tm.V, b.tm.V]), np.concatenate([a.tm.F, b.tm.F + len(a.tm.V)]),
                   np.concatenate([a.tm.col, b.tm.col]), np.concatenate([a.tm.cap, b.tm.cap]))
        n = Piece(t)
        n.kind, n.color, n.src = a.kind or b.kind, a.color or b.color, a.src
        i = self.pieces.index(a)
        self.pieces[i] = n
        self.pieces.remove(b)
        return n

    def find_surface(self, q):
        """Manh co BE MAT gan q nhat (q la diem neo nam tren mat manh) - khong dung kiem tra trong/ngoai: tam
        mu non rong nam lot trong dau, chon theo chua diem se to nham dau (meo phu thuy 2026-10-02)."""
        q = np.asarray(q, dtype=np.float64)
        return min(self.pieces, key=lambda p: p.tm.dist(q)) if self.pieces else None

    def op_color(self, o):
        p = self._target(o, solid_only=False)
        p.color = std.resolve_color(o["color"])

    def op_kind(self, o):
        p = self._target(o, solid_only=False)
        p.kind = o["kind"].upper()

    def op_remesh(self, o):
        """Dung lai luoi manh bang voxel (nut "Mesh lai manh" o panel ghi): het vat mong / mat loi."""
        p = self._target(o, solid_only=False)
        if p is None:
            return
        # tam mong: lam day truoc khi voxel, khong thi thung lo (prep.rebuild, 2026-10-07)
        t2 = bl.voxel_rebuild(p.tm, voxel=o["voxel"]) if o.get("voxel") else prep.rebuild(p.tm, "mesh lai", log=self.say)
        if t2 is None:
            self.say("  !! mesh lai that bai")
            return
        n = Piece(t2)
        n.kind, n.color, n.src, n.parent = p.kind, p.color, p.src, p.parent
        self.pieces[self.pieces.index(p)] = n
        self.say("  mesh lai: %d -> %d mat" % (len(p.tm.F), len(t2.F)))

    def op_trim(self, o):
        """SUA PART XAU / cat phan du (wc/trim.repair - Claude "trim" o buoc xem ca model, nut "Sua part xau"): cat vat /
        kim / gai mong hon han than chinh + va kin, khong dat thi mesh lai tu than chinh. Sua khong dat -> an."""
        p = self._target(o, solid_only=False)
        if p is None:
            return
        from . import trim as TR
        t2, msg, lvl = TR.repair(p.tm, self.model_size)
        if lvl in ("cat", "mesh lai"):
            n = Piece(t2)
            n.kind, n.color, n.src, n.parent, n.hidden = p.kind, p.color, p.src, p.parent, p.hidden
            self.pieces[self.pieces.index(p)] = n
            self.say("  sua part xau: %s" % msg)
        elif lvl == "xau":
            p.hidden = "xấu: " + msg
            self.say("  sua part xau khong dat -> an: %s" % msg)

    def op_hide(self, o):
        """AN part (xau / khong ro la gi): van giu trong canh nhung khong xuat FBX; nguoi dung bat lai o panel."""
        p = self._target(o, solid_only=False)
        if p is not None:
            p.hidden = o.get("why") or "ẩn"

    def op_show(self, o):
        p = self._target(o, solid_only=False)
        if p is not None:
            p.hidden = ""

    def op_shell(self, o):
        """Tach VO rong + dung phan ben trong (nut "Tach vo + dung ben trong", wc/shell.py): mu dac up len than ->
        vo mu rong + dau (mat + long mu) + than cat o co."""
        from . import shell
        shell.op_shell(self, o)

    def op_drop(self, o):
        p = self._target(o, solid_only=False)
        self.pieces.remove(p)

    def op_decal(self, o):
        ci = self.color_index(o["color"]) if o.get("color") else None
        p = self.find_color(o["target"], [ci]) if ci is not None else self.find(o["target"], solid_only=True)
        if p is None:
            self.say("  !! decal: khong manh nao co mau %s" % o.get("color"))
            return
        reg = self._region_near(p, np.asarray(o["target"], dtype=np.float64), ci)
        if reg is None:
            self.say("  !! decal: khong thay vung mau %s gan %s" % (o.get("color"), o["target"]))
            return
        self._make_decal(p, reg)

    def op_part(self, o):
        """Tach mot BO PHAN theo vung mau (mu, mom, giay, tui) bang MAT PHANG khop duong bien mau, roi
        tinh chinh (dich +-, nghieng <= 20 do) cho it mat sai mau nhat ve hai phia."""
        cols = o["color"] if isinstance(o["color"], list) else [o["color"]]
        cis = [self.color_index(c) for c in cols]
        p = self.find_color(o["target"], cis)
        if p is None:
            self.say("  !! part: khong manh nao co mau %s" % cols)
            return
        t = p.tm
        adj = self._face_adj(t)
        ar = t.face_areas()
        C = t.face_centers()
        inset = np.isin(real_col(t.col), cis) & (t.cap < 0)
        if not inset.any():
            self.say("  !! part: manh khong co mau %s" % cols)
            return
        q = np.asarray(o["target"], dtype=np.float64)
        cand = np.where(inset)[0]
        s0 = int(cand[np.argmin(((C[cand] - q) ** 2).sum(1))])
        mask = np.zeros(len(t.F), bool)
        st = [s0]
        mask[s0] = True
        while st:
            f = st.pop()
            for g in adj[f]:
                if inset[g] and not mask[g]:
                    mask[g] = True
                    st.append(g)
        # lap lo trong vung (dom mau khac nam gon trong vung)
        rest = ~mask
        seen = np.zeros(len(t.F), bool)
        comps = []
        for s in np.where(rest)[0]:
            if seen[s]:
                continue
            comp, st = [], [s]
            seen[s] = True
            while st:
                f = st.pop()
                comp.append(f)
                for g in adj[f]:
                    if rest[g] and not seen[g]:
                        seen[g] = True
                        st.append(g)
            comps.append(np.array(comp))
        if comps:
            big = max(comps, key=lambda c: ar[c].sum())
            for c in comps:
                if c is not big and ar[c].sum() < 0.5 * ar[mask].sum():
                    mask[c] = True
        ef, _ = t.edge_faces()
        E, _ = t.edges()
        ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
        bd = ok.copy()
        bd[ok] = mask[ef[ok, 0]] != mask[ef[ok, 1]]
        notcap = ok.copy()
        notcap[ok] = (t.cap[ef[ok, 0]] < 0) & (t.cap[ef[ok, 1]] < 0)
        if (bd & notcap).sum() >= 6:
            bd = bd & notcap                    # chi bien mau that, khong tinh mep nap cua nhat cat truoc
        if not bd.any():
            self.say("  !! part: vung mau phu ca manh - khong co bien de cat")
            return
        pts = t.V[np.unique(E[bd].ravel())]
        c = pts.mean(0)
        w_, v_ = np.linalg.eigh(np.cov((pts - c).T))
        n = v_[:, 0]
        rc = (C[mask] * ar[mask, None]).sum(0) / ar[mask].sum()
        if (rc - c) @ n < 0:
            n = -n
        rad = float(np.sqrt(((pts - c) ** 2).sum(1)).max())
        near = np.sqrt(((C - c) ** 2).sum(1)) < 1.6 * rad
        # tinh chinh: mat phang lam sai mau it nhat (dien tich mat vung nam phia duoi + mat ngoai nam phia tren)
        u, w = basis_of(n)
        best = None
        for a in (0, 8, -8, 16, -16):
            for b in (0, 8, -8, 16, -16):
                nn = unit(n * math.cos(math.radians(abs(a) + abs(b))) + u * math.sin(math.radians(a))
                          + w * math.sin(math.radians(b)))
                for off in np.linspace(-0.35 * rad, 0.35 * rad, 9):
                    cc = c + n * off
                    sd = (C[near] - cc) @ nn
                    bad = ar[near][(mask[near] & (sd < 0)) | (~mask[near] & (sd > 0))].sum()
                    sc = bad * (1 + 0.1 * abs(off) / rad)
                    if best is None or sc < best[0]:
                        best = (sc, cc, nn)
        _, cc, nn = best
        cc = cc + nn * float(o.get("offset", 0.0))
        mis = best[0] / max(ar[near].sum(), 1e-9)
        if mis > float(o.get("max_mis", 0.25)):
            self.say("  !! part %s: mat phang tot nhat van sai mau %.0f%% - KHONG cat. Bien mau khong phang: "
                     "dung 'cut' voi mat phang tu chon (hoac them \"max_mis\": 0.5 de ep)" % (o.get("label", cols), 100 * mis))
            self.warn.append("part %s bi bo (sai mau %.0f%%)" % (o.get("label", cols), 100 * mis))
            return
        if os.environ.get("WC_DEBUG"):
            self.say("    bien: %d diem, tam %s, ban kinh %.2f; PCA n=%s -> chon c=%s n=%s" % (
                len(pts), np.round(c, 2), rad, np.round(n, 2), np.round(cc, 2), np.round(nn, 2)))
        cid = self.next_cut()
        res = t.plane_cut(cc, nn, cid, mode="local", q=cc)
        if not res:
            res = t.plane_cut(c, n, cid, mode="local", q=c)
        if not res:
            self.say("  !! part %s: mat phang khong tach duoc" % o.get("label", cols))
            return
        new = [Piece(x) for x in res]
        self.replace(p, new, cid)
        self.say("  part %-12s -> %d manh %s (sai mau %.1f%%)" % (
            o.get("label", ""), len(new), [len(x.tm.F) for x in new], 100 * best[0] / max(ar[near].sum(), 1e-9)))

    # ------------------------------------------------------------ vung mau / mieng dan
    def _face_adj(self, t):
        if "adj" not in t.meta:
            ef, cnt = t.edge_faces()
            ok = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
            adj = [[] for _ in range(len(t.F))]
            for a, b in ef[ok]:
                adj[a].append(b)
                adj[b].append(a)
            t.meta["adj"] = adj
        return t.meta["adj"]

    def _regions(self, p):
        """Vung lien thong cung mau tren mat that (khong tinh nap)."""
        t = p.tm
        adj = self._face_adj(t)
        seen = np.zeros(len(t.F), bool)
        regs = []
        for s in range(len(t.F)):
            if seen[s] or t.cap[s] >= 0 or t.col[s] < 0:
                seen[s] = True
                continue
            c = t.col[s]
            st, comp = [s], []
            seen[s] = True
            while st:
                f = st.pop()
                comp.append(f)
                for g in adj[f]:
                    if not seen[g] and t.cap[g] < 0 and t.col[g] == c:
                        seen[g] = True
                        st.append(g)
            regs.append((int(c), np.array(comp)))
        return regs

    def _region_near(self, p, q, ci):
        t = p.tm
        C = t.face_centers()
        best = None
        for c, comp in self._regions(p):
            if ci is not None and c != ci:
                continue
            d = float(np.sqrt(((C[comp] - q) ** 2).sum(1)).min())
            if best is None or d < best[0]:
                best = (d, c, comp)
        return None if best is None else (best[1], best[2])

    def _make_decal(self, host, reg, t_off=DECAL_T):
        """Vung mau tren manh -> mieng dan kin mong (mat tren noi len, mat duoi chim nhe, thanh ben)."""
        c, comp = reg
        t = host.tm
        F = t.F[comp]
        used, inv = np.unique(F.ravel(), return_inverse=True)
        Fl = inv.reshape(-1, 3)
        V = t.V[used].copy()
        fn = np.cross(V[Fl[:, 1]] - V[Fl[:, 0]], V[Fl[:, 2]] - V[Fl[:, 0]])
        vn = np.zeros_like(V)
        for j in range(3):
            np.add.at(vn, Fl[:, j], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        # canh bien cua vung (chi 1 mat trong vung)
        e = np.concatenate([Fl[:, [0, 1]], Fl[:, [1, 2]], Fl[:, [2, 0]]])
        key = collections.Counter(tuple(sorted(x)) for x in e.tolist())
        bnd = [tuple(x) for x in e.tolist() if key[tuple(sorted(x))] == 1]
        # lam min duong bien (vung voxel co rang cua): Laplace 1 chieu doc bien, giu tren mat
        nb = collections.defaultdict(list)
        for a, b in bnd:
            nb[a].append(b)
            nb[b].append(a)
        for _ in range(6):
            newV = V.copy()
            for a, ns in nb.items():
                if len(ns) == 2:
                    newV[a] = 0.5 * V[a] + 0.25 * (V[ns[0]] + V[ns[1]])
            V = newV
        n = len(V)
        top = V + vn * t_off
        bot = V - vn * t_off * 0.35
        Vd = np.concatenate([top, bot])
        Fd = [Fl, Fl[:, ::-1] + n]
        side = []
        for a, b in bnd:                     # (a,b) theo chieu mat trong vung -> thanh ben huong ra ngoai
            side += [(b, a, a + n), (b, a + n, b + n)]
        Fd.append(np.array(side, dtype=np.int64).reshape(-1, 3))
        Fd = np.concatenate(Fd)
        d = TM(Vd, Fd, np.full(len(Fd), c), np.full(len(Fd), -1))
        dp = Piece(d, src=host.src)
        dp.decal = True
        dp.kind = "D" if d.size < 0.12 * self.model_size else None     # quang mat to: de luat co quyet S/D
        dp.host = host.id
        dp.color = self.names[c]
        self.pieces.append(dp)
        host.tm.col[comp] = -2 - c          # mat duoi mieng dan: nho mau goc, khong tinh vao mau manh
        return dp

    def auto_decals(self, label="[tu dong]", max_model=None):
        """Vung mau khac mau chinh cua manh: nho -> D (mat, mui, nut); vet nhieu -> to theo manh;
        vung to -> giu, bao (nen them nhat cat)."""
        made, warn = 0, []
        for p in list(self.pieces):
            if p.decal:
                continue
            t = p.tm
            ar = t.face_areas()
            adj = self._face_adj(t)
            regs = self._regions(p)
            if not regs:
                continue
            tot = collections.Counter()
            for c, comp in regs:
                tot[c] += ar[comp].sum()
            main = tot.most_common(1)[0][0]
            parea = ar[t.cap < 0].sum()
            for c, comp in regs:
                if c == main:
                    continue
                a = ar[comp].sum()
                touches_cap = any(t.cap[g] >= 0 for f in comp for g in adj[f])
                if touches_cap or a < DECAL_MIN_MODEL * self.total_area or self.contrast(c, main) < DECAL_DE                         or roundness(t, comp, ar) < DECAL_ROUND:
                    t.col[comp] = main                    # vet nhieu / cung mau son -> to theo manh
                elif (a <= (max_model or DECAL_MAX_MODEL) * self.total_area and a <= DECAL_MAX_PIECE * parea) or                         (max_model and a <= PATCH_MAX * self.total_area and a <= DECAL_MAX_PIECE * parea
                         and flatness(t, comp) <= PATCH_FLAT):
                    self._make_decal(p, (c, comp))
                    made += 1
                else:
                    warn.append((p, self.names[c], a / max(parea, 1e-9)))
        self.say("%s %d mieng dan D tu vung mau nho" % (label, made))
        for p, c, f in warn:
            self.say("  luu y: manh #%d con vung %s %.0f%% - nen them nhat cat" % (p.id, c.replace("Color_", ""), 100 * f))

    def contrast(self, a, b):
        """dE2000 giua mau danh nghia hai slot (Orange-Yellow ~ thap, Orange-Black/Cream cao)."""
        from . import color
        la = color._lab(np.array([std.nominal_lin(self.names[a])]))
        lb = color._lab(np.array([std.nominal_lin(self.names[b])]))
        return float(color.de2000(la, lb, 1.0)[0, 0])

    # ------------------------------------------------------------ mau / loai / so manh
    def piece_color(self, p):
        if p.color:
            return p.color
        t = p.tm
        ar = t.face_areas()
        ok = (t.cap < 0) & (t.col >= 0)
        if not ok.any():
            ok = t.col >= 0
        if not ok.any():
            return std.mat_name(25, "Gray")
        w = np.bincount(t.col[ok], weights=ar[ok], minlength=len(self.names))
        return self.names[int(w.argmax())]

    def kinds(self):
        solid = [p for p in self.pieces]
        dims = [p.dims() for p in solid]
        closed = [p.tm.is_closed() for p in solid]
        auto = std.auto_kinds(dims, closed, side=self.model_size)
        out = {}
        for p, k in zip(solid, auto):
            out[p.id] = p.kind or ("D" if p.decal else k)
        return out

    def balance(self, nmin, nmax):
        """KHONG tu cat / gop de dat so manh (nguoi dung 2026-10-05: "chi nen tach bo phan" - truoc day thieu manh thi
        bo doi khoi to nhat -> dia nuong bi chia 4). Chi ghi chu so manh lech [nmin, nmax]."""
        kinds = self.kinds()
        k = sum(1 for p in self.pieces if kinds[p.id] != "D")
        if k < nmin:
            self.say("  luu y: %d manh S/M < %d (khong tu cat - tu chia bo phan o panel)" % (k, nmin))
        elif k > nmax:
            self.say("  luu y: %d manh S/M > %d (giu nguyen cac bo phan)" % (k, nmax))

    def neighbors(self, p, cands):
        tol = 0.02 * self.model_size
        kd = KDTree(len(p.tm.V))
        for i, v in enumerate(p.tm.V):
            kd.insert(Vector(v), i)
        kd.balance()
        lo, hi = p.tm.bbox()
        out = []
        for x in cands:
            if x is p:
                continue
            xl, xh = x.tm.bbox()
            if np.any(xl > hi + tol) or np.any(xh < lo - tol):
                continue
            step = max(1, len(x.tm.V) // 400)
            if any(kd.find(Vector(v))[2] < tol for v in x.tm.V[::step]):
                out.append(x)
        return out

    def review(self, kinds):
        """Canh bao cho buoc lap ke hoach tiep: manh S/M vun (lat cat thua), manh lan nhieu mau."""
        for p in self.pieces:
            if kinds[p.id] == "D":
                continue
            lo, hi = p.tm.bbox()
            ext = np.sort(hi - lo)
            if ext[2] < 0.05 * self.model_size or (ext[0] < 0.12 * ext[2] and ext[2] < 0.3 * self.model_size):
                p.cache["warn"] = "vun/mong"
            t = p.tm
            ar = t.face_areas()
            ok = (t.cap < 0) & (t.col >= 0)
            if ok.any():
                w = np.bincount(t.col[ok], weights=ar[ok], minlength=len(self.names))
                share = w.max() / max(w.sum(), 1e-12)
                if share < 0.7:
                    second = self.names[int(np.argsort(w)[-2])].replace("Color_", "").replace("_mat", "")
                    p.cache["warn"] = (p.cache.get("warn", "") + " lan mau %d%% %s" % (100 - 100 * share, second)).strip()

    def assign_hosts(self, kinds):
        """D bam vao manh S/M co be mat gan nhat."""
        solid = [p for p in self.pieces if kinds[p.id] != "D"]
        for p in self.pieces:
            if kinds[p.id] != "D" or not solid:
                continue
            if p.host and any(s.id == p.host for s in solid):
                continue
            c = p.tm.centroid()
            p.host = min(solid, key=lambda s: s.tm.dist(c)).id


def dry_run(work_dir, plan):
    """CHAY THU ke hoach (chi hinh hoc, khong render, khong ghi file) de panel xem truoc dung manh + mat phang that
    cua tung nhat (nhat sau nham vao manh do nhat truoc cat ra). Tra ve {chi so thao tac: [(planes, TM)]}."""
    tms, names, meta = prep.load_prep(work_dir)
    R = Run(tms, names, verbose=False)
    R.trace = {}
    if plan.get("features", True):
        R.auto_decals(label="[chi tiet] truoc khi cat", max_model=FEATURE_MAX)
    for i, o in enumerate(plan.get("ops", [])):
        fn = getattr(R, "op_" + o.get("op", ""), None)
        if fn is None or o.get("skip") or o.get("paint"):
            continue
        R._cur = i
        try:
            if o.get("op") not in ("cut", "merge"):
                p = R._target(o, solid_only=o.get("op") not in ("color", "kind", "drop"))
                if p is not None:
                    R.trace[i] = [([], p.tm)]                 # mac dinh: chi to manh dich
            fn(o)
        except Exception as e:
            R.say("  !! chay thu %d: %s" % (i, e))
        R._cur = None
    return R.trace


TINY = 0.025                 # xoa manh co canh dai nhat < 2.5% co model (li ti, khong nhin thay); 0 = tat


def execute(work_dir, plan_path, nmin=15, nmax=35, verbose=True, bevel=None, tiny=None):
    t0 = time.time()
    tms, names, meta = prep.load_prep(work_dir)
    plan = {"ops": []}
    if plan_path and os.path.exists(plan_path):
        with open(plan_path, encoding="utf-8") as fh:
            plan = json.load(fh)
    nmin = int(plan.get("min", nmin))
    nmax = int(plan.get("max", nmax))
    R = Run(tms, names, verbose)
    R.say("[cat] %d khoi ban dau, ke hoach %d thao tac" % (len(R.pieces), len(plan.get("ops", []))))
    if plan.get("features", True):
        R.auto_decals(label="[chi tiet] truoc khi cat", max_model=FEATURE_MAX)
    for i, o in enumerate(plan.get("ops", [])):
        fn = getattr(R, "op_" + o.get("op", ""), None)
        if o.get("skip"):                          # tat o panel (xem truoc ke hoach)
            R.say("[%d] bo qua (da tat): %s %s" % (i + 1, o.get("op"), o.get("label", "")))
            continue
        if fn is None:
            R.say("  !! thao tac la: %s" % o.get("op"))
            continue
        R.say("[%d] %s %s" % (i + 1, o["op"], o.get("label", "")))
        try:
            fn(o)
        except Exception as e:                     # mot thao tac hong khong lam do ca ke hoach
            import traceback
            traceback.print_exc()
            R.say("  !! loi: %s" % e)
    R.auto_decals()
    tn = float(plan.get("tiny", TINY) if tiny is None else tiny)
    if tn > 0:                                     # vat the li ti (nguoi dung 2026-10-05: "user kho nhin thay") -> xoa
        lim = tn * R.model_size
        small = [p for p in R.pieces if float((p.tm.V.max(0) - p.tm.V.min(0)).max()) < lim]
        if small:
            R.pieces = [p for p in R.pieces if p not in small]
            R.say("[don] xoa %d manh li ti (canh dai < %.2f = %.1f%% co model)" % (len(small), lim, 100 * tn))
    R.balance(nmin, nmax)
    kinds = R.kinds()
    R.assign_hosts(kinds)
    R.review(kinds)
    # chong lan giua cac khoi roi cua Tripo (2026-10-08): cat phan chim, gop manh chim sau (wc/overlap.py)
    if plan.get("overlap", True) and os.environ.get("WOOLCUT_OVERLAP", "1") != "0":
        from . import overlap as OV
        try:
            OV.resolve(R, kinds, log=R.say)
        except Exception as e:
            R.say("[chong lan] loi: %s" % e)
    # ---- xuat
    bpy.ops.wm.read_factory_settings(use_empty=True)
    coll = bpy.data.collections.new("WoolCut Parts")
    bpy.context.scene.collection.children.link(coll)
    order = sorted(R.pieces, key=lambda p: ({"M": 0, "S": 1, "D": 2}[kinds[p.id]], -p.tm.centroid()[2]))
    objs, rows = [], []
    name_of = {}
    bev = float(plan.get("bevel", BEVEL) if bevel is None else bevel)
    n_bev = 0
    for i, p in enumerate(order):
        nm = "P%02d" % (i + 1)
        name_of[p.id] = nm
    for p in order:
        nm = name_of[p.id]
        col = R.piece_color(p)
        tm_out = p.tm
        if (p.kind or kinds[p.id]) != "D":             # cat tia gai mong nho (wc/trim.py, 2026-10-08) - giu be mat con lai
            from . import trim as TR
            try:
                t_tr, msg = TR.trim(p.tm, R.model_size, max_comp=TR.AUTO_COMP)
                if msg and t_tr is not p.tm:
                    R.say("  [cat tia] %s: %s" % (nm, msg))
                    p.tm = tm_out = t_tr
            except Exception as e:
                R.say("  [cat tia] %s loi: %s" % (nm, e))
        if bev > 0 and (p.kind or kinds[p.id]) != "D" and (p.tm.cap >= 0).any():
            from . import fillet as FL
            tm_out = FL.fillet(p.tm, bev, log=R.say)        # bo cong bang hinh hoc moi (2026-10-05)
            n_bev += int(len(tm_out.F) != len(p.tm.F))
        ob = bl.object_from_tm(tm_out, nm, coll=coll, mat=bl.palette_material(col), per_face=False)
        uvmod.center_origin(ob)
        ob["wc_kind_auto"] = kinds[p.id]
        ob["wc_color"] = col
        look.apply_piece(ob, p.kind or kinds[p.id], col, unwrap=False)
        if p.kind:
            ob["wc_kind"] = p.kind
        if p.hidden:
            ob["wc_hidden"] = 1
            ob["wc_hidden_why"] = p.hidden
        if kinds[p.id] == "D" and p.host in name_of:
            ob["wc_host"] = name_of[p.host]
        objs.append(ob)
        lo, hi = p.tm.bbox()
        ar = p.tm.face_areas()
        real = np.where(p.tm.cap < 0, ar, 0)
        fi = int(real.argmax()) if real.max() > 0 else int(ar.argmax())
        rows.append(dict(name=nm, kind=kinds[p.id], color=col, faces=int(len(p.tm.F)), closed=p.tm.is_closed(),
                         size=round(float((hi - lo).max()) / R.model_size, 3), host=ob.get("wc_host"),
                         center=[round(float(x), 2) for x in p.tm.centroid()],
                         anchor=[float(x) for x in p.tm.face_centers()[fi]], warn=p.cache.get("warn", "")))
    if bev > 0:
        R.say("[bo cong] mep cat ban kinh %.2f: %d manh" % (bev, n_bev))
    # UV kieu bo goc cho M/S (xem len dan dung co mui; xuat se trai lai o co cuoi)
    uvmod.unwrap_v2([o for o in objs if (o.get("wc_kind") or o.get("wc_kind_auto")) != "D"], 2.148 * 8.2 / 10.0,
                    log=R.say)                     # UV kieu moi (2026-10-08) - xem trong canh dung nhu xuat toi uu
    out_blend = os.path.join(work_dir, "parts.blend")
    imgs = render.result_views(objs, work_dir)
    imgs.append(render.sheet(objs, os.path.join(work_dir, "parts_sheet.png"),
                             ["%s %s %s" % (r["name"], r["kind"], r["color"].replace("Color_", "").replace("_mat", "").split("_", 1)[-1])
                              for r in rows]))
    bpy.ops.wm.save_as_mainfile(filepath=out_blend, compress=True)
    cnt = collections.Counter(r["kind"] for r in rows)
    with open(os.path.join(work_dir, "parts.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(parts=rows, counts=cnt, log=R.log, warn=R.warn, min=nmin, max=nmax), fh, indent=1, ensure_ascii=False)
    print("[ket qua] %d manh: %d M, %d S, %d D; kin %d/%d; %d tam giac; %.1fs" % (
        len(rows), cnt["M"], cnt["S"], cnt["D"], sum(r["closed"] for r in rows), len(rows),
        sum(r["faces"] for r in rows), time.time() - t0))
    for r in rows:
        print("[part] %s | %s | %s | %.3f | %s | tam %s%s%s" % (
            r["name"], r["color"].replace("Color_", "").replace("_mat", ""), r["kind"], r["size"],
            "kin" if r["closed"] else "HO", r["center"], (" | tren " + r["host"]) if r.get("host") else "",
            (" | !! " + r["warn"]) if r.get("warn") else ""))
    for w in R.warn:
        print("[canh bao]", w)
    for p in imgs:
        print("[anh]", p)
    return out_blend
