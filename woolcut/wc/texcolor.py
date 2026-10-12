"""MAU THEO TEXTURE GOC (2026-10-12) - model co texture: mau moi manh = mau texture chiem nhieu dien tich nhat tren BE
MAT THAT cua manh (lay theo mat prep gan nhat), khong goi Claude.

Gau truc ve tranh (PandaPainter3dModel2): truoc lan Claude to mau mu / ao / ong quan deu Xanh troi, mom Trang, can co
Vang - dung texture; Claude to (luat 8-14 mau, bo phan cham nhau tuong phan, "mau tuoi nhu gau mau") doi mu sang Do,
mom Be, tay ao Xanh duong, can co Nau -> khac han ban goc. Claude chi nhin anh mau HIEN TAI, khong thay texture.
Sau tach sau, manh con mang mau manh cha (mot material) -> cung lay lai theo texture o day."""
import os
import numpy as np


def is_textured(work_dir):
    """Prep co > 1 mau texture (model Tripo co texture)."""
    import json
    p = os.path.join(work_dir, "prep.json")
    if not os.path.exists(p):
        return False
    return len(json.load(open(p, encoding="utf-8")).get("names", [])) > 1


class Index:
    """Mat prep (moi khoi) + mau tung mat, de tra mau texture tai mot diem."""

    def __init__(self, work_dir):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        from . import prep
        tms, names, meta = prep.load_prep(work_dir)
        V, F, C, off = [], [], [], 0
        for t in tms:
            V.append(t.V)
            F.append(t.F + off)
            C.append(np.asarray(t.col))
            off += len(t.V)
        self.V = np.concatenate(V)
        self.F = np.concatenate(F)
        self.col = np.concatenate(C)
        self.names = list(names)
        self.size = float((self.V.max(0) - self.V.min(0)).max())
        self.bvh = BVHTree.FromPolygons([Vector(v) for v in self.V], [tuple(int(i) for i in f) for f in self.F],
                                        all_triangles=True)

    def color_of(self, V, F, skip=None, max_rel=0.03):
        """Mau texture cua manh (V the gioi, F tam giac): gom dien tich theo mau mat prep gan nhat cua tung mat (bo mat
        `skip` - mat nap / mat tiep xuc - va mat xa be mat prep > max_rel co model). -> (ten mau, ti le) hoac (None, 0)."""
        from mathutils import Vector
        V, F = np.asarray(V, float), np.asarray(F, np.int64)
        if not len(F):
            return None, 0.0
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        nrm = np.cross(b - a, c - a)
        ar = 0.5 * np.linalg.norm(nrm, axis=1)
        nrm = nrm / np.maximum(2 * ar[:, None], 1e-30)
        cen = (a + b + c) / 3.0
        keep = np.ones(len(F), bool) if skip is None else ~np.asarray(skip, bool)
        lim = max_rel * self.size
        w = np.zeros(len(self.names))
        for i in np.where(keep)[0]:
            hit = self.bvh.find_nearest(Vector(cen[i]), lim)
            if hit[0] is None or float(np.dot(nrm[i], hit[1][:])) < 0.3:     # nap / mat bo cong ben trong: bo
                continue
            ci = int(self.col[hit[2]])
            if 0 <= ci < len(w):
                w[ci] += ar[i]
        if w.sum() <= 0:
            return None, 0.0
        k = int(w.argmax())
        return self.names[k], float(w[k] / w.sum())
