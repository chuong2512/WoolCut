"""Anh: (1) anh LUOI TOA DO cho Claude lap ke hoach cat, (2) anh ket qua (mau / moi manh mot mau / no tung).
Chay trong Blender. Toa do model da chuan hoa: tam X/Y = 0, day Z = 0, canh dai nhat 10."""
import os, math, colorsys
import numpy as np
import bpy
from mathutils import Vector
from . import bl

# huong nhin: (vi tri camera theo huong, truc ngang anh, truc doc anh)
VIEWS = {
    "front": ((0, -1, 0), "X", "Z"),     # nhin tu truoc (mat truoc model o -Y)
    "back":  ((0, 1, 0), "-X", "Z"),
    "right": ((1, 0, 0), "Y", "Z"),      # nhin tu ben phai model (+X)
    "left":  ((-1, 0, 0), "-Y", "Z"),
    "top":   ((0, 0, 1), "X", "Y"),
    "iso":   ((0.75, -1, 0.65), None, None),
    "iso_back": ((-0.75, 1, 0.65), None, None),
}


def setup(res=900):
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    w = sc.world or bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.93, 0.93, 0.95, 1)
    bg.inputs[1].default_value = 0.9
    if not bpy.data.objects.get("_sun"):
        for nm, en, rot in (("_sun", 3.2, (50, 0, 25)), ("_fill", 1.3, (-55, 0, 200)), ("_top", 0.8, (0, 0, 0))):
            L = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "SUN"))
            sc.collection.objects.link(L)
            L.data.energy = en
            L.rotation_euler = tuple(math.radians(a) for a in rot)
    cam = bpy.data.objects.get("_cam")
    if cam is None:
        cam = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
        sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    sc.camera = cam
    return cam


def _emit(name, rgb):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs[0].default_value = (rgb[0], rgb[1], rgb[2], 1)
        m.diffuse_color = (rgb[0], rgb[1], rgb[2], 1)        # Workbench (anh nhanh) lay mau nay
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(e.outputs[0], o.inputs[0])
    return m


