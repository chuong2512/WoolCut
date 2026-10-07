"""THU VIEN DECOR + GAN DECOR (nguoi dung 2026-10-05): 27 decor dung san cua nguoi dung (D:\\BlenderTool\\Deco\\DeCo.fbx,
UV tren Deco_Texture) + bo khoi don gian tu dung (mat tron, cham sang, ma hong, mui, mieng cuoi, nut...). Claude xem anh
cac manh da tach -> chon decor + manh + diem + co (planner.decor) -> addon dat len be mat (place_matrix) thanh manh D con.

Quy uoc mesh trong thu vien (data/decor/library.blend, object "dec_<id>"): tam hop bao o goc, canh dai nhat = 1, MAT
TRUOC nhin -Y (mat sau o +Y ap vao be mat), dau decor huong +Z. mode "multi" = giu UV nhieu mau cua decor; "tint" = UV
don ve mot diem mau (doi mau duoc)."""
import os, json, math
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(HERE, "data", "decor")
LIB_BLEND = os.path.join(LIB_DIR, "library.blend")
CATALOG = os.path.join(LIB_DIR, "catalog.json")
SRC_FBX = r"D:\BlenderTool\Deco\DeCo.fbx"

# ---- 27 decor cua nguoi dung (DeCo.fbx) - ten, mo ta cho Claude, nhom, che do mau, mau mac dinh
USER_DECOR = {
    1: ("kem ốc quế", "ice cream cone", "food", "multi", None),
    2: ("cupcake anh đào", "cupcake with cherry", "food", "multi", None),
    3: ("dâu tây", "strawberry", "food", "multi", None),
    4: ("hoa xanh có cuống", "blue flower with stem and leaf", "nature", "multi", None),
    5: ("mèo cam", "small sitting orange cat", "character", "multi", None),
    6: ("bánh quy", "chocolate chip cookie", "food", "multi", None),
    7: ("pizza", "pizza slice", "food", "multi", None),
    8: ("kẹo", "wrapped candy", "food", "tint", "Pink"),
    9: ("mầm cây trong chậu", "sprout in a small pot", "nature", "multi", None),
    10: ("nấm", "mushroom", "nature", "multi", None),
    11: ("trứng ốp", "fried egg", "food", "multi", None),
    12: ("tim đỏ", "heart", "symbol", "tint", "Red"),
    13: ("mặt trời cười", "smiling sun", "symbol", "multi", None),
    14: ("mũi tên", "arrow sign (purple outline, white inside)", "symbol", "multi", None),
    15: ("tim hồng", "puffy heart", "symbol", "tint", "Pink"),
    16: ("mặt cười tím", "smiley face swirl", "symbol", "tint", "Purple"),
    17: ("trứng ốp xanh", "green fried egg / blob flower", "nature", "multi", None),
    18: ("trăng khuyết", "crescent moon", "symbol", "tint", "Orange"),
    19: ("nốt nhạc đôi", "double music note", "symbol", "tint", "TurquoiseMint"),
    20: ("thẻ chữ nhật", "rounded rectangle tag / plaque", "misc", "tint", "Pink"),
    21: ("hoa vàng nhị cam", "yellow flower with orange center", "nature", "multi", None),
    22: ("nốt nhạc", "music note", "symbol", "tint", "Red"),
    23: ("nút áo dấu X", "button with an X", "misc", "multi", None),
    24: ("que ghim", "pin / stick with a ball end", "misc", "tint", "Green"),
    25: ("hoa 5 cánh", "five-petal yellow flower", "nature", "multi", None),
    26: ("lấp lánh", "4-point sparkle", "symbol", "tint", "White"),
    27: ("ngôi sao", "star", "symbol", "tint", "Green"),
}

