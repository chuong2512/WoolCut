"""Buoc 4 - DAT TEN S/M/D + XUAT FBX dung cau tao bo 108 file goc (chep logic tu PrimForge export.py).

Cay khi mo trong Blender:
    <Ten>            EMPTY, xoay X 90, scale 0.01   (Maya: cm, Y-up)
      S_<Ten>        EMPTY
        S_<Ten>_1    MESH, moi transform identity, toa do dinh = toa do model
          D_<Ten>_3  MESH - D la con cua dung manh no trang tri
      M_<Ten>        EMPTY
        M_<Ten>_1 ...
Loai moi manh: wc_kind (chon tay) > wc_kind_auto (buoc cat) > luat kich thuoc. Mau: material dau tien
(nguoi dung doi trong Blender) > wc_color. M ho -> S."""
import os, re, json, math, uuid
import bpy, bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from . import std, bl, look

KINDS = ("S", "M", "D")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_TEMPLATE = os.path.join(HERE, "data", "fbx_meta_template.txt")


def clean_name(name):
    s = re.sub(r"[^A-Za-z0-9]", "", name)
    if not s or not s[0].isalpha():
        s = "Model" + s
    return s


def _bbox(objs):
    vs = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    return (Vector([min(v[i] for v in vs) for i in range(3)]), Vector([max(v[i] for v in vs) for i in range(3)]))


