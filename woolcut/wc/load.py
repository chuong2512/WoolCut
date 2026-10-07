"""Nap model (glb/gltf/fbx/obj) va doc mau tung mat tu texture. Chay trong Blender.
Chep tu primforge/pf/mesh.py (2026-10-01) - woolcut khong import primforge."""
import os, math
import numpy as np
import bpy, bmesh
from mathutils import Matrix
from . import std


def _to_lin(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))


def load(path, turn=0.0, tilt=0.0):
    """Nap file, ap transform + LAT `tilt` do quanh X (model nam) roi xoay `turn` do quanh Z. Tra ve SRC_n."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError("khong doc duoc %s (fbx/glb/gltf/obj)" % ext)
    dg = bpy.context.evaluated_depsgraph_get()
    imported = list(bpy.data.objects)
    src = [o for o in imported if o.type == "MESH"]
    R = Matrix.Rotation(math.radians(turn), 4, "Z") @ Matrix.Rotation(math.radians(tilt), 4, "X")
    out = []
    for i, o in enumerate(src):
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(R @ o.matrix_world)
        no = bpy.data.objects.new("SRC_%d" % i, me)
        no["src_name"] = o.name
        out.append(no)
    for o in imported:
        bpy.data.objects.remove(o, do_unlink=True)
    for o in out:
        bpy.context.scene.collection.objects.link(o)
        size = max(o.dimensions) or 1.0
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5 * size)   # glTF tach dinh o duong may UV
        bm.to_mesh(o.data)
        bm.free()
    return out


def _find_image(mat):
    if not mat or not mat.node_tree:
        return None, None
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    base = None
    if bsdf:
        bc = bsdf.inputs["Base Color"]
        base = tuple(bc.default_value[:3])
        seen, stack = set(), [l.from_node for l in bc.links]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            if n.type == "TEX_IMAGE" and n.image and n.image.size[0] > 0:
                return n.image, base
            for inp in n.inputs:
                stack += [l.from_node for l in inp.links]
    img = next((n.image for n in nodes if n.type == "TEX_IMAGE" and n.image and n.image.size[0] > 0), None)
    return img, base


_IMG_CACHE = {}


def _pixels(img):
    if img.name not in _IMG_CACHE:
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)[:, :, :3].astype(np.float64)
        if not img.is_float and img.colorspace_settings.name.lower().startswith("srgb"):
            px = _to_lin(px)
        _IMG_CACHE[img.name] = px
    return _IMG_CACHE[img.name]


def face_colors(obj):
    """(mau linear moi mat [F,3], nhan co dinh moi mat hoac None, dien tich [F])."""
    me = obj.data
    F = len(me.polygons)
    area = np.empty(F); me.polygons.foreach_get("area", area)
    mi = np.empty(F, dtype=np.int64); me.polygons.foreach_get("material_index", mi)
    ls = np.empty(F, dtype=np.int64); me.polygons.foreach_get("loop_start", ls)
    lt = np.empty(F, dtype=np.int64); me.polygons.foreach_get("loop_total", lt)
    L = len(me.loops)
    col = np.full((F, 3), 0.5)
    fixed = [None] * F
    uv = None
    if me.uv_layers:
        uv = np.empty(L * 2); me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(L, 2)
    vcol = None
    ca = me.color_attributes.active_color if hasattr(me, "color_attributes") else None
    if ca is not None:
        raw = np.empty(len(ca.data) * 4); ca.data.foreach_get("color", raw)
        raw = raw.reshape(-1, 4)[:, :3]
        if ca.domain == "CORNER":
            vcol = raw
        elif ca.domain == "POINT":
            lv = np.empty(L, dtype=np.int64); me.loops.foreach_get("vertex_index", lv)
            vcol = raw[lv]
    for slot in range(max(1, len(me.materials))):
        sel = np.where(mi == slot)[0]
        if len(sel) == 0:
            continue
        mat = me.materials[slot] if slot < len(me.materials) else None
        canon = std.canonical(mat.name) if mat else None
        if canon:
            for f in sel:
                fixed[f] = canon
            col[sel] = std.PALETTE_BY_MAT.get(canon, (0.5, 0.5, 0.5))
            continue
        img, base = _find_image(mat)
        if img is not None and uv is not None:
            px = _pixels(img)
            h, w = px.shape[:2]
            x = np.clip((np.mod(uv[:, 0], 1.0) * (w - 1)).astype(int), 0, w - 1)
            y = np.clip((np.mod(uv[:, 1], 1.0) * (h - 1)).astype(int), 0, h - 1)
            lc = px[y, x]
            for f in sel:
                a, n = ls[f], lt[f]
                cu = uv[a:a + n].mean(axis=0)
                cx = int(np.clip((cu[0] % 1.0) * (w - 1), 0, w - 1))
                cy = int(np.clip((cu[1] % 1.0) * (h - 1), 0, h - 1))
                col[f] = (lc[a:a + n].sum(axis=0) + 2 * px[cy, cx]) / (n + 2)
        elif vcol is not None:
            for f in sel:
                col[f] = vcol[ls[f]:ls[f] + lt[f]].mean(axis=0)
        elif base is not None:
            col[sel] = base
    return col, fixed, area