# ---- bo khoi don gian (tu dung) - (ten, mo ta, nhom, mau mac dinh)
BASIC = {
    "eye_round": ("mắt tròn", "round black bead eye (dome)", "face", "Black"),
    "eye_oval": ("mắt bầu dục", "tall oval eye", "face", "Black"),
    "eye_shine": ("chấm sáng mắt", "tiny white highlight dot placed on the upper part of an eye", "face", "White"),
    "eye_closed": ("mắt nhắm (^)", "closed happy eye arc", "face", "Black"),
    "eyebrow": ("lông mày", "short rounded eyebrow bar", "face", "Black"),
    "blush": ("má hồng", "flat oval blush cheek", "face", "Pink"),
    "nose_round": ("mũi tròn", "round nose ball", "face", "Black"),
    "nose_tri": ("mũi tam giác", "rounded triangle nose (pointing down)", "face", "Black"),
    "mouth_smile": ("miệng cười", "smile arc", "face", "Black"),
    "mouth_cat": ("miệng mèo (w)", "cat mouth w-shape", "face", "Black"),
    "mouth_open": ("miệng há", "open mouth (half oval)", "face", "Red"),
    "whisker": ("ria", "thin whisker bar", "face", "Black"),
    "dot": ("chấm tròn", "round dot / bead / rivet", "basic", "White"),
    "button": ("nút tròn", "round flat button", "basic", "Yellow"),
    "disc": ("đĩa tròn dẹt", "flat round patch / spot", "basic", "White"),
}


def catalog():
    with open(CATALOG, encoding="utf-8") as fh:
        return json.load(fh)


def catalog_text(cat):
    """Danh sach decor cho Claude (id, ten, nhom, mau)."""
    rows = []
    for d in cat:
        rows.append("  %-11s %-22s [%s] %s%s" % (d["id"], d["vi"], d["group"], d["en"],
                                                (" | doi mau duoc, mac dinh %s" % d["color"]) if d["mode"] == "tint"
                                                else " | nhieu mau co dinh"))
    return "\n".join(rows)


# ------------------------------------------------------------------ dung thu vien (chay trong Blender headless)
def _normalize(me):
    """Tam hop bao ve goc, canh dai nhat = 1."""
    V = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    lo, hi = V.min(0), V.max(0)
    V = (V - (lo + hi) / 2) / float((hi - lo).max() or 1.0)
    me.vertices.foreach_set("co", V.ravel())
    me.update()
    return (hi - lo) / float((hi - lo).max() or 1.0)