def _axis_vec(a):
    s = -1 if a.startswith("-") else 1
    return np.array({"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[a[-1]]) * s


def frame2d(view, lo, hi):
    """Khung luoi (toa do anh) cho mot huong nhin: (H, V, d, h0, h1, v0, v1) - H, V co dau."""
    d, ha, va = VIEWS[view]
    d = np.array(d, dtype=float)
    H, Vv = _axis_vec(ha), _axis_vec(va)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    hs, vs = corners @ H, corners @ Vv
    return H, Vv, d, math.floor(hs.min()) - 1, math.ceil(hs.max()) + 1, math.floor(vs.min()) - 1, math.ceil(vs.max()) + 1


def grid(view, lo, hi, step=1.0):
    """Luoi + nhan so phia sau model cho mot huong nhin. Nhan ghi TOA DO THAT cua truc (x, y hoac z).
    Tra ve list object de xoa sau."""
    H, Vv, d, h0, h1, v0, v1 = frame2d(view, lo, hi)
    objs = []
    c = (lo + hi) / 2
    depth = float(d @ c) - (float(np.abs(d) @ (hi - lo)) / 2 + 1.5)    # mat phang sau model
    sh = 1.0 if H.sum() > 0 else -1.0                                   # dau cua truc ngang
    sv = 1.0 if Vv.sum() > 0 else -1.0

    def P(h, v, dd=0.0):          # toa do anh (h, v) + do sau -> diem 3D
        return H * h + Vv * v + d * (depth + dd)
    verts, faces = [], []
    th = 0.018

    def quad(p0, p1, wdir):
        i = len(verts)
        for q in (p0 - wdir * th, p1 - wdir * th, p1 + wdir * th, p0 + wdir * th):
            verts.append(tuple(q))
        faces.append((i, i + 1, i + 2, i + 3))
    for g in np.arange(h0, h1 + 1e-6, step / 2):
        quad(P(g, v0), P(g, v1), H * (1.0 if abs(g - round(g)) < 1e-6 else 0.45))
    for g in np.arange(v0, v1 + 1e-6, step / 2):
        quad(P(h0, g), P(h1, g), Vv * (1.0 if abs(g - round(g)) < 1e-6 else 0.45))
    me = bpy.data.meshes.new("_grid")
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("_grid", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(_emit("_gridmat", (0.62, 0.64, 0.7)))
    objs.append(ob)
    txt = _emit("_txtmat", (0.05, 0.05, 0.1))
    an, vn = VIEWS[view][1][-1].lower(), VIEWS[view][2][-1].lower()
    for g in range(h0, h1 + 1):                     # nhan truc ngang: duoi khung
        val = int(round(sh * g))
        objs.append(_label("%s=%d" % (an, val) if g == h0 else str(val), P(g, v0 - 0.5, 0.2), d, H, Vv, txt))
    for g in range(v0, v1 + 1):                     # nhan truc doc: trai khung
        val = int(round(sv * g))
        objs.append(_label("%s=%d" % (vn, val) if g == v0 else str(val), P(h0 - 0.6, g, 0.2), d, H, Vv, txt))
    return objs


def _label(text, pos, d, H, Vv, mat):
    cu = bpy.data.curves.new("_t", "FONT")
    cu.body = text
    cu.size = 0.42
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new("_t", cu)
    bpy.context.scene.collection.objects.link(ob)
    # chu nam trong mat phang (H, V), nhin ve phia camera (+d)
    from mathutils import Matrix
    R = Matrix(((H[0], Vv[0], d[0]), (H[1], Vv[1], d[1]), (H[2], Vv[2], d[2])))
    ob.matrix_world = Matrix.Translation(Vector(pos)) @ R.to_4x4()
    cu.materials.append(mat)
    return ob


def shoot(cam, view, lo, hi, path, margin=1.25):
    d = np.array(VIEWS[view][0], dtype=float)
    d = d / np.linalg.norm(d)
    c = (lo + hi) / 2
    diag = float(np.linalg.norm(hi - lo))
    if VIEWS[view][1] is not None:                 # huong chinh: canh camera theo khung luoi
        H, Vv, dd, h0, h1, v0, v1 = frame2d(view, lo, hi)
        hc, vc = (h0 + h1) / 2 - 0.3, (v0 + v1) / 2 - 0.25
        c = H * hc + Vv * vc + d * float(d @ c)
        cam.data.ortho_scale = max(h1 - h0, v1 - v0) + 1.8
    else:
        cam.data.ortho_scale = diag * margin
    cam.location = Vector(c + d * diag * 2.5)
    cam.rotation_euler = Vector(-d).to_track_quat("-Z", "Y").to_euler()
    if view == "top":
        cam.rotation_euler = (0, 0, 0)
    cam.data.clip_end = diag * 10
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def bounds(objs):
    lo = np.array([1e9] * 3)
    hi = -lo
    for o in objs:
        if o.type != "MESH" or not o.data.vertices:
            continue
        V = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
        lo = np.minimum(lo, V.min(0))
        hi = np.maximum(hi, V.max(0))
    return lo, hi


def plan_views(objs, out_dir, prefix="plan", views=("front", "right", "back", "left", "top"), res=900, fast=False):
    """Anh co luoi toa do cho Claude doc vi tri cat. fast: Workbench (mau material phang + hoc toi), nhanh ~10 lan."""
    cam = setup(res)
    if fast:
        _workbench(bpy.context.scene, by_object=False)
    lo, hi = bounds(objs)
    paths = []
    for v in views:
        g = grid(v, lo, hi)
        p = os.path.join(out_dir, "%s_%s.png" % (prefix, v))
        shoot(cam, v, lo, hi, p)
        for o in g:
            bpy.data.objects.remove(o, do_unlink=True)
        paths.append(p)
    p = os.path.join(out_dir, "%s_iso.png" % prefix)
    shoot(cam, "iso", lo, hi, p)
    paths.append(p)
    return paths


def id_colors(n, seed=7):
    rnd = np.random.RandomState(seed)
    out = []
    for i in range(n):
        h = (i * 0.618034 + 0.05) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.5 + 0.4 * rnd.rand(), 0.62 + 0.38 * rnd.rand())
        out.append((r ** 2.2, g ** 2.2, b ** 2.2))
    return out


ALL_VIEWS = ("front", "back", "left", "right", "top", "iso", "iso_back")
VIEW_VI = {"front": "truoc (-Y)", "back": "sau (+Y)", "left": "trai (-X)", "right": "phai (+X)", "top": "tren",
           "iso": "iso truoc", "iso_back": "iso sau", "explode": "no tung"}


def _read_png(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    return px


def _text_strips(texts, w, h, tmp):
    """Nhieu dai chu w x h trong MOT lan render Workbench (xep doc) - truoc moi nhan mot lan render EEVEE ~0.36 s."""
    sc = bpy.context.scene
    cam = sc.camera
    if not texts:
        return []
    restore = _workbench(sc, by_object=True)
    hidden = {o.name: o.hide_render for o in sc.objects}
    for o in sc.objects:
        if o.type in ("MESH", "FONT", "CURVE"):
            o.hide_render = True
    old = (sc.render.resolution_x, sc.render.resolution_y, tuple(cam.location), tuple(cam.rotation_euler),
           cam.data.ortho_scale, cam.data.clip_start, cam.data.clip_end)
    n = len(texts)
    H = n * h
    u = 0.01
    sc.render.resolution_x, sc.render.resolution_y = w, H
    cam.location = Vector((w * u / 2, H * u / 2, 50.0))
    cam.rotation_euler = (0, 0, 0)
    cam.data.ortho_scale = max(w, H) * u
    cam.data.clip_start, cam.data.clip_end = 0.1, 100.0
    objs = []
    for i, text in enumerate(texts):
        cu = bpy.data.curves.new("_lab", "FONT")
        cu.body = text or " "
        cu.size = 0.7 * h * u
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        t = bpy.data.objects.new("_lab", cu)
        t.location = (w * u / 2, (H - (i + 0.5) * h) * u, 0.0)     # o i tu tren xuong
        t.color = (0.05, 0.05, 0.1, 1.0)
        sc.collection.objects.link(t)
        objs.append(t)
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    px = _read_png(tmp)
    for t in objs:
        cu = t.data
        bpy.data.objects.remove(t, do_unlink=True)
        bpy.data.curves.remove(cu)
    for o in sc.objects:
        if o.name in hidden:
            o.hide_render = hidden[o.name]
    sc.render.resolution_x, sc.render.resolution_y = old[0], old[1]
    cam.location, cam.rotation_euler, cam.data.ortho_scale = Vector(old[2]), old[3], old[4]
    cam.data.clip_start, cam.data.clip_end = old[5], old[6]
    restore()
    return [px[H - (i + 1) * h:H - i * h] for i in range(n)]


def _text_strip(text, w, h, tmp):
    """Anh chu (nen sang) rong w x h - render rieng mot text object, an moi thu khac."""
    sc = bpy.context.scene
    cam = sc.camera
    hidden = {o.name: o.hide_render for o in sc.objects}
    for o in sc.objects:
        if o.type in ("MESH", "FONT", "CURVE"):
            o.hide_render = True
    old = (sc.render.resolution_x, sc.render.resolution_y, tuple(cam.location), tuple(cam.rotation_euler),
           cam.data.ortho_scale)
    sc.render.resolution_x, sc.render.resolution_y = w, h
    cam.location = Vector((0, 0, 1000))
    cam.rotation_euler = (0, 0, 0)
    cam.data.ortho_scale = 10.0 * w / max(w, h)
    cu = bpy.data.curves.new("_lab", "FONT")
    cu.body = text
    cu.size = 10.0 * 0.7 * h / max(w, h)
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    t = bpy.data.objects.new("_lab", cu)
    t.location = (0, 0, 990)
    sc.collection.objects.link(t)
    cu.materials.append(_emit("_txtmat", (0.05, 0.05, 0.1)))
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    px = _read_png(tmp)
    bpy.data.objects.remove(t, do_unlink=True)
    for o in sc.objects:
        if o.name in hidden:
            o.hide_render = hidden[o.name]
    sc.render.resolution_x, sc.render.resolution_y = old[0], old[1]
    cam.location, cam.rotation_euler, cam.data.ortho_scale = Vector(old[2]), old[3], old[4]
    return px


def compose(paths, labels, out, cols=3, tile=400, title=""):
    """Ghep nhieu anh thanh mot luoi co nhan (de Claude / nguoi xem soat MOI GOC trong mot anh)."""
    tmp = os.path.join(os.path.dirname(out), "_strip.png")
    lab_h = 36
    rows = (len(paths) + cols - 1) // cols
    W, H = cols * tile, rows * (tile + lab_h)
    canvas = np.ones((H, W, 4), dtype=np.float32) * np.array([0.93, 0.93, 0.95, 1.0], dtype=np.float32)
    strips = _text_strips(list(labels), tile, lab_h, tmp)     # mot lan render cho moi nhan
    for i, (pth, lab) in enumerate(zip(paths, labels)):
        px = _read_png(pth)
        h, w = px.shape[:2]
        k = max(1, int(round(max(h, w) / tile)))
        px = px[:h // k * k, :w // k * k].reshape(h // k, k, w // k, k, 4).mean((1, 3))
        px = px[:tile, :tile]
        r, c = divmod(i, cols)
        y0 = H - (r + 1) * (tile + lab_h) + lab_h
        canvas[y0 + tile - px.shape[0]:y0 + tile, c * tile:c * tile + px.shape[1]] = px
        strip = strips[i]
        canvas[y0 - lab_h:y0, c * tile:(c + 1) * tile] = strip[:lab_h, :tile]
    img = bpy.data.images.new("_compose", W, H, alpha=True)
    img.pixels = canvas.ravel().tolist()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return out


def result_views(objs, out_dir, prefix="parts", res=800, explode=0.55):
    """Anh ket qua o DU CAC GOC (truoc, sau, trai, phai, tren, iso, iso sau) - mau that va moi manh mot mau - va
    anh no tung; ghep thanh <prefix>_all.png va <prefix>_ids_all.png de soat mot lan (nguoi dung 2026-10-02:
    'nen cat du cac goc de tu xem xet cach cat')."""
    cam = setup(res)
    lo, hi = bounds(objs)
    mats = {o.name: [s.material for s in o.material_slots] for o in objs}
    out = []
    col_paths, id_paths = [], []
    for v in ALL_VIEWS:
        p = os.path.join(out_dir, "%s_%s.png" % (prefix, v))
        shoot(cam, v, lo, hi, p, margin=1.12)
        col_paths.append(p)
    cols = id_colors(len(objs))
    for i, o in enumerate(objs):
        m = bl.flat_material("_id%d" % i, cols[i])
        for s in o.material_slots:
            s.material = m
    for v in ALL_VIEWS:
        p = os.path.join(out_dir, "%s_ids_%s.png" % (prefix, v))
        shoot(cam, v, lo, hi, p, margin=1.12)
        id_paths.append(p)
    c = (lo + hi) / 2
    keep = {o.name: o.location.copy() for o in objs}
    for o in objs:
        V = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
        oc = V.mean(0)
        o.location = keep[o.name] + Vector(((oc - c) * explode).tolist())
    ex = os.path.join(out_dir, "%s_explode_iso.png" % prefix)
    shoot(cam, "iso", lo - (hi - lo) * explode / 2, hi + (hi - lo) * explode / 2, ex, margin=1.1)
    exb = os.path.join(out_dir, "%s_explode_iso_back.png" % prefix)
    shoot(cam, "iso_back", lo - (hi - lo) * explode / 2, hi + (hi - lo) * explode / 2, exb, margin=1.1)
    for o in objs:
        o.location = keep[o.name]
    labels = [VIEW_VI[v] for v in ALL_VIEWS] + [VIEW_VI["explode"]]
    out.append(compose(id_paths + [ex], labels, os.path.join(out_dir, "%s_ids_all.png" % prefix)))
    for o in objs:
        for s, m in zip(o.material_slots, mats[o.name]):
            s.material = m
    out.append(compose(col_paths + [exb], labels[:-1] + ["no tung (sau)"], os.path.join(out_dir, "%s_all.png" % prefix)))
    out += col_paths + id_paths + [ex, exb]
    return out


def _workbench(sc, by_object=True):
    """Chuyen sang Workbench (kieu viewport Solid: mau phang + hoc toi + vien) - nhanh hon EEVEE ~10 lan.
    Tra ve ham khoi phuc engine cu."""
    old = sc.render.engine
    try:
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "OBJECT" if by_object else "MATERIAL"
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.show_object_outline = True
        if sc.world is not None:
            sc.world.color = (0.93, 0.93, 0.95)
    except (TypeError, AttributeError):
        pass

    def restore():
        try:
            sc.render.engine = old
        except TypeError:
            pass
    return restore


def sheet(objs, path, labels, tile=220, cols=8):
    """Bang manh: moi manh mot o (nhin iso, mau cua manh), ten + loai + mau o duoi.
    2026-10-02: truoc day EEVEE render tung o (~0.6 s) + render RIENG tung nhan chu -> xe may 197 manh mat 119 s
    / 151 s cua buoc cat. Nay: o hinh bang Workbench, tat ca nhan chu render MOT lan."""
    cam = setup(tile)
    sc = bpy.context.scene
    restore = _workbench(sc, by_object=True)
    tmp = os.path.join(os.path.dirname(path), "_tile.png")
    hide = {o.name: o.hide_render for o in objs}
    rows = (len(objs) + cols - 1) // cols
    W, H = cols * tile, rows * (tile + 34)
    canvas = np.ones((H, W, 4), dtype=np.float32) * np.array([0.93, 0.93, 0.95, 1.0], dtype=np.float32)
    sc.render.resolution_x = sc.render.resolution_y = tile
    for i, o in enumerate(objs):
        for x in objs:
            x.hide_render = x is not o
        lo, hi = bounds([o])
        c = (lo + hi) / 2
        diag = float(np.linalg.norm(hi - lo)) or 1.0
        d = np.array(VIEWS["iso"][0], dtype=float)
        d /= np.linalg.norm(d)
        cam.location = Vector(c + d * diag * 3)
        cam.rotation_euler = Vector(-d).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = diag * 1.15
        cam.data.clip_end = diag * 20
        cam.data.clip_start = diag * 0.01
        bpy.context.view_layer.update()
        sc.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp, check_existing=False)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(tile, tile, 4)
        bpy.data.images.remove(img)
        r, k = divmod(i, cols)
        y0 = H - (r + 1) * (tile + 34) + 34
        canvas[y0:y0 + tile, k * tile:(k + 1) * tile] = px
    # TAT CA nhan chu trong MOT lan render: khung W x H, 1 px = 0.01 don vi, chu dat dung dai nhan cua tung o
    for o in objs:
        o.hide_render = True
    u = 0.01
    sc.render.resolution_x, sc.render.resolution_y = W, H
    cam.rotation_euler = (0, 0, 0)
    cam.location = Vector((W * u / 2, H * u / 2, 50.0))
    cam.data.ortho_scale = max(W, H) * u
    cam.data.clip_start, cam.data.clip_end = 0.1, 100.0
    txt = []
    for i, lab in enumerate(labels):
        r, k = divmod(i, cols)
        ys = H - (r + 1) * (tile + 34)                    # day cua dai nhan (toa do anh, tu duoi len)
        cu = bpy.data.curves.new("_lab", "FONT")
        cu.body = lab
        cu.size = 21 * u
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        t = bpy.data.objects.new("_lab", cu)
        t.location = ((k + 0.5) * tile * u, (ys + 17) * u, 0.0)
        t.color = (0.05, 0.05, 0.1, 1.0)
        sc.collection.objects.link(t)
        txt.append(t)
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    lab_px = _read_png(tmp)
    for t in txt:
        cu = t.data
        bpy.data.objects.remove(t, do_unlink=True)
        bpy.data.curves.remove(cu)
    if lab_px.shape[0] == H and lab_px.shape[1] == W:
        for r in range(rows):
            ys = H - (r + 1) * (tile + 34)
            canvas[ys:ys + 34] = lab_px[ys:ys + 34]
    for o in objs:
        o.hide_render = hide[o.name]
    sc.render.resolution_x = sc.render.resolution_y = tile
    restore()
    out = bpy.data.images.new("_sheet", W, H, alpha=True)
    out.pixels = canvas.ravel().tolist()
    out.filepath_raw = path
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return path
