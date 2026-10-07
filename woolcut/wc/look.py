"""Vat lieu va UV dung chung (buoc cat, panel, xuat):
- M/S: material TEN bang mau. Xem trong Blender nhu trong game = texture len dan (knit_basecolor.png, chep tu Unity)
  nhan mau that trong game (Highlight Unity x1.4 - theo PrimForge); mau phang (diffuse) = mau FBX bo goc.
- D: material Deco_mat + UV don vao MOT diem cua o mau tren Deco_Texture.png (85% D bo goc lam vay); diem chon
  trong 368 diem bo goc da dung (data/deco_points.json) theo mau gan nhat.
- Mau hien trong che do Solid: obj.color (viewport Color = Object) -> moi manh (ke ca D chung Deco_mat) dung mau."""
import os, re, json
import numpy as np
import bpy
from . import std, color

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
KNIT_TEX = os.path.join(DATA, "knit_basecolor.png")
DECO_TEX = os.path.join(DATA, "Deco_Texture.png")
DECO_POINTS = os.path.join(DATA, "deco_points.json")
_DECO = {}


def slot_of(mat_name):
    m = re.match(r"Color_(\d+)_", mat_name or "")
    return int(m.group(1)) if m else None


def deco_point(mat_name):
    """(u, v, dE): diem tren Deco_Texture cho mau bang `mat_name` (CIEDE2000 - 2 log10(so lan bo goc dung))."""
    if "pts" not in _DECO:
        with open(DECO_POINTS, encoding="utf-8") as fh:
            pts = [p for p in json.load(fh)["points"] if p["count"] >= 2]
        _DECO["pts"] = pts
        _DECO["lab"] = color._lab(color._to_lin(np.array([p["srgb"] for p in pts])))
    pts, labs = _DECO["pts"], _DECO["lab"]
    want = std.NOMINAL.get(slot_of(mat_name) or 15, (0.9, 0.9, 0.9))
    de = color.de2000(color._lab(color._to_lin(np.array([want]))), labs, 1.0)[0]
    i = int((de - 2.0 * np.log10(np.array([p["count"] for p in pts]))).argmin())
    return pts[i]["u"], pts[i]["v"], float(de[i])


def _image(path):
    if not os.path.exists(path):
        return None
    name = os.path.basename(path)
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.load(path, check_existing=True)
    return img


def game_rgb_lin(mat_name):
    """Mau nguoi choi thay (linear): Highlight Unity x1.4, cat 1."""
    c = np.array(std.game_rgb(mat_name), dtype=float) * 1.4
    return tuple(np.clip(c, 0, 1).tolist())


def palette_material(mat_name, game=True):
    """Material TEN bang mau. game=True: Base Color = texture len x mau trong game (xem nhu game, can UV);
    game=False: Base Color = mau FBX bo goc, khong texture (dung khi XUAT - giong het model mau)."""
    m = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    fbx = std.PALETTE_BY_MAT.get(mat_name) or std.nominal_lin(mat_name)
    bsdf.inputs["Roughness"].default_value = 0.553
    bsdf.inputs["Base Color"].default_value = (fbx[0], fbx[1], fbx[2], 1.0)
    knit = _image(KNIT_TEX) if game else None
    if knit is not None:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = std.UV_NAME
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = knit
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        g = game_rgb_lin(mat_name)
        mix.inputs[7].default_value = (g[0], g[1], g[2], 1.0)
        nt.links.new(uv.outputs[0], tex.inputs[0])
        nt.links.new(tex.outputs[0], mix.inputs[6])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    m.diffuse_color = (fbx[0], fbx[1], fbx[2], 1.0)
    return m


def deco_material():
    """Deco_mat nhu bo goc (ten khop Unity Game/Material/Deco_mat.mat), hien Deco_Texture theo UV."""
    m = bpy.data.materials.get(std.DECO_MAT)
    if m is None:
        m = bpy.data.materials.new(std.DECO_MAT)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        img = _image(DECO_TEX)
        if img is not None:
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.interpolation = "Closest"
            nt.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.553
    return m


def deco_uv(me, u, v):
    if not me.uv_layers:
        me.uv_layers.new(name=std.UV_NAME)
    me.uv_layers[0].name = std.UV_NAME
    me.uv_layers.active = me.uv_layers[0]
    me.uv_layers[0].data.foreach_set("uv", np.tile([u, v], len(me.loops)).astype(np.float32))


def show_color(ob, mat_name):
    """Mau o che do Solid (viewport Color = Object): mau FBX bo goc cua slot."""
    c = std.PALETTE_BY_MAT.get(mat_name) or std.nominal_lin(mat_name)
    ob.color = (c[0], c[1], c[2], 1.0)


def apply_piece(ob, kind, mat_name, unwrap=True, density=None):
    """Dat vat lieu + UV cho mot manh theo loai: D -> Deco (UV 1 diem); M/S -> bang mau + trai UV kieu bo goc."""
    from . import uv as uvmod
    ob["wc_color"] = mat_name
    ob.data.materials.clear()
    if kind == "D":
        ob.data.materials.append(deco_material())
        u, v, _ = deco_point(mat_name)
        deco_uv(ob.data, u, v)
    else:
        ob.data.materials.append(palette_material(mat_name))
        if unwrap:
            uvmod.unwrap([ob], density or std.UV_DENSITY)
    show_color(ob, mat_name)