def _basic_mesh(key):
    """Dung khoi don gian: mat truoc -Y, dau +Z, bo tron bang Subdivision."""
    import bpy, bmesh
    from mathutils import Matrix
    bm = bmesh.new()
    sub = 0
    if key in ("eye_round", "eye_shine", "dot", "nose_round", "eye_oval", "blush", "disc"):
        bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=0.5)
        sc = {"eye_round": (1, 0.45, 1), "eye_shine": (1, 0.5, 1), "dot": (1, 0.6, 1), "nose_round": (1.2, 0.8, 0.9),
              "eye_oval": (0.75, 0.42, 1.1), "blush": (1.6, 0.18, 1.0), "disc": (1, 0.16, 1)}[key]
        bmesh.ops.scale(bm, vec=sc, verts=bm.verts)
    elif key == "button":
        bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.5, radius2=0.5, depth=0.22)
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90), 3, "X"), verts=bm.verts)
        sub = 1
    elif key == "nose_tri":
        verts = [bm.verts.new(p) for p in [(-0.5, -0.2, 0.3), (0.5, -0.2, 0.3), (0, -0.2, -0.45),
                                            (-0.5, 0.2, 0.3), (0.5, 0.2, 0.3), (0, 0.2, -0.45)]]
        for f in ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)):
            bm.faces.new([verts[i] for i in f])
        sub = 2
    elif key in ("eyebrow", "whisker"):
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(1.0, 0.3, 0.28) if key == "eyebrow" else (1.0, 0.1, 0.1), verts=bm.verts)
        sub = 2
    elif key in ("mouth_smile", "eye_closed", "mouth_cat", "mouth_open"):
        def arc(cx, r, a0, a1, tube, n=18):
            rings = []
            for i in range(n + 1):
                a = a0 + (a1 - a0) * i / n
                c = np.array([cx + r * math.cos(a), 0.0, r * math.sin(a)])
                t = np.array([-math.sin(a), 0.0, math.cos(a)])
                nrm = np.cross(t, [0, 1.0, 0])
                ring = []
                for j in range(8):
                    b = 2 * math.pi * j / 8
                    p = c + tube * (math.cos(b) * nrm + math.sin(b) * np.array([0, 1.0, 0]))
                    ring.append(bm.verts.new(p.tolist()))
                rings.append(ring)
            for i in range(n):
                for j in range(8):
                    bm.faces.new([rings[i][j], rings[i][(j + 1) % 8], rings[i + 1][(j + 1) % 8], rings[i + 1][j]])
            bm.faces.new(list(reversed(rings[0])))
            bm.faces.new(rings[-1])
        if key == "mouth_smile":
            arc(0, 0.5, math.radians(200), math.radians(340), 0.07)
        elif key == "eye_closed":
            arc(0, 0.5, math.radians(20), math.radians(160), 0.09)
        elif key == "mouth_cat":
            arc(-0.25, 0.25, math.radians(180), math.radians(360), 0.06, 12)
            arc(0.25, 0.25, math.radians(180), math.radians(360), 0.06, 12)
        else:                                            # mieng ha: nua elip dac
            bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=0.5)
            bmesh.ops.scale(bm, vec=(1.0, 0.3, 0.7), verts=bm.verts)
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0),
                                   plane_no=(0, 0, 1), clear_outer=True)
            bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
    me = bpy.data.meshes.new("dec_" + key)
    bm.to_mesh(me)
    bm.free()
    if sub:
        ob = bpy.data.objects.new("_tmp", me)
        bpy.context.scene.collection.objects.link(ob)
        m = ob.modifiers.new("s", "SUBSURF")
        m.levels = sub
        dg = bpy.context.evaluated_depsgraph_get()
        me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.meshes.remove(me)
        me = me2
        me.name = "dec_" + key
    for p in me.polygons:
        p.use_smooth = True
    if not me.uv_layers:
        me.uv_layers.new(name="map1")
    return me


def build_library():
    """DeCo.fbx + khoi don gian -> data/decor/library.blend + catalog.json. Chay 1 lan (run.py decor-lib)."""
    import bpy
    os.makedirs(LIB_DIR, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=SRC_FBX)
    bpy.context.view_layer.update()
    out, cat = [], []
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        num = int(o.name.split("_")[-1])
        if num not in USER_DECOR:
            continue
        vi, en, grp, mode, col = USER_DECOR[num]
        me = o.data.copy()
        me.transform(o.matrix_world)
        while len(me.uv_layers) > 1:
            me.uv_layers.remove(me.uv_layers[-1])
        if me.uv_layers:
            me.uv_layers[0].name = "map1"
            uv = np.empty(len(me.loops) * 2)
            me.uv_layers[0].data.foreach_get("uv", uv)
            me.uv_layers[0].data.foreach_set("uv", np.mod(uv, 1.0))      # D_Oai_15 UV 11.9 -> trong [0,1]
        me.materials.clear()
        dims = _normalize(me)
        me.name = "dec_oai%02d" % num
        out.append(bpy.data.objects.new("dec_oai%02d" % num, me))
        cat.append(dict(id="oai%02d" % num, vi=vi, en=en, group=grp, mode=mode, color=col,
                        dims=[round(float(x), 3) for x in dims], src="DeCo.fbx D_Oai_%d" % num))
    for key, (vi, en, grp, col) in BASIC.items():
        me = _basic_mesh(key)
        dims = _normalize(me)
        out.append(bpy.data.objects.new("dec_" + key, me))
        cat.append(dict(id=key, vi=vi, en=en, group=grp, mode="tint", color=col,
                        dims=[round(float(x), 3) for x in dims], src="woolcut"))
    for o in out:
        bpy.context.scene.collection.objects.link(o)
    bpy.data.libraries.write(LIB_BLEND, set(out), fake_user=True)
    order = {"face": 0, "basic": 1, "symbol": 2, "nature": 3, "food": 4, "character": 5, "misc": 6}
    cat.sort(key=lambda d: (order.get(d["group"], 9), d["id"]))
    with open(CATALOG, "w", encoding="utf-8") as fh:
        json.dump(cat, fh, ensure_ascii=False, indent=1)
    render_thumbs(cat)
    print("[decor] thu vien %d decor -> %s" % (len(cat), LIB_BLEND))
    return cat