def _closed(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    ok = len(bm.edges) > 0 and all(len(e.link_faces) == 2 for e in bm.edges)
    bm.free()
    return ok


def kind_of(o, side):
    for key in ("wc_kind", "wc_kind_auto"):
        k = str(o.get(key, "")).upper()
        if k in KINDS:
            return k
    lo, hi = _bbox([o])
    return std.classify(hi - lo, side)


def color_of(o):
    """Mau bang cua manh: material (nguoi dung doi) > wc_color; manh D dung Deco_mat thi mau o wc_color."""
    m = o.data.materials[0] if o.data.materials else None
    c = std.canonical(m.name) if m else None
    if c and c.startswith("Deco_mat"):
        c = None
    return c or o.get("wc_color") or std.mat_name(25, "Gray")


def uv_box(me, density=std.UV_DENSITY):
    """UV chieu theo khong gian that 2.148 o/m: mat ngang (x,y), mat dung (ngang, z) -> cot mui dan doc."""
    if not me.uv_layers:
        me.uv_layers.new(name=std.UV_NAME)
    me.uv_layers[0].name = std.UV_NAME
    uv = me.uv_layers[0].data
    for p in me.polygons:
        n = p.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if az > 0.75:
                u, v = co.x, co.y
            elif ax >= ay:
                u, v = co.y, co.z
            else:
                u, v = co.x, co.z
            uv[li].uv = (u * density, v * density)


DECO_TEX = os.path.join(HERE, "data", "Deco_Texture.png")
DECO_POINTS = os.path.join(HERE, "data", "deco_points.json")
_DECO = {}


def deco_point(mat_name):
    """Diem UV tren Deco_Texture.png cho mieng D mau `mat_name`: trong cac diem BO GOC da dung (data/deco_points.json,
    368 diem), chon diem mau gan nhat (CIEDE2000), uu tien diem hay dung."""
    import numpy as np
    from . import color
    if "pts" not in _DECO:
        with open(DECO_POINTS, encoding="utf-8") as fh:
            pts = [p for p in json.load(fh)["points"] if p["count"] >= 2]
        _DECO["pts"] = pts
        _DECO["lab"] = color._lab(color._to_lin(np.array([p["srgb"] for p in pts])))
    pts, labs = _DECO["pts"], _DECO["lab"]
    n = int(re.match(r"Color_(\d+)_", mat_name).group(1)) if re.match(r"Color_(\d+)_", mat_name or "") else 15
    want = std.NOMINAL.get(n, (0.9, 0.9, 0.9))
    lab = color._lab(color._to_lin(np.array([want])))
    de = color.de2000(lab, labs, 1.0)[0]
    score = de - 2.0 * np.log10(np.array([p["count"] for p in pts]))
    p = pts[int(score.argmin())]
    return p["u"], p["v"], float(de[int(score.argmin())])


def deco_material():
    """Material Deco_mat nhu bo goc (ten khop material Unity Game/Material/Deco_mat.mat), hien texture Deco."""
    m = bpy.data.materials.get(std.DECO_MAT)
    if m is None:
        m = bpy.data.materials.new(std.DECO_MAT)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        tex = nt.nodes.new("ShaderNodeTexImage")
        if os.path.exists(DECO_TEX):
            tex.image = bpy.data.images.load(DECO_TEX, check_existing=True)
            tex.interpolation = "Closest"
        nt.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.553
    return m


def deco_uv(me, u, v):
    if not me.uv_layers:
        me.uv_layers.new(name=std.UV_NAME)
    me.uv_layers[0].name = std.UV_NAME
    import numpy as np
    me.uv_layers[0].data.foreach_set("uv", np.tile([u, v], len(me.loops)).astype(np.float32))


def to_quads(me):
    """Ghep cap tam giac thanh tu giac (bo goc 83.5% tu giac). Khong doi hinh; giu canh sac (mep nap)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bmesh.ops.join_triangles(bm, faces=bm.faces, angle_face_threshold=math.radians(30),
                             angle_shape_threshold=math.radians(40), cmp_seam=False, cmp_sharp=True,
                             cmp_uvs=False, cmp_vcols=False, cmp_materials=True)
    bm.to_mesh(me)
    bm.free()
    me.update()


def build(objs, name, size_target=std.SIZE_TARGET, pivot="center"):
    """Manh (object mesh) -> cay chuan + ten S_/M_/D_. Tra ve (ten goc, [hang bang ket qua])."""
    name = clean_name(name)
    bpy.context.view_layer.update()
    lo, hi = _bbox(objs)
    side = max(hi - lo)
    info = []
    for o in objs:
        k = kind_of(o, side)
        if k == "M" and not _closed(o):
            print("[xuat] %s ho -> doi M thanh S" % o.name)
            k = "S"
        info.append(dict(obj=o, kind=k, mat=color_of(o), src=o.name, host=o.get("wc_host")))
    # D: cha = wc_host neu con, khong thi manh S/M co be mat gan nhat
    by_src = {d["src"]: d for d in info}
    hosts = [d for d in info if d["kind"] != "D"] or info
    trees = {}
    for d in hosts:
        bm = bmesh.new()
        bm.from_mesh(d["obj"].data)
        bm.transform(d["obj"].matrix_world)
        trees[d["src"]] = BVHTree.FromBMesh(bm)
        bm.free()
    for d in info:
        if d["kind"] != "D":
            continue
        h = by_src.get(d["host"])
        if h is None or h["kind"] == "D":
            o = d["obj"]
            pts = [o.matrix_world @ v.co for v in o.data.vertices][::max(1, len(o.data.vertices) // 60)]
            best, bd = None, 1e18
            for q in hosts:
                if q is d:
                    continue
                dist = min((trees[q["src"]].find_nearest(v)[3] or 1e18) for v in pts)
                if dist < bd:
                    best, bd = q, dist
            h = best
        d["parent"] = h
    # chuan hoa: tam hop bao ve goc, canh dai nhat = size_target
    k = (size_target / side) if size_target else 1.0
    N = Matrix.Scale(k, 4) @ Matrix.Translation(-(lo + hi) / 2)
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    root.rotation_euler = (math.radians(std.ROOT_ROT_X_DEG), 0, 0)
    root.scale = (std.ROOT_SCALE,) * 3
    bpy.context.view_layer.update()
    Rinv = root.matrix_world.inverted()
    groups = {}
    for kd in ("S", "M"):
        g = bpy.data.objects.new("%s_%s" % (kd, name), None)
        bpy.context.scene.collection.objects.link(g)
        g.parent = root
        g.matrix_parent_inverse = Matrix.Identity(4)
        groups[kd] = g
    # thu tu: M truoc (to -> nho), S, D
    info.sort(key=lambda d: ({"M": 0, "S": 1, "D": 2}[d["kind"]], -max(_bbox([d["obj"]])[1] - _bbox([d["obj"]])[0])))
    cnt = {"S": 0, "M": 0, "D": 0}
    for d in info:
        cnt[d["kind"]] += 1
        d["name"] = "%s_%s_%d" % (d["kind"], name, cnt[d["kind"]])
    for d in info:
        o = d["obj"]
        o.data.transform(N @ o.matrix_world)
        o.matrix_basis = Matrix.Identity(4)
        to_quads(o.data)
        o.data.materials.clear()
        o.data.materials.append(look.palette_material(d["mat"], game=False))   # mau FBX phang nhu model mau
    # UV kieu bo goc (1-3 dao/manh, van len doc chieu dai, 2.148 o/m) - tinh o kich thuoc cuoi, truoc khi doi truc
    from . import uv as uvmod
    n_uv = uvmod.unwrap([d["obj"] for d in info if d["kind"] != "D"])
    print("[uv] trai UV %d/%d manh S/M" % (n_uv, sum(1 for d in info if d["kind"] != "D")))
    # UV2 'uvSet' = tham so cuon len cho hieu ung tan dan (shader UserWooler clip theo uv2.y) - nhu BearArt
    for d in info:
        if d["kind"] != "D":
            uvmod.flow_uv(d["obj"])
    # D: material Deco_mat + UV don vao MOT diem cua o mau tren Deco_Texture (85% D bo goc lam vay)
    for d in info:
        if d["kind"] != "D":
            continue
        o = d["obj"]
        if o.get("wc_decor_multi") and o.data.uv_layers:    # decor nhieu mau tu thu vien: giu UV tren Deco_Texture
            o.data.materials.clear()
            o.data.materials.append(look.deco_material())
            o.data.uv_layers[0].name = std.UV_NAME
            d["deco"] = "multi"
            d["mat"] = std.DECO_MAT
            continue
        u, v, de = look.deco_point(d["mat"])
        o.data.materials.clear()
        o.data.materials.append(look.deco_material())
        look.deco_uv(o.data, u, v)
        d["deco"] = (u, v, round(de, 1))
        d["mat"] = std.DECO_MAT
    for d in info:
        d["obj"].data.transform(Rinv)
        d["c"] = Vector((0, 0, 0))
        if pivot == "center":                      # tam manh o GIUA manh (nguoi dung 2026-10-02); BearArt: tai goc
            me = d["obj"].data
            P = [v.co for v in me.vertices]
            if P:
                lo = Vector([min(q[i] for q in P) for i in range(3)])
                hi = Vector([max(q[i] for q in P) for i in range(3)])
                d["c"] = (lo + hi) / 2
                me.transform(Matrix.Translation(-d["c"]))
    for d in info:
        o = d["obj"]
        o.name = d["name"]
        o.data.name = d["name"]
        host = d["parent"] if d["kind"] == "D" and d.get("parent") else None
        par = host["obj"] if host else groups["M" if d["kind"] == "M" else "S"]
        o.parent = par
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_basis = Matrix.Translation(d["c"] - (host["c"] if host else Vector((0, 0, 0))))
        for c in list(o.users_collection):
            c.objects.unlink(o)
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    rows = [dict(mesh=d["name"], kind=d["kind"], mat=d["mat"], src=d["src"], deco_uv=d.get("deco"),
                 parent=d["parent"]["name"] if d.get("parent") else None) for d in info]
    return name, rows


def write_fbx(path):
    kw = dict(filepath=path, use_selection=False, object_types={"EMPTY", "MESH"},
              apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE", global_scale=1.0,
              axis_forward="-Z", axis_up="Y", bake_space_transform=False,
              mesh_smooth_type="FACE", use_mesh_modifiers=True, use_triangles=False,
              add_leaf_bones=False, use_custom_props=False, path_mode="AUTO",
              embed_textures=False, bake_anim=False, colors_type="NONE")
    try:
        bpy.ops.export_scene.fbx(**kw)
    except TypeError:
        for key in ("colors_type", "use_triangles"):
            kw.pop(key, None)
        bpy.ops.export_scene.fbx(**kw)
    return path


def write_meta(fbx_path):
    if not os.path.exists(META_TEMPLATE):
        return None
    with open(META_TEMPLATE, encoding="utf-8") as fh:
        t = fh.read()
    t = re.sub(r"guid: \w+", "guid: " + uuid.uuid4().hex, t, count=1)
    with open(fbx_path + ".meta", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(t)
    return fbx_path + ".meta"


def polycount(meshes, rows=None):
    """So tam giac / mat / dinh cua FBX vua dung (nguoi dung 2026-10-08: "khi xuat thong bao so policount")."""
    kind = {r["mesh"]: r["kind"] for r in (rows or [])}
    out = dict(tris=0, faces=0, verts=0, quads=0, by_kind={"M": 0, "S": 0, "D": 0})
    for o in meshes:
        n3 = sum(len(p.vertices) - 2 for p in o.data.polygons)
        out["tris"] += n3
        out["faces"] += len(o.data.polygons)
        out["quads"] += sum(1 for p in o.data.polygons if len(p.vertices) == 4)
        out["verts"] += len(o.data.vertices)
        k = kind.get(o.name)
        if k in out["by_kind"]:
            out["by_kind"][k] += n3
    out["quad_pct"] = round(100 * out["quads"] / max(1, out["faces"]))
    return out


EXPORT_SIZE = 8.2     # canh dai nhat khi mo trong Blender: bang BearArt (nguoi dung 2026-10-02: file goc to hon);
                       # bo goc 4.3-8.2, trung vi 6.1


def run(parts_blend, name, out_dir, size=EXPORT_SIZE, pivot="center", kind="char"):
    """Mo parts.blend (hoac ban da sua tay) -> cay chuan -> FBX + .meta + .map.json + anh + BANG CHAM DIEM
    (<Goc>.score.json canh FBX va work/<Ten>/score.json; wc/score.py)."""
    from . import render
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(parts_blend, link=False) as (src, dst):
        dst.objects = [n for n in src.objects]
    objs = [o for o in dst.objects if o is not None and o.type == "MESH" and not o.name.startswith("_")]
    for o in objs:
        bpy.context.scene.collection.objects.link(o)
        o.parent = None
    # BAT BUOC: object vua nap tu thu vien co matrix_world CU (identity) toi khi depsgraph cap nhat. Manh co tam
    # rieng (location != 0) ma khong cap nhat thi build doc sai vi tri -> manh vang ra xa (thuyen sushi 2026-10-02).
    bpy.context.view_layer.update()
    root, rows = build(objs, name, size_target=size, pivot=pivot)
    os.makedirs(out_dir, exist_ok=True)
    fbx = os.path.join(out_dir, root + ".fbx")
    write_fbx(fbx)
    write_meta(fbx)
    with open(os.path.join(out_dir, root + ".map.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    render.result_views(meshes, out_dir, prefix=root, res=700)
    cnt = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}
    mats = sorted(set(r["mat"] for r in rows if r["kind"] != "D"))
    print("[xuat] %s: %d M, %d S, %d D, %d mau -> %s" % (root, cnt["M"], cnt["S"], cnt["D"], len(mats), fbx))
    poly = polycount(meshes, rows)
    print("[polycount] %d tam giac · %d mat (%d%% tu giac) · %d dinh | M %d · S %d · D %d tam giac" % (
        poly["tris"], poly["faces"], poly["quad_pct"], poly["verts"], poly["by_kind"]["M"], poly["by_kind"]["S"],
        poly["by_kind"]["D"]))
    print("POLY: %d %d %d %d" % (poly["tris"], poly["faces"], poly["verts"], poly["quad_pct"]))
    for r in rows:
        print("[mesh] %s | %s%s" % (r["mesh"], r["mat"].replace("Color_", "").replace("_mat", ""),
                                   (" | cha " + r["parent"]) if r["parent"] else ""))
    try:                                         # cham diem tren cay vua dung (mau D da thanh Deco_mat - khong tinh)
        from . import score as scmod
        by = {o.name: o for o in meshes}
        items = [dict(obj=by[r["mesh"]], name=r["src"], kind=r["kind"], mat=r["mat"],
                      host=(next((x["src"] for x in rows if x["mesh"] == r["parent"]), None) if r["parent"] else None))
                 for r in rows if r["mesh"] in by]
        res = scmod.measure(items, kind=kind)
        res["fbx"] = fbx
        res["poly"] = poly
        res["draft"] = os.path.normcase(os.path.abspath(out_dir)) != os.path.normcase(os.path.join(HERE, "out"))
        scmod.save(res, os.path.join(out_dir, root + ".score.json"),
                   os.path.join(HERE, "work", name, "score.json") if os.path.isdir(os.path.join(HERE, "work", name))
                   else None)
        for ln in scmod.lines(res):
            print(ln)
        print("SCORE: %d %s" % (res["score"], res["grade"]))
    except Exception as e:                       # cham diem khong duoc lam hong viec xuat
        import traceback
        traceback.print_exc()
        print("[cham diem] loi: %s" % e)
    return fbx