THUMBS = os.path.join(LIB_DIR, "thumbs")
SHEET = os.path.join(LIB_DIR, "catalog.png")


def render_thumbs(cat):
    """Anh tung decor (icon panel) + bang tong (Claude xem)."""
    import bpy
    from mathutils import Vector
    from . import render, look, std
    os.makedirs(THUMBS, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    by = {}
    for path in (LIB_BLEND, CUSTOM_BLEND):
        if os.path.exists(path):
            with bpy.data.libraries.load(path, link=False) as (src, dst):
                dst.objects = list(src.objects)
            by.update({o.name: o for o in dst.objects if o is not None})
    mat = look.deco_material()
    cam = render.setup(160)
    paths, labels = [], []
    for c in cat:
        o = by.get("dec_" + c["id"])
        if o is None:
            continue
        bpy.context.scene.collection.objects.link(o)
        o.data.materials.clear()
        o.data.materials.append(mat)
        if c["mode"] == "tint":
            u, v, _ = look.deco_point(std.resolve_color(c["color"]))
            look.deco_uv(o.data, u, v)
        for x in bpy.context.scene.objects:
            if x.type == "MESH":
                x.hide_render = x is not o
        d = np.array((0.35, -1.0, 0.3))
        d /= np.linalg.norm(d)
        cam.location = Vector(d * 6)
        cam.rotation_euler = Vector(-d).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = 1.35
        p = os.path.join(THUMBS, c["id"] + ".png")
        bpy.context.scene.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p)
        labels.append(c["id"])
    render.compose(paths, labels, SHEET, cols=8, tile=200)


# ------------------------------------------------------------------ dat decor len be mat (dung trong addon)
VIEW_DIR = {"front": (0, 1, 0), "back": (0, -1, 0), "left": (1, 0, 0), "right": (-1, 0, 0), "top": (0, 0, -1),
            "bottom": (0, 0, 1)}


def world_bvh(ob):
    from mathutils.bvhtree import BVHTree
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def union_bvh(objs):
    """BVH the gioi cua NHIEU manh + bang mat -> object (tia lay be mat NHIN THAY dau tien)."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    V, F, own = [], [], []
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        base = len(V)
        mw = o.matrix_world
        V += [mw @ v.co for v in me.vertices]
        for t in me.loop_triangles:
            F.append(tuple(base + i for i in t.vertices))
            own.append(o)
    if not F:
        return None, []
    return BVHTree.FromPolygons(V, F, all_triangles=True), own


def place_matrix(bvh, at, view, size, dims, rot=0.0, sink=0.45):
    """Ma tran the gioi cho decor: ban tia theo huong nhin `view` vao diem `at` tren manh chu (bvh the gioi), lay phap
    tuyen (trung binh vung lan can) -> mat truoc decor (-Y) huong ra ngoai, dau (+Z) huong len (Z the gioi chieu len
    mat phang tiep tuyen; mat tren nam ngang thi +Y). Lun `sink` x be day. Tra ve (Matrix, diem cham) hoac None."""
    from mathutils import Vector, Matrix
    d = Vector(VIEW_DIR.get(view, VIEW_DIR["front"])).normalized()
    a = Vector(at)
    # tia bat dau GAN diem Claude chi (truoc 1.2 don vi) - ban tu xa thi "top" trung dinh dau thay vi mat de duoi chan
    hit = bvh.ray_cast(a - d * 1.2, d, 2.4)
    if hit[0] is None:
        hit = bvh.ray_cast(a - d * 30.0, d, 60.0)
    if hit[0] is None:
        hit = bvh.find_nearest(a)
    if hit[0] is None:
        return None
    p, n, fidx = hit[0], hit[1].normalized(), hit[2]
    near = bvh.find_nearest_range(p, max(0.15, 0.5 * size))
    if near:
        acc = Vector()
        for loc, nn, idx, dist in near:
            acc += nn
        if acc.length > 1e-9 and acc.normalized().dot(n) > 0.3:
            n = acc.normalized()
    if n.dot(-d) < 0 and view in VIEW_DIR:          # mat trong (lung vo mong) -> lat ra phia nguoi nhin
        n = -n
    up = Vector((0, 0, 1)) - n * n.dot(Vector((0, 0, 1)))
    if up.length < 0.3:
        up = Vector((0, 1, 0)) - n * n.dot(Vector((0, 1, 0)))
    up.normalize()
    yax = -n
    xax = yax.cross(up).normalized()
    zax = xax.cross(yax).normalized()
    R = Matrix((xax, yax, zax)).transposed()
    if rot:
        R = Matrix.Rotation(math.radians(rot), 3, n) @ R
    s = float(size)
    thick = float(dims[1]) * s
    c = p + n * (0.5 - sink) * thick
    M = Matrix.Translation(c) @ R.to_4x4() @ Matrix.Scale(s, 4)
    return M, p, fidx


# ------------------------------------------------------------------ decor MOI do Claude thiet ke (ghep khoi co ban)
CUSTOM_BLEND = os.path.join(LIB_DIR, "custom.blend")
SHAPES = ("sphere", "box", "cylinder", "cone", "torus", "star", "arc")


def valid_spec(spec):
    """Kiem mo ta decor moi cua Claude. Tra ve loi (chuoi) hoac None."""
    parts = spec.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= 10:
        return "parts phai co 1-10 khoi"
    for p in parts:
        if p.get("shape") not in SHAPES:
            return "shape la: %s" % p.get("shape")
        for k in ("size", "at", "rot"):
            v = p.get(k, [1, 1, 1] if k == "size" else [0, 0, 0])
            if not (isinstance(v, list) and len(v) == 3 and
                    all(isinstance(x, (int, float)) and math.isfinite(x) and abs(x) < 50 for x in v)):
                return "%s sai" % k
    return None


def _spec_mesh(spec, name):
    """Ghep cac khoi co ban (toa do decor: mat truoc -Y, ~1 don vi) -> mesh."""
    import bpy, bmesh
    from mathutils import Matrix, Euler, Vector as V3
    total = bmesh.new()
    for p in spec["parts"]:
        bm = bmesh.new()
        sh = p["shape"]
        sx, sy, sz = [float(x) for x in p.get("size", [1, 1, 1])]
        if sh == "sphere":
            bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=0.5)
            bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
        elif sh == "box":
            bmesh.ops.create_cube(bm, size=1.0)
            bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
            for v in bm.verts:                       # bo tron goc (kieu do choi nhoi bong)
                c = v.co.copy()
                q = V3([math.copysign(max(0.0, abs(c[i]) - 0.3), c[i]) for i in range(3)])
                dv = c - q
                if dv.length > 1e-9:
                    v.co = q + dv.normalized() * 0.2
            bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
        elif sh in ("cylinder", "cone"):
            bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.5,
                                  radius2=0.5 if sh == "cylinder" else 0.0, depth=1.0)
            bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
        elif sh == "torus":
            r = 0.5 * min(0.45, sy)
            R = 0.5 - r
            rings = []
            for i in range(24):
                a = 2 * math.pi * i / 24
                ring = []
                for j in range(10):
                    b = 2 * math.pi * j / 10
                    ring.append(bm.verts.new(((R + r * math.cos(b)) * math.cos(a), r * math.sin(b),
                                              (R + r * math.cos(b)) * math.sin(a))))
                rings.append(ring)
            for i in range(24):
                for j in range(10):
                    bm.faces.new([rings[i][j], rings[(i + 1) % 24][j], rings[(i + 1) % 24][(j + 1) % 10],
                                  rings[i][(j + 1) % 10]])
            bmesh.ops.scale(bm, vec=(sx, 1.0, sz), verts=bm.verts)
        elif sh == "star":
            n = max(3, min(12, int(p.get("points", 5))))
            inner = float(p.get("inner", 0.45))
            pts = []
            for i in range(2 * n):
                a = math.pi / 2 + math.pi * i / n
                rr = 0.5 if i % 2 == 0 else 0.5 * inner
                pts.append((rr * math.cos(a), rr * math.sin(a)))
            top = [bm.verts.new((x, -0.35, z)) for x, z in pts]
            bot = [bm.verts.new((x, 0.5, z)) for x, z in pts]
            cf, cb = bm.verts.new((0, -0.5, 0)), bm.verts.new((0, 0.5, 0))
            m = len(pts)
            for i in range(m):
                j = (i + 1) % m
                bm.faces.new([top[i], top[j], bot[j], bot[i]])
                bm.faces.new([cf, top[j], top[i]])
                bm.faces.new([cb, bot[i], bot[j]])
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
        elif sh == "arc":
            a0, a1 = math.radians(float(p.get("from", 200))), math.radians(float(p.get("to", 340)))
            tube = float(p.get("tube", 0.08))
            n = 16
            rings = []
            for i in range(n + 1):
                a = a0 + (a1 - a0) * i / n
                c = np.array([0.5 * math.cos(a), 0.0, 0.5 * math.sin(a)])
                t = np.array([-math.sin(a), 0.0, math.cos(a)])
                nrm = np.cross(t, [0, 1.0, 0])
                ring = []
                for j in range(8):
                    b = 2 * math.pi * j / 8
                    q = c + tube * (math.cos(b) * nrm + math.sin(b) * np.array([0, 1.0, 0]))
                    ring.append(bm.verts.new(q.tolist()))
                rings.append(ring)
            for i in range(n):
                for j in range(8):
                    bm.faces.new([rings[i][j], rings[i][(j + 1) % 8], rings[i + 1][(j + 1) % 8], rings[i + 1][j]])
            bm.faces.new(list(reversed(rings[0])))
            bm.faces.new(rings[-1])
            bmesh.ops.scale(bm, vec=(sx, 1.0, sz), verts=bm.verts)
        Rm = Euler([math.radians(float(x)) for x in p.get("rot", [0, 0, 0])]).to_matrix().to_4x4()
        T = Matrix.Translation(V3([float(x) for x in p.get("at", [0, 0, 0])]))
        bm.transform(T @ Rm)
        tmp = bpy.data.meshes.new("_p")
        bm.to_mesh(tmp)
        bm.free()
        total.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    me = bpy.data.meshes.new(name)
    total.to_mesh(me)
    total.free()
    for f in me.polygons:
        f.use_smooth = True
    if not me.uv_layers:
        me.uv_layers.new(name="map1")
    return me


def build_custom():
    """Moi decor co 'spec' trong catalog (Claude tao) -> custom.blend; ve lai icon + bang tong."""
    import bpy
    cat = catalog()
    specs = [c for c in cat if c.get("spec")]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    out = []
    for c in specs:
        me = _spec_mesh(c["spec"], "dec_" + c["id"])
        c["dims"] = [round(float(x), 3) for x in _normalize(me)]
        out.append(bpy.data.objects.new("dec_" + c["id"], me))
    for o in out:
        bpy.context.scene.collection.objects.link(o)
    if out:
        bpy.data.libraries.write(CUSTOM_BLEND, set(out), fake_user=True)
    with open(CATALOG, "w", encoding="utf-8") as fh:
        json.dump(cat, fh, ensure_ascii=False, indent=1)
    render_thumbs(cat)
    print("[decor] %d decor do Claude tao -> %s" % (len(out), CUSTOM_BLEND))
