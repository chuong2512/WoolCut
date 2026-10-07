"""WoolCut - panel Blender (tab "WoolCut", phim N): 4 buoc bam tay
  1 Prompt (Claude)  ->  2 Model (Tripo)  ->  3 Tach manh (Claude lap ke hoach + cat phang)  ->  4 Dat ten S/M/D + FBX
Moi viec nang chay nen bang run.py (python he thong) - Blender khong bi treo; xong thi tu nap ket qua."""
bl_info = {
    "name": "WoolCut",
    "author": "Claude",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > WoolCut",
    "description": "Prompt -> Tripo -> Claude tach manh mot mau -> S/M/D FBX",
    "category": "Import-Export",
}

import os, re, sys, json, glob, shutil, subprocess, threading, collections, time
import bpy
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty, FloatProperty, CollectionProperty

ROOT = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(ROOT, "run.py")
COLL_MODEL = "WC 2 · Model"
COLL_PARTS = "WC 3 · Manh"
COLL_PREP = "WC 3 · Khoi"          # cac part / khoi roi sau buoc chuan bi - xem truoc ke hoach cat
LOG = collections.deque(maxlen=400)
# Hai O viec nen doc lap: "main" (tach, cat, gen, xuat) va "prompt" (Claude viet prompt) - nguoi dung 2026-10-02:
# dang tach van phai lay duoc prompt de dan len web Tripo.
# "batch" (2026-10-07): hang doi tach hang loat chay O RIENG - dang chay van bam duoc cac nut khac de soat model da xong
JOBS = {k: {"proc": None, "kind": "", "name": "", "lines": [], "t0": 0.0, "done": None}
        for k in ("main", "prompt", "batch")}
JOB = JOBS["main"]
# Model Claude cho tung chuc nang (nguoi dung 2026-10-07) - danh sach chuc nang + goi y nam o wc/planner.py
try:
    from .wc.planner import TASKS as CLAUDE_TASKS, RECOMMENDED as CLAUDE_RECOMMENDED
except Exception:
    CLAUDE_TASKS, CLAUDE_RECOMMENDED = [], {}
CLAUDE_MODELS = [("PRESET", "Theo chế độ", "Theo chế độ chung (Nhanh / Vừa / Kỹ)"),
                 ("DEFAULT", "Mặc định CLI", "Model mặc định của Claude CLI trên máy (settings.json)"),
                 ("OPUS", "Opus", "Mạnh, chậm hơn ~2 lần, tốn hơn ~3 lần Sonnet"),
                 ("SONNET", "Sonnet", "Nhanh, rẻ - hợp việc viết chữ"),
                 ("HAIKU", "Haiku", "Nhanh nhất, rẻ nhất, kém nhất"),
                 ("FABLE", "Fable", "Model mới nhất (claude-fable)")]
CLAUDE_EFFORTS = [("PRESET", "Theo chế độ", "Theo chế độ chung"), ("LOW", "low", ""), ("MEDIUM", "medium", ""),
                  ("HIGH", "high", ""), ("XHIGH", "xhigh", ""), ("MAX", "max", "")]
CLAUDE_TASK_HELP = {"prompt": "Viết prompt Tripo (bước 1)", "facing": "Tìm mặt trước khi nạp model",
                    "label": "Đặt tên tiếng Việt cho từng mảnh", "paint": "Tô màu theo bảng màu game",
                    "decor": "Gắn decor (mắt, má hồng, sao...)", "refine": "Tách sâu: xem cả model rồi từng bộ phận",
                    "piece": "Nút 'Claude chia mảnh đang chọn'", "plan": "Lập kế hoạch cắt cả model (luồng cũ)",
                    "review": "Soát kế hoạch cắt (luồng cũ)"}


def _prefs():
    try:
        return bpy.context.preferences.addons[__name__].preferences
    except (KeyError, AttributeError):
        return None


def _claude_models():
    """{chuc nang: [model, effort]} khac 'theo che do' -> bien WOOLCUT_MODELS cho tien trinh nen (wc/planner.model_for)."""
    p, out = _prefs(), {}
    if p is None:
        return out
    for k, _vi, _g in CLAUDE_TASKS:
        mo, ef = getattr(p, "m_" + k, "PRESET"), getattr(p, "e_" + k, "PRESET")
        if mo != "PRESET" or ef != "PRESET":
            out[k] = ["" if mo == "PRESET" else mo.lower(), "" if ef == "PRESET" else ef.lower()]
    return out


# ------------------------------------------------------------------ tien ich
def _python():
    """Python he thong (khong phai python cua Blender: run.py tu goi Blender headless)."""
    exe = sys.executable
    return exe if "python" in os.path.basename(exe).lower() else (shutil.which("python") or "python")


def _tripo_key():
    """Key Tripo: Preferences WoolCut > bien moi truong > Preferences PrimForge (chi doc)."""
    for mod in (__name__, "primforge"):
        try:
            k = bpy.context.preferences.addons[mod].preferences.tripo_key
            if k:
                return k
        except (KeyError, AttributeError):
            pass
    return os.environ.get("TRIPO_API_KEY", "")


def _env():
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        env["WOOLCUT_SPEED"] = bpy.context.scene.wc_speed.lower()
    except AttributeError:
        pass
    models = _claude_models()
    if models:
        env["WOOLCUT_MODELS"] = json.dumps(models)
    k = _tripo_key()
    if k:
        env["TRIPO_API_KEY"] = k
    return env


def _redraw():
    wm = bpy.context.window_manager
    for w in wm.windows:
        for a in w.screen.areas:
            if a.type in ("VIEW_3D", "PROPERTIES"):
                a.tag_redraw()


def _log(line):
    LOG.append(line.rstrip())


def _fresh(name):
    old = bpy.data.collections.get(name)
    if old:
        for o in list(old.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def _show_only(keep):
    for c in bpy.context.scene.collection.children:
        if c.name.startswith(("WC ", "PF ", "PrimForge")):
            lc = bpy.context.view_layer.layer_collection.children.get(c.name)
            if lc:
                lc.hide_viewport = c.name != keep


def part_objects():
    c = bpy.data.collections.get(COLL_PARTS)
    return sorted([o for o in c.all_objects if o.type == "MESH"], key=lambda o: o.name) if c else []


# ------------------------------------------------------------------ chay nen
def start_job(kind, name, args, done=None, slot="main"):
    J = JOBS[slot]
    if J["proc"] and J["proc"].poll() is None:
        return False
    cmd = [_python(), "-u", RUN] + args
    _log("$ run.py " + " ".join(args))
    proc = subprocess.Popen(cmd, cwd=os.path.dirname(ROOT), env=_env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    J.update(proc=proc, kind=kind, name=name, lines=[], t0=time.time(), done=done)

    def pump():
        for line in proc.stdout:
            J["lines"].append(line.rstrip())
            _log(line)
    th = threading.Thread(target=pump, daemon=True)
    th.start()
    J["thread"] = th
    import functools
    bpy.app.timers.register(functools.partial(_tick, slot), first_interval=0.5)
    return True


def _tick(slot="main"):
    J = JOBS[slot]
    p = J["proc"]
    _redraw()
    if p is None:
        return None
    if p.poll() is None:
        return 0.5
    th = J.get("thread")
    if th is not None:
        th.join(timeout=15)          # doc HET output (dong CUT_READY/SPLIT_READY o cuoi) roi moi xu ly ket qua
    rc = p.returncode
    J["proc"] = None
    _log("[xong] %s (%ds, ma %s)" % (J["kind"], time.time() - J["t0"], rc))
    fn = J.get("done")
    if fn:
        try:
            fn(rc, J["lines"])
        except Exception as e:                     # khong de loi nap ket qua lam hong timer
            import traceback
            traceback.print_exc()
            _log("[loi nap ket qua] %s" % e)
    _redraw()
    return None


def running(slot="main"):
    J = JOBS[slot]
    return J["proc"] is not None and J["proc"].poll() is None


def _wrap(text, width=44):
    out, cur = [], ""
    for w in (text or "").split():
        if len(cur) + len(w) + 1 > width:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out


def _grab(lines, key):
    for ln in reversed(lines):
        if ln.startswith(key):
            return ln.split(":", 1)[1].strip()
    return None


# ------------------------------------------------------------------ nap ket qua
def import_model(path, turn):
    coll = _fresh(COLL_MODEL)
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    piv = bpy.data.objects.new("WC_xoay", None)
    coll.objects.link(piv)
    import math
    piv.rotation_euler = (math.radians(getattr(bpy.context.scene, "wc_tilt", 0.0)), 0, math.radians(turn))
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        if o.parent is None:
            o.parent = piv
    _show_only(COLL_MODEL)


def _material_view():
    """Solid: moi manh hien dung mau cua no (Color = Object; D dung chung Deco_mat nen khong dung Material)."""
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == "VIEW_3D":
                sh = a.spaces.active.shading
                if sh.type == "SOLID":
                    sh.color_type = "OBJECT"


def load_parts(path):
    _material_view()
    UNDO.clear()
    old = bpy.data.collections.get(COLL_ARCH)
    if old:
        for o in list(old.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = _fresh(COLL_PARTS)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith("_")]
    for o in dst.objects:
        if o is not None and o.type == "MESH":
            coll.objects.link(o)
    _show_only(COLL_PARTS)
    try:
        apply_labels(bpy.context.scene)
    except Exception as e:
        _log("[dat ten] loi: %s" % e)
    try:
        n = apply_decor_json(bpy.context.scene)
        if n:
            _log("[decor] dat lai %d decor tu decor.json" % n)
    except Exception as e:
        _log("[decor] loi dat lai: %s" % e)
    return coll


def import_fbx_result(path, name):
    coll = _fresh("WC 4 · " + name)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    for o in [o for o in bpy.data.objects if o not in before]:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    _show_only(coll.name)


# ------------------------------------------------------------------ thao tac
def _sc():
    return bpy.context.scene


def model_name(path):
    """Ten model tu ten file: 'chibi witch cat 3d model.glb' -> ChibiWitchCat3dModel; bo duoi _xxxxxxxx cua Tripo."""
    base = re.sub(r"_[0-9a-f]{8}$", "", os.path.splitext(os.path.basename(path))[0])
    words = re.findall(r"[A-Za-z0-9]+", base)
    return "".join(w[:1].upper() + w[1:] for w in words)[:40] or "Model"


def _model_changed(self, ctx):
    if self.wc_model:
        self.wc_name = model_name(bpy.path.abspath(self.wc_model))
        self.wc_model_prompt = find_model_prompt(self)
        if getattr(self, "wc_autoload", False) and os.path.exists(bpy.path.abspath(self.wc_model)) and not running():
            sc = self

            def _later():                       # khong goi operator trong callback thuoc tinh -> hoan lai 1 nhip
                try:
                    import_model(bpy.path.abspath(sc.wc_model), sc.wc_turn)
                    if sc.wc_autochain:
                        chain_start(sc)
                    elif sc.wc_autoface:
                        start_facing(sc)
                except Exception as e:
                    _log("[nap model] loi: %s" % e)
                return None
            bpy.app.timers.register(_later, first_interval=0.05)


CHAIN = {"stage": None}            # tu chay het: None | "facing" | "split" | "refine" | "decor"


def chain_start(sc):
    """Bat dau chuoi tu dong sau khi nap model."""
    CHAIN["stage"] = "facing" if sc.wc_autoface else "split"
    sc.wc_decor_msg = "Tự chạy: tìm mặt trước…" if sc.wc_autoface else "Tự chạy: tách bộ phận…"
    if sc.wc_autoface:
        start_facing(sc)
    else:
        chain_next(sc, "split")


def chain_next(sc, stage):
    """Sang buoc tiep theo (hoan 0.3 s cho viec nen truoc giai phong)."""
    CHAIN["stage"] = stage

    def _go():
        if running():
            return 0.5                             # viec cu chua xong -> doi
        try:
            if stage == "split":
                sc.wc_decor_msg = "Tự chạy: tách bộ phận + đặt tên…"
                bpy.ops.woolcut.parts_only(reprep=False)
            elif stage == "refine":
                sc.wc_decor_msg = "Tự chạy: tách sâu từng bộ phận…"
                bpy.ops.woolcut.refine(auto=True)
            elif stage == "decor":
                sc.wc_decor_msg = "Tự chạy: Claude gắn decor…"
                bpy.ops.woolcut.decor_ai()
                CHAIN["stage"] = None
        except Exception as e:
            CHAIN["stage"] = None
            _log("[tu chay] dung o buoc %s: %s" % (stage, e))
            sc.wc_decor_msg = "Tự chạy dừng ở bước %s" % stage
        return None
    bpy.app.timers.register(_go, first_interval=0.3)


def find_model_prompt(sc):
    """Prompt cua model dang chon: work/<Ten>/prompt.txt > <Ten>.tripo.json canh file (buoc 2 ghi)."""
    from .wc import prompt as pr
    return pr.find_prompt(bpy.path.abspath(sc.wc_model), sc.wc_name, os.path.join(ROOT, "work", sc.wc_name))


class _Locked:
    """Khong bam duoc khi dang co viec chay nen (tranh ghi de giua chung)."""

    @classmethod
    def poll(cls, ctx):
        return not running()


class WC_OT_prompt(bpy.types.Operator):
    bl_idname = "woolcut.prompt"
    bl_label = "Claude viết prompt"
    bl_description = "Claude CLI viết prompt Tripo theo ý tưởng (để trống = Claude tự nghĩ). Không tốn credit. " \
                     "Chạy được cả khi đang tách mảnh"

    @classmethod
    def poll(cls, ctx):
        return not running("prompt")

    def execute(self, ctx):
        sc = ctx.scene

        mode = sc.wc_pmode

        def done(rc, lines):
            got = {}
            for ln in lines:
                for k in ("NAME", "PROMPT", "VI", "MODEL", "TOPOLOGY", "POLYCOUNT", "WHY", "CHECK"):
                    t = ln.strip().strip("*").strip()
                    if t.upper().startswith(k + ":"):
                        got[k] = t.split(":", 1)[1].strip().strip('"').strip("`")
            if got.get("PROMPT"):
                sc.wc_prompt = got["PROMPT"]
                # ten de dung KHI GUI TRIPO - khong doi o Ten cua model dang tach
                sc.wc_prompt_name = re.sub(r"[^A-Za-z0-9]", "", got.get("NAME", "Model"))[:40] or "Model"
                sc.wc_prompt_vi = got.get("VI", "")
                sc.wc_prompt_mode = mode
                sc.wc_prompt_check = got.get("CHECK", "") if mode == "IMAGE" else ""
                if got.get("POLYCOUNT", "").isdigit():
                    sc.wc_faces = int(got["POLYCOUNT"])
        if not start_job("prompt", sc.wc_name, ["prompt", "--idea", sc.wc_idea, "--kind", sc.wc_ptype.lower(),
                                                "--theme", sc.wc_theme.lower(), "--mode", mode.lower()], done,
                         slot="prompt"):
            self.report({"WARNING"}, "Đang chạy việc khác")
        return {"FINISHED"}


def full_prompt(sc):
    """Prompt + cau phong cach (tool tu noi khi goi API; dan len WEB Tripo thi phai co san).
    Prompt ANH: + cau khung anh (toan than, 3/4, nen tron, moi bo phan mot mau phang - wc/prompt.IMAGE_TAIL)."""
    from .wc import categories as cat, tripo, prompt
    style = cat.FORMATS.get(sc.wc_ptype.lower(), cat.FORMATS["char"])["style"]
    tail = prompt.IMAGE_TAIL if sc.wc_prompt_mode == "IMAGE" else tripo.STYLES.get(style, tripo.STYLE)
    p = sc.wc_prompt.strip()
    if p and not p.endswith("."):
        p += "."
    return (p + " " + tail[:1].upper() + tail[1:] + ".").strip()


class WC_OT_copy_prompt(bpy.types.Operator):
    bl_idname = "woolcut.copy_prompt"
    bl_label = "Copy prompt (dán lên web Tripo)"
    bl_description = "Chép prompt + câu phong cách vào clipboard. Prompt text: dán vào Text to 3D trên web Tripo. " \
                     "Prompt ảnh: dán vào công cụ tạo ảnh, soát ảnh rồi đưa vào Image to 3D"

    def execute(self, ctx):
        if not ctx.scene.wc_prompt.strip():
            self.report({"ERROR"}, "Chưa có prompt")
            return {"CANCELLED"}
        txt = full_prompt(ctx.scene)
        ctx.window_manager.clipboard = txt
        self.report({"INFO"}, "Đã chép prompt %s(%d ký tự)" % ("ảnh " if ctx.scene.wc_prompt_mode == "IMAGE" else "",
                                                             len(txt)))
        return {"FINISHED"}


class WC_OT_prompt_from_step1(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.prompt_from_step1"
    bl_label = "Lấy prompt ở bước 1"
    bl_description = "Dùng prompt bước 1 làm prompt của model này (khi đã dán prompt đó lên web Tripo)"

    def execute(self, ctx):
        sc = ctx.scene
        if not sc.wc_prompt.strip():
            self.report({"ERROR"}, "Bước 1 chưa có prompt")
            return {"CANCELLED"}
        sc.wc_model_prompt = sc.wc_prompt.strip()
        return {"FINISHED"}


class WC_OT_gen(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.gen"
    bl_label = "Tạo model bằng Tripo"
    bl_description = "Gửi prompt lên Tripo (TỐN CREDIT). Bấm 'Ước tính' trước để xem số credit"
    send: BoolProperty(default=False)

    def invoke(self, ctx, event):
        if self.send:
            return ctx.window_manager.invoke_confirm(self, event)
        return self.execute(ctx)

    def execute(self, ctx):
        sc = ctx.scene
        if not sc.wc_prompt.strip():
            self.report({"ERROR"}, "Chưa có prompt")
            return {"CANCELLED"}
        if sc.wc_prompt_mode == "IMAGE":               # prompt tao anh gui vao Text to 3D = phi credit
            self.report({"ERROR"}, "Đây là prompt ẢNH (dùng cho Image to 3D trên web). Muốn gửi Tripo: chọn kiểu "
                                   "Text → 3D ở bước 1 rồi viết lại")
            return {"CANCELLED"}
        from .wc import categories as cat
        style = cat.FORMATS.get(sc.wc_ptype.lower(), cat.FORMATS["char"])["style"]
        gname = sc.wc_prompt_name or sc.wc_name
        args = ["gen", "--name", gname, "--prompt", sc.wc_prompt, "--faces", str(sc.wc_faces), "--style", style]
        if self.send:
            args.append("--yes")

        def done(rc, lines):
            m = _grab(lines, "MODEL_READY")
            if m and os.path.exists(m):
                sc.wc_model = m
                sc.wc_turn = float(_grab(lines, "TURN") or -90)
                import_model(m, sc.wc_turn)
        start_job("gen", sc.wc_name, args, done)
        return {"FINISHED"}


class WC_OT_load_model(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.load_model"
    bl_label = "Nạp model có sẵn"
    bl_description = "Xem model (glb/fbx/obj) - ví dụ file tải từ web Tripo"

    def execute(self, ctx):
        sc = ctx.scene
        p = bpy.path.abspath(sc.wc_model)
        if not os.path.exists(p):
            self.report({"ERROR"}, "Không thấy file")
            return {"CANCELLED"}
        sc.wc_name = model_name(p)
        sc.wc_model_prompt = find_model_prompt(sc)
        import_model(p, sc.wc_turn)
        if sc.wc_autochain:
            chain_start(sc)
        elif sc.wc_autoface:
            start_facing(sc)
        return {"FINISHED"}


def _apply_turn(sc, deg, tilt=None):
    import math
    sc.wc_turn = ((float(deg) + 180) % 360) - 180
    if tilt is not None:
        sc.wc_tilt = ((float(tilt) + 180) % 360) - 180
    piv = bpy.data.objects.get("WC_xoay")
    if piv:
        piv.rotation_euler = (math.radians(sc.wc_tilt), 0, math.radians(sc.wc_turn))


def start_facing(sc):
    """Blender chup model 4 huong -> Claude chon mat truoc -> xoay (nguoi dung 2026-10-02)."""
    p = bpy.path.abspath(sc.wc_model)

    def done(rc, lines):
        t = _grab(lines, "TURN")
        if t is not None:
            _apply_turn(sc, t, _grab(lines, "TILT") or 0)
        if CHAIN["stage"] == "facing":
            chain_next(sc, "split")
    return start_job("facing", sc.wc_name, ["facing", "--in", p, "--name", sc.wc_name], done)


class WC_OT_facing(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.facing"
    bl_label = "Tự tìm mặt trước"
    bl_description = "Chụp model 4 hướng, Claude chọn hướng nhìn thấy mặt rồi xoay cho mặt trước về −Y (~20 giây)"

    def execute(self, ctx):
        if not os.path.exists(bpy.path.abspath(ctx.scene.wc_model)):
            self.report({"ERROR"}, "Chưa có model")
            return {"CANCELLED"}
        start_facing(ctx.scene)
        return {"FINISHED"}


class WC_OT_turn(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.turn"
    bl_label = "Xoay"
    deg: FloatProperty(default=90)
    tilt: FloatProperty(default=0)

    def execute(self, ctx):
        sc = ctx.scene
        _apply_turn(sc, sc.wc_turn + self.deg, sc.wc_tilt + self.tilt)
        return {"FINISHED"}


class WC_OT_split(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.split"
    bl_label = "Tách mảnh"
    bl_description = "Dựng khối kín + đọc màu -> Claude nhìn ảnh lập kế hoạch cắt -> cắt phẳng -> Claude soát"
    mode: EnumProperty(items=[("full", "Claude lập kế hoạch", ""), ("recut", "Cắt lại theo plan.json", ""),
                              ("review", "Claude soát & sửa", ""), ("reprep", "Làm lại từ đầu", ""),
                              ("paint", "Claude tô màu", "")])

    def execute(self, ctx):
        sc = ctx.scene
        p = bpy.path.abspath(sc.wc_model)
        name = sc.wc_name
        mm = ["--min", str(sc.wc_min), "--max", str(sc.wc_max), "--bevel", "%.3f" % sc.wc_bevel3, "--tiny", "%.4f" % (sc.wc_tiny / 100.0)]
        if self.mode != "recut":
            mm = mm + ["--prompt", sc.wc_model_prompt]       # Claude doc prompt de biet bo phan + mau y do
        if self.mode == "recut":
            args = ["cut", "--name", name] + mm
        elif self.mode == "paint":
            args = ["paint", "--name", name] + mm
        elif self.mode == "review":
            args = ["split", "--name", name, "--keep-plan", "--rounds", "1"] + mm
        else:
            if not os.path.exists(p):
                self.report({"ERROR"}, "Chưa có model (bước 2)")
                return {"CANCELLED"}
            args = ["split", "--in", p, "--name", name, "--turn", str(sc.wc_turn), "--tilt", str(sc.wc_tilt), "--rounds", str(sc.wc_rounds)] + mm
            if self.mode == "reprep":
                args.append("--reprep")
            if sc.wc_remesh:
                args += ["--remesh", "--reprep"]
            args.append("--paint" if sc.wc_autopaint else "--no-paint")

        def done(rc, lines):
            r = _grab(lines, "SPLIT_READY") or _grab(lines, "CUT_READY")
            if r and os.path.exists(r):
                load_parts(r)
        start_job("split", name, args, done)
        return {"FINISHED"}


SPLIT_PATTERNS = [
    ("AUTO", "Tự chọn (2–4 mảnh)", "Khối dài: 2–3 khúc theo chiều dài; khối dẹt: đôi; khối tròn: 4 múi"),
    ("HALF_X", "Đôi trái / phải", "Cắt dọc qua tâm (trái | phải)"),
    ("HALF_Y", "Đôi trước / sau", "Cắt dọc qua tâm (trước | sau)"),
    ("HALF_Z", "Đôi trên / dưới", "Cắt ngang qua tâm"),
    ("QUAD", "4 múi dọc", "Trái/phải × trước/sau"),
    ("OCT", "8 múi (như đầu gấu BearArt)", "Trái/phải × trước/sau × trên/dưới"),
    ("LAYERS", "Tầng ngang (N tầng)", "N lát ngang đều"),
    ("VSLICE", "Lát dọc (N lát)", "N lát dọc theo chiều dài nhất"),
    ("ORANGE", "Múi cam (N múi)", "N múi quanh trục đứng"),
    ("ORANGE_LONG", "Múi cam quanh trục dài (N)", "Khối nằm ngang: trống, đuôi, ống"),
    ("ORANGE_LAYERS", "Múi cam × tầng (N × M)", "Như Totoro: 4 múi × 3 tầng"),
    ("GRID", "Lưới (N × N × M)", "Ô vuông theo cả 3 trục"),
    ("CUR_X", "Cắt tại con trỏ 3D ⟂ X", "Mặt phẳng qua con trỏ 3D (Shift+chuột phải đặt), vuông góc trục X"),
    ("CUR_Y", "Cắt tại con trỏ 3D ⟂ Y", "Mặt phẳng qua con trỏ 3D, vuông góc trục Y"),
    ("CUR_Z", "Cắt tại con trỏ 3D ⟂ Z", "Mặt phẳng qua con trỏ 3D, vuông góc trục Z (vd cắt vạt thừa dưới yên)"),
]


_DRAW = {"handle": None, "cache": {}}


def _tris(ob):
    """Tam giac cua mesh (loop triangles) - de tinh truc khoi giong loi cat (wc.tm.piece_frame)."""
    import numpy as np
    me = ob.data
    me.calc_loop_triangles()
    F = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", F)
    return F.reshape(-1, 3) if len(F) else None


def _preview_geom(ob, sc):
    """Mat phang xem truoc (tam giac) cho kieu chia dang chon + canh cua manh (de lam noi)."""
    import numpy as np
    import math
    from .wc.tm import piece_frame
    W = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    if not len(W):
        return [], []
    R = _user_rot(sc) @ (np.eye(3) if sc.wc_split_world else piece_frame(W, _tris(ob)))   # + xoay tay
    W0 = W.mean(0)
    V = (W - W0) @ R                                                 # toa do trong he truc khoi
    lo, hi = V.min(0), V.max(0)
    c = V.mean(0)
    s = float((hi - lo).max()) * 0.62
    n_, m_ = sc.wc_split_n, sc.wc_split_m
    dims = hi - lo
    pat = sc.wc_split_pattern
    E = np.eye(3)
    planes = []                                    # (diem, phap tuyen, None) day du | (tam, truc, huong) nua

    def full(p, nrm):
        planes.append((np.asarray(p, float), np.asarray(nrm, float), None))
    if pat == "AUTO":
        a = _auto_split(dims)
        if a[0] == "LONG":
            for i in range(1, a[1]):
                q = c.copy()
                q[a[2]] = lo[a[2]] + dims[a[2]] * i / a[1]
                full(q, E[a[2]])
        elif a[0] == "HALF":
            full(c, E[a[2]])
        else:
            full(c, E[0])
            full(c, E[1])
    if pat in ("CUR_X", "CUR_Y", "CUR_Z"):
        k = "XYZ".index(pat[-1])
        cur = np.array(bpy.context.scene.cursor.location)
        full(R.T @ (cur - W0), R.T @ np.eye(3)[k])
    if pat in ("HALF_X", "QUAD", "OCT"):
        full(c, E[0])
    if pat in ("HALF_Y", "QUAD", "OCT"):
        full(c, E[1])
    if pat in ("HALF_Z", "OCT"):
        full(c, E[2])
    if pat == "LAYERS":
        for i in range(1, n_):
            full([c[0], c[1], lo[2] + dims[2] * i / n_], E[2])
    if pat == "VSLICE":
        k = 0 if dims[0] >= dims[1] else 1
        for i in range(1, n_):
            q = c.copy()
            q[k] = lo[k] + dims[k] * i / n_
            full(q, E[k])
    if pat == "GRID":
        for k, cnt in ((0, n_), (1, n_), (2, m_)):
            for i in range(1, cnt):
                q = c.copy()
                q[k] = lo[k] + dims[k] * i / cnt
                full(q, E[k])
    if pat in ("ORANGE", "ORANGE_LAYERS", "ORANGE_LONG"):
        ax = E[2] if pat != "ORANGE_LONG" else E[int(np.argmax(dims))]
        a0 = np.array([1.0, 0, 0]) if abs(ax[0]) < 0.9 else np.array([0, 1.0, 0])
        e1 = np.cross(ax, a0)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(ax, e1)
        for i in range(n_):
            a = 2 * math.pi * i / n_
            planes.append((c, ax, math.cos(a) * e1 + math.sin(a) * e2))
        if pat == "ORANGE_LAYERS":
            for i in range(1, m_):
                full([c[0], c[1], lo[2] + dims[2] * i / m_], E[2])
    planes = [(W0 + R @ p, R @ a, None if d is None else R @ d) for p, a, d in planes]
    tris, lines = [], []
    for p, a, d in planes:
        if d is None:                              # mat phang day du: hinh vuong canh 2s
            u = np.cross(a, [0, 0, 1.0] if abs(a[2]) < 0.9 else [1.0, 0, 0])
            u /= np.linalg.norm(u)
            w = np.cross(a, u)
            q = [p + s * (su * u + sw * w) for su, sw in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        else:                                      # nua mat phang tu truc ra ngoai (mui cam)
            q = [p - s * a, p + s * a, p + s * a + s * d, p - s * a + s * d]
        tris += [q[0], q[1], q[2], q[0], q[2], q[3]]
        lines += [q[0], q[1], q[1], q[2], q[2], q[3], q[3], q[0]]
    return [tuple(x) for x in tris], [tuple(x) for x in lines]


def _draw_preview():
    try:
        _draw_plan()
    except Exception as e:
        _DRAW["err"] = repr(e)
    try:
        sc = bpy.context.scene
        ob = bpy.context.active_object
        if not getattr(sc, "wc_split_preview", False) or not ob or ob.type != "MESH" or ob not in part_objects():
            return
        import gpu
        from gpu_extras.batch import batch_for_shader
        sh = gpu.shader.from_builtin("UNIFORM_COLOR")
        key = (ob.name, len(ob.data.vertices), tuple(round(x, 4) for x in ob.matrix_world.translation))
        ed = _DRAW["cache"].get(key)
        if ed is None:
            mw = ob.matrix_world
            ed = [tuple(mw @ ob.data.vertices[i].co) for e in ob.data.edges for i in e.vertices]
            _DRAW["cache"] = {key: ed}
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        gpu.state.line_width_set(1.5)
        b = batch_for_shader(sh, "LINES", {"pos": ed})
        sh.bind()
        sh.uniform_float("color", (1.0, 0.82, 0.1, 0.55))        # lam noi manh dang chon (vien vang)
        b.draw(sh)
        tris, lines = _preview_geom(ob, sc)
        if tris:
            gpu.state.depth_test_set("LESS_EQUAL")
            b = batch_for_shader(sh, "TRIS", {"pos": tris})
            sh.uniform_float("color", (1.0, 0.15, 0.25, 0.28))   # mat phang cat (do trong)
            b.draw(sh)
            gpu.state.depth_test_set("NONE")
            gpu.state.line_width_set(2.0)
            b = batch_for_shader(sh, "LINES", {"pos": lines})
            sh.uniform_float("color", (1.0, 0.15, 0.25, 0.9))
            b.draw(sh)
        gpu.state.blend_set("NONE")
        gpu.state.line_width_set(1.0)
        _DRAW["calls"] = _DRAW.get("calls", 0) + 1
    except Exception as e:                       # khong lam vo viewport; ghi lai de soat
        _DRAW["err"] = repr(e)


def _piece_anchor(ob):
    """Diem tren be mat manh (tam mat lon nhat) - thao tac trong plan.json chon dung manh nay khi cat lai."""
    best = max(ob.data.polygons, key=lambda p: p.area)
    return [float(x) for x in (ob.matrix_world @ best.center)]


def _recut(sc):
    def done(rc, lines):
        r = _grab(lines, "CUT_READY")
        if r and os.path.exists(r):
            load_parts(r)
    start_job("split", sc.wc_name, ["cut", "--name", sc.wc_name, "--min", str(sc.wc_min), "--max", str(sc.wc_max)],
              done)


def _auto_split(dims):
    """Kieu chia mac dinh 2-4 manh (nguoi dung 2026-10-05): dai -> 2-3 khuc theo chieu dai; det -> doi; tron -> 4 mui."""
    import numpy as np
    d = sorted([float(x) for x in dims], reverse=True)
    if d[0] >= 1.8 * max(d[1], 1e-9):
        return ("LONG", 3 if d[0] >= 3.2 * d[1] else 2, int(np.argmax(dims)))
    if d[2] < 0.4 * max(d[1], 1e-9):
        return ("HALF", 2, int(np.argmax(dims)))
    return ("QUAD", 4, -1)


def _split_op(ob, sc):
    """Thao tac chia cho manh `ob` theo kieu dang chon tren panel."""
    import numpy as np
    from .wc.tm import piece_frame
    n, m = sc.wc_split_n, sc.wc_split_m
    W = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    R = _user_rot(sc) @ (np.eye(3) if sc.wc_split_world else piece_frame(W, _tris(ob)))
    L = W @ R
    dims = L.max(0) - L.min(0)                     # kich thuoc theo he truc khoi (khoi nghieng: truc dai = truc khoi)
    long_h = "x" if dims[0] >= dims[1] else "y"
    long3 = "xyz"[max(range(3), key=lambda i: dims[i])]
    pat = sc.wc_split_pattern
    if pat == "AUTO":
        a = _auto_split(dims)
        op = dict(op="slices", axis="long", n=a[1]) if a[0] == "LONG" else \
            dict(op="split", axes=[long3]) if a[0] == "HALF" else dict(op="split", axes=["x", "y"])
        anc = _piece_anchor(ob)
        op.update({"target": anc, "anchor": anc, "manual": True, "label": "%s tu chon" % ob.name})
        return op
    op = {"HALF_X": dict(op="split", axes=["x"]), "HALF_Y": dict(op="split", axes=["y"]),
          "HALF_Z": dict(op="split", axes=["z"]), "QUAD": dict(op="split", axes=["x", "y"]),
          "OCT": dict(op="split", axes=["x", "y", "z"]), "LAYERS": dict(op="slices", axis="z", n=n),
          "VSLICE": dict(op="slices", axis=long_h, n=n), "ORANGE": dict(op="sectors", n=n, axis="z"),
          "ORANGE_LONG": dict(op="sectors", n=n, axis=long3),
          "ORANGE_LAYERS": dict(op="sectors", n=n, axis="z", layers=m),
          "GRID": dict(op="grid", grid=[n, n, m]),
          "CUR_X": dict(op="split", normals=[[1, 0, 0]], center=list(bpy.context.scene.cursor.location)),
          "CUR_Y": dict(op="split", normals=[[0, 1, 0]], center=list(bpy.context.scene.cursor.location)),
          "CUR_Z": dict(op="split", normals=[[0, 0, 1]], center=list(bpy.context.scene.cursor.location))}[pat]
    rot = [float(x) for x in sc.wc_split_rot]
    if pat.startswith("CUR_"):                      # mat phang qua con tro: xoay phap tuyen truc tiep
        op["normals"] = [list(_user_rot(sc) @ np.array(op["normals"][0], float))]
    elif any(abs(x) > 1e-6 for x in rot) or sc.wc_split_world:
        op["rot"] = rot
        if sc.wc_split_world:
            op["rot_world"] = True
    anc = _piece_anchor(ob)
    op.update({"target": anc, "anchor": anc, "manual": True, "label": "%s %s" % (ob.name, pat.lower())})
    return op


def _user_rot(sc):
    """Ma tran xoay tay cua mat cat (do, quanh truc the gioi)."""
    import numpy as np
    import math
    from mathutils import Euler
    r = [math.radians(float(x)) for x in sc.wc_split_rot]
    return np.array(Euler(r).to_matrix())


class WC_OT_split_rot_reset(bpy.types.Operator):
    bl_idname = "woolcut.split_rot_reset"
    bl_label = "Đặt lại góc cắt"

    def execute(self, ctx):
        ctx.scene.wc_split_rot = (0.0, 0.0, 0.0)
        return {"FINISHED"}


def _rot_changed(self, ctx):
    _DRAW["cache"] = {}
    for w in ctx.window_manager.windows:
        for a in w.screen.areas:
            if a.type == "VIEW_3D":
                a.tag_redraw()


COLL_ARCH = "WC 3 · Goc (an)"     # mesh cu truoc moi lan chia / ghep / mesh lai / xoa - hoan tac tuc thi
UNDO = []                          # [{"orig": [ten object luu], "new": [ten object moi], "nops": so op plan truoc do}]
                                   # + "colors": {ten: mau cu}, "plan_ops": ops plan.json cu (Claude to mau)


def _plan_len(sc):
    pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
    try:
        return len(json.load(open(pj, encoding="utf-8")).get("ops", []))
    except (OSError, ValueError):
        return None


def _archive(objs):
    """Cat object vao collection an (khong xoa) de hoan tac. Tra ve ten."""
    coll = bpy.data.collections.get(COLL_ARCH)
    if coll is None:
        coll = bpy.data.collections.new(COLL_ARCH)
        bpy.context.scene.collection.children.link(coll)
    lc = bpy.context.view_layer.layer_collection.children.get(COLL_ARCH)
    if lc:
        lc.exclude = True
    names = []
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        names.append(o.name)
    return names


def _push_undo(orig_names, new_objs, nops):
    UNDO.append({"orig": list(orig_names), "new": [o.name for o in new_objs], "nops": nops})
    del UNDO[:-30]


def _undo_last(sc):
    """Tra lai buoc gan nhat: xoa manh moi, dua mesh cu ve, cat plan.json ve nhu truoc. Tuc thi."""
    if not UNDO:
        return False
    e = UNDO.pop()
    if e.get("colors"):                              # Claude to mau: tra mau cu tung manh
        from .wc import look
        for n, m in e["colors"].items():
            o = bpy.data.objects.get(n)
            if o is not None and m:
                look.apply_piece(o, _kind(o), m, unwrap=False)
    pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
    if e.get("plan_ops") is not None and os.path.exists(pj):
        plan = json.load(open(pj, encoding="utf-8"))
        plan["ops"] = e["plan_ops"]
        json.dump(plan, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for n, h in e.get("hosts", {}).items():          # tach vo da doi manh chu cua mieng dan D -> tra lai
        o = bpy.data.objects.get(n)
        if o is not None and h:
            o["wc_host"] = h
    rows = _decor_entries(sc)
    drop_uid = set()
    for n in e["new"]:
        o = bpy.data.objects.get(n)
        if o is not None:
            if o.get("wc_decor_uid"):
                drop_uid.add(o["wc_decor_uid"])
            bpy.data.objects.remove(o, do_unlink=True)
    for n in e["orig"]:
        o = bpy.data.objects.get(n)
        if o is not None and o.get("wc_decor_entry"):
            try:
                rows.append(json.loads(o["wc_decor_entry"]))
            except ValueError:
                pass
            del o["wc_decor_entry"]
    if drop_uid or any(bpy.data.objects.get(n) is not None and bpy.data.objects[n].get("wc_decor") for n in e["orig"]):
        _decor_save(sc, [r for r in rows if r.get("uid") not in drop_uid])
    parts = bpy.data.collections.get(COLL_PARTS)
    back = []
    for n in e["orig"]:
        o = bpy.data.objects.get(n)
        if o is None:
            continue
        for c in list(o.users_collection):
            c.objects.unlink(o)
        parts.objects.link(o)
        if o.name.endswith(" (cu)"):
            o.name = o.name[:-5]
        back.append(o)
    pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
    if e["nops"] is not None and os.path.exists(pj):
        plan = json.load(open(pj, encoding="utf-8"))
        plan["ops"] = plan.get("ops", [])[:e["nops"]]
        json.dump(plan, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in back:
        o.select_set(True)
    if back:
        bpy.context.view_layer.objects.active = back[0]
    _DRAW["cache"] = {}
    return True


def apply_labels(sc):
    """labels.json (Claude dat ten) -> doi ten manh 'P05 tai trai' theo diem neo gan nhat; sua wc_host theo ten moi."""
    path = os.path.join(ROOT, "work", sc.wc_name, "labels.json")
    if not os.path.exists(path):
        return 0
    from mathutils import Vector
    rows = json.load(open(path, encoding="utf-8"))
    objs = part_objects()
    ren = {}
    for r in rows:
        if not r.get("anchor") or not r.get("label"):
            continue
        q = Vector(r["anchor"])
        best, bd = None, None
        for o in objs:
            ok, loc, nrm, idx = o.closest_point_on_mesh(o.matrix_world.inverted() @ q)
            if not ok:
                continue
            dd = ((o.matrix_world @ loc) - q).length
            if bd is None or dd < bd:
                best, bd = o, dd
        if best is None or best.name in ren:
            continue
        pre = best.name.split(" ")[0]
        ren[best.name] = (best, "%s %s" % (pre, r["label"]), r["label"])
    old2new = {}
    for old, (o, new, lab) in ren.items():
        o.name = new
        o["wc_label"] = lab
        old2new[old] = o.name
    for o in objs:
        h = o.get("wc_host")
        if h in old2new:
            o["wc_host"] = old2new[h]
    return len(ren)


def _live_split(ob, op, labels=None, rest_label=""):
    """Cat NGAY trong Blender bang dung loi woolcut (wc.tm / wc.plan) -> manh moi (vat lieu + UV chuan).
    labels = [{"tip": diem, "label": ten}] (tach sau): manh gan diem nhat mang ten do; manh con lai lon nhat = rest_label."""
    import numpy as np
    from .wc import bl, plan as planmod, look, std
    col = ob.get("wc_color") or std.canonical(ob.data.materials[0].name if ob.data.materials else "") \
        or std.mat_name(15, "White")
    bpy.context.view_layer.update()              # matrix_world cu ngay sau khi nap manh -> manh moi lech vi tri
    t = bl.tm_from_mesh(ob.data, ob.matrix_world)
    t.col = np.zeros(len(t.F), np.int64)
    R = planmod.Run([t], [col], verbose=False)
    for o_ in (op if isinstance(op, list) else [op]):       # mot thao tac hoac ca ke hoach (Claude chia manh)
        try:
            getattr(R, "op_" + o_["op"])(dict(o_, force=True))
        except Exception as e:
            R.say("  !! %s: %s" % (o_.get("label", o_.get("op")), e))
    v0 = abs(t.volume()) or 1e-9                 # vun the tich 0 con sot trong manh cu (bo cong cu) -> khong thanh manh
    R.pieces = [pc for pc in R.pieces if abs(pc.tm.volume()) >= 0.002 * v0 or len(pc.tm.F) >= 30]
    if len(R.pieces) < 2:
        return [], R.log
    allp = part_objects()
    lo = np.min([np.array(o.bound_box).min(0) for o in allp], axis=0)
    hi = np.max([np.array(o.bound_box).max(0) for o in allp], axis=0)
    side = float((hi - lo).max()) or 10.0
    forced = ob.get("wc_kind")
    coll = ob.users_collection[0]
    base = ob.name
    new = []
    for i, pc in enumerate(R.pieces):
        tm2 = pc.tm
        if (forced or "") != "D" and bpy.context.scene.wc_bevel3 > 0:
            from .wc import fillet as FL
            tm2 = FL.fillet(pc.tm, bpy.context.scene.wc_bevel3, log=_log)
        o2 = bl.object_from_tm(tm2, "%s.%d" % (base, i + 1), coll=coll, per_face=False)
        from .wc import uv as uvmod
        uvmod.center_origin(o2)
        lo2, hi2 = pc.tm.bbox()
        kind = forced or std.classify((hi2 - lo2).tolist(), side)
        o2["wc_kind_auto"] = kind
        if forced:
            o2["wc_kind"] = forced
        look.apply_piece(o2, kind, col, unwrap=True, density=_uv_density())
        new.append(o2)
    if labels is not None:
        _name_pieces(ob, new, [pc.tm for pc in R.pieces], labels, rest_label)
    _push_undo(_archive([ob]), new, _plan_len(bpy.context.scene))
    return new, R.log


def _name_pieces(ob, new, tms, labels, rest_label):
    """Gan ten Claude dat cho tung manh moi. Moi nhan mang cac diem SAT BIEN phia phan tach ("pts"); moi diem bo phieu
    cho manh co be mat gan nhat (BVH, khoang cach that) -> manh nhieu phieu nhat mang ten. Mot diem 'tip' thi sai khi
    cat long nhau (xe ga 2026-10-06: dau mut cua yem truoc nam tren hoc do da cat truoc -> hoc do mang ten yem)."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    pre = ob.name.split(" ")[0]
    parent = ob.get("wc_label") or (ob.name.split(" ", 1)[1] if " " in ob.name else "")
    bvhs = [BVHTree.FromPolygons([Vector(v) for v in t.V], [tuple(int(i) for i in f) for f in t.F], all_triangles=True)
            for t in tms]
    pairs = []
    for li, lb in enumerate(labels):
        pts = lb.get("pts") or ([lb["tip"]] if lb.get("tip") else [])
        if not pts or not lb.get("label"):
            continue
        votes = [0] * len(tms)
        dsum = [0.0] * len(tms)
        for q in pts:
            ds = [(bv.find_nearest(Vector([float(x) for x in q]))[3] or 1e9) for bv in bvhs]
            k = min(range(len(ds)), key=lambda i: ds[i])
            votes[k] += 1
            dsum[k] += ds[k]
        for oi in range(len(tms)):
            if votes[oi]:
                pairs.append((-votes[oi], dsum[oi] / votes[oi], li, oi))
    got, used = {}, set()
    for _, _, li, oi in sorted(pairs):
        if li in used or oi in got:
            continue
        got[oi] = labels[li]["label"]
        used.add(li)
    rest = [oi for oi in range(len(new)) if oi not in got]
    if rest:
        big = max(rest, key=lambda oi: len(tms[oi].F))
        got[big] = rest_label or parent
        for oi in rest:
            got.setdefault(oi, parent)
    for oi, o2 in enumerate(new):
        lab = got.get(oi) or parent
        o2.name = ("%s.%d %s" % (pre, oi + 1, lab)).strip()
        if lab:
            o2["wc_label"] = lab


def _save_labels(sc):
    """labels.json <- ten hien tai cua moi manh (diem neo = tam mat lon nhat) - nap lai / cat lai van giu ten."""
    rows = [{"name": o.name, "anchor": _piece_anchor(o), "label": o["wc_label"]}
            for o in part_objects() if o.get("wc_label") and not o.get("wc_decor")]
    if not rows:
        return
    path = os.path.join(ROOT, "work", sc.wc_name, "labels.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)


def _piece_vol(ob):
    import numpy as np
    F = _tris(ob)
    if F is None:
        return 0.0
    W = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    a, b, c = W[F[:, 0]], W[F[:, 1]], W[F[:, 2]]
    return abs(float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)


def refine_targets(objs=None):
    """Manh dang xem them: M/S, >= wc_refine_min % the tich model, chua bi Claude ket luan 'khong tach'."""
    allp = [o for o in part_objects() if not o.get("wc_decor")]
    vols = {o.name: _piece_vol(o) for o in allp}
    tot = sum(vols.values()) or 1e-9
    lim = bpy.context.scene.wc_refine_min / 100.0
    out = []
    for o in (objs if objs is not None else allp):
        if o.name not in vols or o.get("wc_refined") or (o.get("wc_kind") or o.get("wc_kind_auto")) == "D":
            continue
        if vols[o.name] / tot >= lim and len(o.data.polygons) >= 120:
            out.append(o)
    return out


def start_refine(sc, names, round_=1, hint="", force=False, hints=None, then=None):
    """Mot vong TACH SAU: chup + do nep tung manh (Blender nen) -> Claude chon song song -> cat ngay trong canh (Hoan tac
    duoc). Xong vong: manh moi con lon -> vong ke (toi wc_refine_rounds); het -> chuoi tu chay sang gan decor."""
    work = os.path.join(ROOT, "work", sc.wc_name)
    os.makedirs(work, exist_ok=True)
    path = os.path.join(work, "refine_in.blend")
    bpy.context.view_layer.update()
    bpy.data.libraries.write(path, set(o for o in part_objects() if not o.get("wc_decor")), fake_user=False)
    sc.wc_decor_msg = "Tách sâu vòng %d: Claude xem %d bộ phận…" % (round_, len(names))
    args = ["refine", "--name", sc.wc_name, "--in", path, "--pieces", "|".join(names), "--prompt", sc.wc_model_prompt]
    if hint.strip():
        args += ["--hint", hint]
    if force:
        args.append("--force")
    if hints:                                     # yeu cau rieng tung manh (buoc xem ca model)
        hp = os.path.join(work, "refine_hints.json")
        with open(hp, "w", encoding="utf-8") as fh:
            json.dump(hints, fh, ensure_ascii=False, indent=1)
        args += ["--hints", hp]

    def done(rc, lines):
        p = _grab(lines, "REFINE_READY")
        made, nsplit = [], 0
        if p and os.path.exists(p):
            plan = json.load(open(p, encoding="utf-8"))
            for e in plan.get("pieces", []):
                o = bpy.data.objects.get(e["name"])
                if o is None:
                    continue
                if not e.get("ops"):
                    o["wc_refined"] = 1
                    continue
                ops = [dict(x, manual=True, refine=round_) for x in e["ops"]]
                new, log = _live_split(o, ops, labels=e.get("labels", []), rest_label=e.get("rest", ""))
                for ln in log[-8:]:
                    _log(ln)
                if not new:
                    o["wc_refined"] = 1
                    _log("[tach sau] %s: khong cat duoc" % e["name"])
                    continue
                nsplit += 1
                made += new
                _append_plan_ops(sc, ops)
                _log("[tach sau] %s -> %d manh: %s" % (e["name"], len(new), e.get("notes", "")))
            _save_labels(sc)
        else:
            _log("[tach sau] khong co ket qua (ma %s)" % rc)
        sc.wc_decor_msg = "Tách sâu vòng %d: tách %d bộ phận → %d mảnh mới" % (round_, nsplit, len(made))
        if then is not None:
            then(made)
            return
        nxt = refine_targets(made) if made and round_ < sc.wc_refine_rounds else []
        if nxt:
            start_refine(sc, [o.name for o in nxt], round_ + 1)
            return
        if CHAIN["stage"] == "refine":
            chain_next(sc, "decor")
    if not start_job("refine", sc.wc_name, args, done):
        return False
    return True


STRUCT = {"history": []}


def start_struct(sc, it=1):
    """Mot lan XEM CA MODEL: chup ca model (ma manh in tren manh) -> Claude doi chieu bo phan chuan -> doi ten, ghep (khoi
    tron), tach (theo nep + yeu cau, qua start_refine) -> lan sau. Dung khi khong con gi sua / het wc_refine_rounds."""
    if it == 1:
        STRUCT["history"] = []
    work = os.path.join(ROOT, "work", sc.wc_name)
    os.makedirs(work, exist_ok=True)
    path = os.path.join(work, "struct_in.blend")
    bpy.context.view_layer.update()
    bpy.data.libraries.write(path, set(o for o in part_objects() if not o.get("wc_decor")), fake_user=False)
    sc.wc_decor_msg = "Xem cả model lần %d: Claude đối chiếu bộ phận…" % it
    args = ["struct", "--name", sc.wc_name, "--in", path, "--it", str(it), "--prompt", sc.wc_model_prompt]
    if STRUCT["history"]:
        args += ["--history", "; ".join(STRUCT["history"][-12:])]

    def finish():
        _save_labels(sc)
        if CHAIN["stage"] == "refine":
            chain_next(sc, "decor")

    def done(rc, lines):
        p = _grab(lines, "STRUCT_READY")
        if not p or not os.path.exists(p):
            _log("[xem ca model] khong co ke hoach (ma %s)" % rc)
            sc.wc_decor_msg = "Xem cả model lỗi (xem Nhật ký)"
            finish()
            return
        plan = json.load(open(p, encoding="utf-8"))
        nren = 0
        for r in plan.get("rename", []):
            o = bpy.data.objects.get(r["piece"])
            if o is not None:
                o.name = "%s %s" % (o.name.split(" ")[0], r["label"])
                o["wc_label"] = r["label"]
                nren += 1
        nmer = 0
        for m in plan.get("merge", []):
            objs = [bpy.data.objects.get(n) for n in m["pieces"]]
            if all(o is not None for o in objs) and _merge_pieces(sc, objs, m["label"]):
                nmer += 1
                STRUCT["history"].append("da ghep %s -> %s" % (" + ".join(n.split(" ")[0] for n in m["pieces"]),
                                                               m["label"]))
        hints = {}
        for s_ in plan.get("split", []):
            o = bpy.data.objects.get(s_["piece"])
            if o is not None:
                hints[o.name] = {"want": s_["want"], "parts": s_.get("parts", [])}
                STRUCT["history"].append("da yeu cau tach %s: %s" % (o.name.split(" ")[0], ", ".join(s_.get("parts", []))))
        _log("[xem ca model] lan %d: doi ten %d, ghep %d, tach %d - %s" % (it, nren, nmer, len(hints), plan.get("notes", "")))
        sc.wc_decor_msg = "Xem cả model lần %d: đổi tên %d, ghép %d, tách %d" % (it, nren, nmer, len(hints))
        if not hints:
            finish()
            return

        def after(made):
            if it < sc.wc_refine_rounds:
                start_struct(sc, it + 1)
            else:
                finish()
        start_refine(sc, list(hints), round_=sc.wc_refine_rounds, hints=hints, then=after)
    return start_job("struct", sc.wc_name, args, done)


def _merge_pieces(sc, objs, label):
    """GHEP thanh MOT khoi tron (vd vo mu trum co tai + mat = cai dau): gop luoi roi dung lai bang voxel (hop khoi, bo mat
    trong / ke ho), mau + loai theo manh lon nhat. Manh cu cat vao kho an (Hoan tac duoc); plan.json ghi merge + remesh."""
    import numpy as np
    from .wc import bl, look, std, uv as uvmod
    from .wc.tm import TM
    bpy.context.view_layer.update()
    tms = [bl.tm_from_mesh(o.data, o.matrix_world) for o in objs]
    big = max(range(len(objs)), key=lambda i: abs(tms[i].volume()))
    base = objs[big]
    off = np.cumsum([0] + [len(t.V) for t in tms[:-1]])
    t = TM(np.concatenate([t.V for t in tms]), np.concatenate([t.F + o for t, o in zip(tms, off)]))
    size = float((t.V.max(0) - t.V.min(0)).max()) or 1.0
    vox = size / 140.0
    t2 = bl.voxel_rebuild(t, voxel=vox, target_faces=max(1200, len(t.F)))
    if t2 is None:
        _log("[ghep] dung lai voxel loi - giu nguyen cac vo")
        t2 = t
    col = base.get("wc_color") or std.canonical(base.data.materials[0].name if base.data.materials else "") \
        or std.mat_name(15, "White")
    o2 = bl.object_from_tm(t2, "%s %s" % (base.name.split(" ")[0], label), coll=base.users_collection[0],
                           per_face=False)
    uvmod.center_origin(o2)
    kind = base.get("wc_kind") or base.get("wc_kind_auto", "M")
    o2["wc_kind_auto"] = kind
    if base.get("wc_kind"):
        o2["wc_kind"] = base["wc_kind"]
    if base.get("wc_color"):
        o2["wc_color"] = base["wc_color"]
    o2["wc_label"] = label
    look.apply_piece(o2, kind, col, unwrap=True, density=_uv_density())
    anchors = [_piece_anchor(o) for o in objs]
    nops = _plan_len(sc)
    _push_undo(_archive(objs), [o2], nops)
    _append_plan_ops(sc, [{"op": "merge", "anchors": anchors, "manual": True, "label": "ghep %s" % label},
                          {"op": "remesh", "anchor": anchors[big], "voxel": vox, "manual": True}])
    _log("[ghep] %s -> %s (%d mat)" % (" + ".join(o.name for o in objs), o2.name, len(t2.F)))
    return o2


def _append_plan_ops(sc, ops):
    pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
    if os.path.exists(pj):
        pl = json.load(open(pj, encoding="utf-8"))
        pl.setdefault("ops", []).extend(ops)
        json.dump(pl, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


class WC_OT_refine(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.refine"
    bl_label = "Claude tách sâu"
    bl_description = ("Claude xem CẢ model (mỗi mảnh in mã) đối chiếu bộ phận chuẩn: tách mảnh gộp hai thứ (mặt dính "
                      "thân, tay liền bàn tay) theo NẾP GẤP thật, ghép mảnh bị xé (vỏ mũ trùm + mặt = cái đầu), sửa tên; "
                      "lặp tới khi hết sửa. Đang chọn mảnh = chỉ xem riêng các mảnh đó. Hoàn tác được")

    auto: BoolProperty(default=False)

    def execute(self, ctx):
        sc = ctx.scene
        sel = [] if self.auto else [o for o in (getattr(ctx, "selected_objects", None) or [])
                                    if o in part_objects() and not o.get("wc_decor")]
        if not sel:                             # 2026-10-07: xem CA model truoc (tach + ghep + doi ten), roi moi cat
            if not part_objects():
                self.report({"ERROR"}, "Chưa có mảnh - bấm Tách bộ phận trước")
                return {"CANCELLED"}
            start_struct(sc, 1)
            return {"FINISHED"}
        for o in sel:
            if "wc_refined" in o:
                del o["wc_refined"]
        objs = refine_targets(sel)
        if not objs:
            self.report({"INFO"}, "Không còn bộ phận lớn nào cần xem")
            if CHAIN["stage"] == "refine":
                chain_next(sc, "decor")
            return {"FINISHED"}
        start_refine(sc, [o.name for o in objs], 1)
        return {"FINISHED"}


class WC_OT_ai_split_piece(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.ai_split_piece"
    bl_label = "Claude chia mảnh đang chọn"
    bl_description = ("Claude xem riêng mảnh đang chọn (vd thân xe liền một khối) và cắt thành các bộ phận con ở rãnh / "
                      "chỗ thắt: yên, chắn bùn, ốp đèn... (~1-2 phút, Hoàn tác được)")

    def execute(self, ctx):
        sc = ctx.scene
        ob = ctx.active_object
        if not ob or ob not in part_objects() or ob.get("wc_decor"):
            self.report({"ERROR"}, "Chọn một mảnh (không phải decor)")
            return {"CANCELLED"}
        # 2026-10-06: dung chung TACH SAU (anh du phia + ung vien cat theo nep) + yeu cau o panel; chi mot vong
        if start_refine(sc, [ob.name], round_=sc.wc_refine_rounds, hint=sc.wc_piece_hint, force=True):
            return {"FINISHED"}
        work = os.path.join(ROOT, "work", sc.wc_name)
        os.makedirs(work, exist_ok=True)
        path = os.path.join(work, "piece_ai.blend")
        bpy.data.libraries.write(path, set(o for o in part_objects() if not o.get("wc_decor")), fake_user=False)
        name = ob.name

        def done(rc, lines):
            p = _grab(lines, "PIECE_PLAN_READY")
            o = bpy.data.objects.get(name)
            if not p or not os.path.exists(p) or o is None:
                _log("[chia manh] khong co ke hoach")
                return
            plan = json.load(open(p, encoding="utf-8"))
            ops = plan.get("ops", [])
            anc = _piece_anchor(o)
            for x in ops:
                x["manual"] = True
                x["ai_piece"] = name
            new, log = _live_split(o, ops)
            for ln in log[-12:]:
                _log(ln)
            if not new:
                _log("[chia manh] khong chia duoc %s" % name)
                sc.wc_decor_msg = "Không chia được %s" % name
                return
            pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
            if os.path.exists(pj):
                pl = json.load(open(pj, encoding="utf-8"))
                pl.setdefault("ops", []).extend(ops)
                json.dump(pl, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            _log("[chia manh] %s -> %d manh: %s" % (name, len(new), plan.get("notes", "")))
            sc.wc_decor_msg = "Claude chia %s thành %d mảnh" % (name, len(new))
        start_job("piece", sc.wc_name, ["piece-plan", "--name", sc.wc_name, "--in", path, "--piece", name,
                                        "--label", ob.get("wc_label", name), "--hint", sc.wc_piece_hint,
                                        "--prompt", sc.wc_model_prompt], done)
        return {"FINISHED"}


class WC_OT_split_piece(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.split_piece"
    bl_label = "Chia mảnh đang chọn"
    bl_description = "Cắt ngay mảnh đang chọn theo kiểu + số phần, trải lại UV; ghi vào plan.json để cắt lại không mất"

    def execute(self, ctx):
        sc = ctx.scene
        ob = ctx.active_object
        if not ob or ob not in part_objects():
            self.report({"ERROR"}, "Chọn một mảnh trong 'WC 3 · Manh'")
            return {"CANCELLED"}
        op = _split_op(ob, sc)
        new, log = _live_split(ob, op)
        if not new:
            self.report({"WARNING"}, "Không chia được mảnh này theo kiểu đã chọn")
            return {"CANCELLED"}
        path = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
        if os.path.exists(path):
            plan = json.load(open(path, encoding="utf-8"))
            plan.setdefault("ops", []).append(op)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(plan, fh, indent=1, ensure_ascii=False)
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        for o in new:
            o.select_set(True)
        ctx.view_layer.objects.active = new[0]
        self.report({"INFO"}, "Chia thành %d mảnh" % len(new))
        return {"FINISHED"}


class WC_OT_view_game(bpy.types.Operator):
    bl_idname = "woolcut.view_game"
    bl_label = "Xem như trong game"
    bl_description = "Bật: Material Preview (len đan x màu game, D theo texture Deco). Tắt: màu phẳng từng mảnh"
    game: BoolProperty(default=True)

    def execute(self, ctx):
        for w in ctx.window_manager.windows:
            for a in w.screen.areas:
                if a.type == "VIEW_3D":
                    sh = a.spaces.active.shading
                    if self.game:
                        sh.type = "MATERIAL"
                    else:
                        sh.type = "SOLID"
                        sh.color_type = "OBJECT"
        return {"FINISHED"}


class WC_OT_undo_split(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.undo_split"
    bl_label = "Bỏ lần chia tay gần nhất"

    def execute(self, ctx):
        sc = ctx.scene
        if _undo_last(sc):                       # co mesh cu luu san -> tra lai tuc thi
            self.report({"INFO"}, "Đã hoàn tác (còn %d bước)" % len(UNDO))
            return {"FINISHED"}
        path = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
        if not os.path.exists(path):
            return {"CANCELLED"}
        plan = json.load(open(path, encoding="utf-8"))
        idx = [i for i, o in enumerate(plan.get("ops", [])) if o.get("manual")]
        if not idx:
            self.report({"INFO"}, "Không có lần chia tay nào")
            return {"CANCELLED"}
        plan["ops"].pop(idx[-1])
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1, ensure_ascii=False)
        _recut(sc)
        return {"FINISHED"}


class WC_OT_open(bpy.types.Operator):
    bl_idname = "woolcut.open"
    bl_label = "Mở"
    what: StringProperty()

    def execute(self, ctx):
        name = ctx.scene.wc_name
        work = os.path.join(ROOT, "work", name)
        path = {"plan": os.path.join(work, "plan.json"), "work": work, "out": os.path.join(ROOT, "out"),
                "sheet": os.path.join(work, "parts_sheet.png")}.get(self.what, work)
        if os.path.exists(path):
            os.startfile(path)
        return {"FINISHED"}


def _append_plan_op(sc, op):
    pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
    if os.path.exists(pj):
        plan = json.load(open(pj, encoding="utf-8"))
        plan.setdefault("ops", []).append(op)
        json.dump(plan, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


class WC_OT_label(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.label"
    bl_label = "Claude đặt tên bộ phận"
    bl_description = "Claude xem ảnh và đặt tên tiếng Việt cho từng mảnh (đầu, tai trái, bánh trước...)"

    def execute(self, ctx):
        sc = ctx.scene

        def done(rc, lines):
            n = apply_labels(sc)
            _log("[dat ten] doi ten %d manh" % n)
        start_job("label", sc.wc_name, ["label", "--name", sc.wc_name, "--prompt", sc.wc_model_prompt], done)
        return {"FINISHED"}


class WC_OT_drop_tiny(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.drop_tiny"
    bl_label = "Xoá mảnh li ti ngay"
    bl_description = "Xoá ngay các mảnh có cạnh dài nhất nhỏ hơn ngưỡng (% cỡ model) trong cảnh. Ghi vào plan.json"

    def execute(self, ctx):
        objs = part_objects()
        if not objs:
            return {"CANCELLED"}
        import numpy as np
        W = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in objs])
        lim = ctx.scene.wc_tiny / 100.0 * float((W.max(0) - W.min(0)).max())
        small = [o for o in objs if max(o.dimensions) < lim and not o.get("wc_decor")]
        pj = os.path.join(ROOT, "work", ctx.scene.wc_name, "plan.json")
        if os.path.exists(pj):
            plan = json.load(open(pj, encoding="utf-8"))
            plan["tiny"] = ctx.scene.wc_tiny / 100.0
            json.dump(plan, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        for o in small:
            bpy.data.objects.remove(o, do_unlink=True)
        self.report({"INFO"}, "Đã xoá %d mảnh li ti" % len(small))
        return {"FINISHED"}


# ------------------------------------------------------------------ DECOR (thu vien + Claude gan)
_PREV = {"coll": None}


def _decor_icon(did):
    """Icon xem truoc cua decor (data/decor/thumbs/<id>.png)."""
    from bpy.utils import previews as _pv
    if _PREV["coll"] is None:
        _PREV["coll"] = _pv.new()
    pc = _PREV["coll"]
    if did not in pc:
        p = os.path.join(ROOT, "data", "decor", "thumbs", did + ".png")
        if not os.path.exists(p):
            return 0
        pc.load(did, p, "IMAGE")
    return pc[did].icon_id


def load_decor_items(sc):
    """catalog.json -> danh sach o panel (giu trang thai tick cu)."""
    from .wc import decor as dmod
    old = {it.did: it.enabled for it in sc.wc_decor_items}
    sc.wc_decor_items.clear()
    try:
        cat = dmod.catalog()
    except (OSError, ValueError):
        return 0
    for c in cat:
        it = sc.wc_decor_items.add()
        it.did, it.vi, it.group = c["id"], c["vi"], c.get("group", "")
        it.enabled = old.get(c["id"], True)
    return len(cat)


def _decor_json(sc):
    return os.path.join(ROOT, "work", sc.wc_name, "decor.json")


def _decor_entries(sc):
    p = _decor_json(sc)
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _decor_save(sc, rows):
    p = _decor_json(sc)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(rows, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def _lib_mesh(did):
    """Mesh thu vien 'dec_<id>' (nap tu library.blend / custom.blend mot lan, giu fake user)."""
    from .wc import decor as dmod
    me = bpy.data.meshes.get("dec_" + did)
    if me is not None and me.get("wc_lib"):
        return me
    for path in (dmod.LIB_BLEND, dmod.CUSTOM_BLEND):
        if not os.path.exists(path):
            continue
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.meshes = [n for n in src.meshes if n == "dec_" + did]
        for m in dst.meshes:
            if m is not None:
                m.use_fake_user = True
                m["wc_lib"] = True
                return m
    return None


def _decor_object(sc, entry, mw):
    """Tao manh D decor tu entry {uid, decor, color, host} + ma tran the gioi."""
    from mathutils import Matrix
    from .wc import look, std, decor as dmod
    cat = {c["id"]: c for c in dmod.catalog()}
    c = cat.get(entry["decor"])
    src = _lib_mesh(entry["decor"])
    if c is None or src is None:
        return None
    me = src.copy()
    me.use_fake_user = False
    if "wc_lib" in me:
        del me["wc_lib"]
    n = sum(1 for o in part_objects() if o.get("wc_decor")) + 1
    ob = bpy.data.objects.new("Dc%02d %s" % (n, c["vi"]), me)
    bpy.data.collections.get(COLL_PARTS).objects.link(ob)
    ob.matrix_world = mw
    me.materials.clear()
    me.materials.append(look.deco_material())
    if c["mode"] == "tint":
        try:
            col = std.resolve_color(entry.get("color") or c.get("color") or "White")
        except Exception:
            col = std.resolve_color(c.get("color") or "White")
        u, v, _ = look.deco_point(col)
        look.deco_uv(me, u, v)
        ob["wc_color"] = col
        look.show_color(ob, col)
    else:
        if me.uv_layers:
            me.uv_layers[0].name = "map1"
        ob["wc_decor_multi"] = True
        ob["wc_color"] = std.mat_name(15, "White")
    ob["wc_kind"] = "D"
    ob["wc_kind_auto"] = "D"
    ob["wc_decor"] = entry["decor"]
    ob["wc_decor_uid"] = entry["uid"]
    if entry.get("host"):
        ob["wc_host"] = entry["host"]
    return ob


def apply_decor_json(sc):
    """decor.json -> dat lai decor sau khi nap / cat lai (host theo ten, mat thi manh gan nhat)."""
    from mathutils import Matrix
    rows = _decor_entries(sc)
    n = 0
    names = {o.name for o in part_objects()}
    for e in rows:
        mw = Matrix([e["matrix"][i * 4:(i + 1) * 4] for i in range(4)])
        if e.get("host") not in names:
            e["host"] = None
        if _decor_object(sc, e, mw) is not None:
            n += 1
    return n


def place_decor_plan(sc, path):
    """decor_plan.json cua Claude -> dat tung decor len manh chu. Tra ve (so da dat, [loi])."""
    from .wc import decor as dmod
    plan = json.load(open(path, encoding="utf-8"))
    cat = {c["id"]: c for c in dmod.catalog()}
    bpy.context.view_layer.update()              # matrix_world cu ngay sau khi nap manh -> tia ban lech (2026-10-05)
    rows = _decor_entries(sc)
    uid0 = max([e.get("uid", 0) for e in rows] + [0])
    made, errs = [], []
    # tia ban vao TAT CA manh M/S: be mat nhin thay dau tien = noi dat, manh chu = manh tia cham (ten Claude dua chi la
    # goi y - khong co ten bo phan Claude tung chon lat mong ben trong than, nut ao nam lot vao trong; 2026-10-05)
    solid = [o for o in part_objects() if not o.get("wc_decor") and (o.get("wc_kind") or o.get("wc_kind_auto")) != "D"]
    ubvh, owner = dmod.union_bvh(solid)
    for k, x in enumerate(plan.get("decor", [])):
        c = cat.get(x.get("decor"))
        if c is None or ubvh is None:
            errs.append("%s: decor la" % x.get("decor"))
            continue
        size = min(2.0, max(0.12 if x.get("decor") == "eye_shine" else 0.25, float(x.get("size", 0.4) or 0.4)))
        r = dmod.place_matrix(ubvh, x["at"], x.get("view", "front"), size,
                              c.get("dims", [1, 0.3, 1]), float(x.get("rot", 0) or 0))
        if r is None:
            errs.append("%s: khong cham be mat" % x.get("decor"))
            continue
        mw, hit, fidx = r
        host = owner[fidx] if fidx is not None and fidx < len(owner) else bpy.data.objects.get(x.get("host", ""))
        if host is None:
            errs.append("%s: khong co manh chu" % x.get("decor"))
            continue
        e = {"uid": uid0 + k + 1, "decor": x["decor"], "color": x.get("color"), "host": host.name,
             "matrix": [v for row in mw for v in row]}
        ob = _decor_object(sc, e, mw)
        if ob is not None:
            rows.append(e)
            made.append(ob)
    _decor_save(sc, rows)
    if made:
        _push_undo([], made, _plan_len(sc))
    return made, errs


class WC_OT_paint_ai(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.paint_ai"
    bl_label = "Claude tô màu theo bảng"
    bl_description = ("Claude nhìn các mảnh ĐANG CÓ trong cảnh (kể cả mảnh tách tay) và chọn màu bảng game cho từng "
                      "mảnh. Gán màu tại chỗ, KHÔNG cắt lại; ghi plan.json để Cắt lại không mất. Hoàn tác được (~1 phút)")

    def execute(self, ctx):
        sc = ctx.scene
        objs = part_objects()
        if not objs:
            self.report({"ERROR"}, "Chưa có mảnh (tách bộ phận trước)")
            return {"CANCELLED"}
        work = os.path.join(ROOT, "work", sc.wc_name)
        os.makedirs(work, exist_ok=True)
        path = os.path.join(work, "parts_paint.blend")
        bpy.data.libraries.write(path, set(objs), fake_user=False)
        pj = os.path.join(work, "plan.json")
        before = json.load(open(pj, encoding="utf-8")).get("ops", []) if os.path.exists(pj) else None

        def done(rc, lines):
            from .wc import look
            p = _grab(lines, "PAINT_READY")
            if not p or not os.path.exists(p):
                return
            d = json.load(open(p, encoding="utf-8"))
            old = {}
            for n, mn in d.get("apply", {}).items():
                o = bpy.data.objects.get(n)
                if o is None or o.type != "MESH":
                    continue
                old[n] = o.get("wc_color", "")
                look.apply_piece(o, _kind(o), mn, unwrap=False)     # chi doi material / o Deco, giu UV
            UNDO.append({"orig": [], "new": [], "nops": None, "colors": old, "plan_ops": before})
            del UNDO[:-30]
            _log("[to mau] doi mau %d manh tai cho (Hoan tac de tra lai)" % len(old))
        start_job("paint", sc.wc_name, ["paint", "--name", sc.wc_name, "--in", path, "--prompt", sc.wc_model_prompt], done)
        return {"FINISHED"}


class WC_OT_decor_ai(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.decor_ai"
    bl_label = "Claude gắn decor"
    bl_description = "Claude xem các mảnh đã tách, chọn decor phù hợp trong các decor đang tick và gắn lên bề mặt (~1-2 phút)"

    def execute(self, ctx):
        sc = ctx.scene
        objs = part_objects()
        if not objs:
            self.report({"ERROR"}, "Chưa có mảnh (tách bộ phận trước)")
            return {"CANCELLED"}
        allow = [it.did for it in sc.wc_decor_items if it.enabled]
        if not allow:
            self.report({"ERROR"}, "Chưa tick decor nào")
            return {"CANCELLED"}
        work = os.path.join(ROOT, "work", sc.wc_name)
        os.makedirs(work, exist_ok=True)
        path = os.path.join(work, "parts_decor.blend")
        bpy.data.libraries.write(path, set(objs), fake_user=False)

        def done(rc, lines):
            p = _grab(lines, "DECOR_READY")
            newd = _grab(lines, "DECOR_NEW")
            if newd:
                load_decor_items(sc)
                for it in sc.wc_decor_items:
                    if it.did.startswith("ai_"):
                        it.enabled = True
                _log("[decor] Claude da TAO decor moi: %s" % newd)
                sc.wc_decor_msg = "Claude tạo decor mới: " + newd
            if p and os.path.exists(p):
                made, errs = place_decor_plan(sc, p)
                _log("[decor] da gan %d decor%s" % (len(made), ("; bo qua: " + "; ".join(errs[:6])) if errs else ""))
                if not newd:
                    sc.wc_decor_msg = "Đã gắn %d decor" % len(made)
        start_job("decor", sc.wc_name, ["decor", "--name", sc.wc_name, "--in", path, "--allow", ",".join(allow),
                                        "--prompt", sc.wc_model_prompt], done)
        return {"FINISHED"}


class WC_OT_decor_tick(bpy.types.Operator):
    bl_idname = "woolcut.decor_tick"
    bl_label = "Tick decor"
    mode: StringProperty(default="all")

    def execute(self, ctx):
        sc = ctx.scene
        if self.mode == "reload":
            load_decor_items(sc)
            return {"FINISHED"}
        for it in sc.wc_decor_items:
            it.enabled = (self.mode == "all") or (self.mode not in ("none",) and it.group == self.mode)
        return {"FINISHED"}


class WC_OT_decor_clear(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.decor_clear"
    bl_label = "Xoá hết decor đã gắn"
    bl_description = "Xoá mọi decor do Claude gắn (Hoàn tác được)"

    def execute(self, ctx):
        sc = ctx.scene
        objs = [o for o in part_objects() if o.get("wc_decor")]
        if not objs:
            return {"CANCELLED"}
        rows = _decor_entries(sc)
        for o in objs:
            e = next((r for r in rows if r.get("uid") == o.get("wc_decor_uid")), None)
            if e is not None:
                o["wc_decor_entry"] = json.dumps(e)
        _decor_save(sc, [r for r in rows if r.get("uid") not in {o.get("wc_decor_uid") for o in objs}])
        _push_undo(_archive(objs), [], _plan_len(sc))
        self.report({"INFO"}, "Đã xoá %d decor" % len(objs))
        return {"FINISHED"}


class WCDecorItem(bpy.types.PropertyGroup):
    did: StringProperty()
    vi: StringProperty()
    group: StringProperty()
    enabled: BoolProperty(default=True)


class WC_UL_decor(bpy.types.UIList):
    def draw_item(self, ctx, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text=item.vi, icon_value=_decor_icon(item.did))


class WC_OT_drop_piece(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.drop_piece"
    bl_label = "Xoá mảnh đang chọn"
    bl_description = "Xoá các mảnh thừa đang chọn (vạt, mẩu vụn). Ghi vào plan.json để Cắt lại không hiện lại"

    def execute(self, ctx):
        sel = [o for o in ctx.selected_objects if o.type == "MESH" and o in part_objects()]
        if not sel:
            self.report({"ERROR"}, "Chưa chọn mảnh")
            return {"CANCELLED"}
        nops = _plan_len(ctx.scene)
        rows = _decor_entries(ctx.scene)
        gone = set()
        for o in sel:
            if o.get("wc_decor"):                    # decor: bo khoi decor.json (hoan tac dua lai)
                e = next((r for r in rows if r.get("uid") == o.get("wc_decor_uid")), None)
                if e is not None:
                    o["wc_decor_entry"] = json.dumps(e)
                    gone.add(e["uid"])
                continue
            _append_plan_op(ctx.scene, {"op": "drop", "anchor": _piece_anchor(o), "manual": True,
                                        "label": "xoa tay %s" % o.name})
        if gone:
            _decor_save(ctx.scene, [r for r in rows if r.get("uid") not in gone])
        _push_undo(_archive(sel), [], nops)
        self.report({"INFO"}, "Đã xoá %d mảnh" % len(sel))
        return {"FINISHED"}


class WC_OT_remesh_piece(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.remesh_piece"
    bl_label = "Mesh lại mảnh đang chọn"
    bl_description = "Dựng lại lưới mảnh lỗi bằng voxel (hết vạt mỏng, mặt chồng, lỗ hở). Ghi vào plan.json"

    def execute(self, ctx):
        from .wc import bl, look, prep as prepmod, uv as uvmod
        sel = [o for o in ctx.selected_objects if o.type == "MESH" and o in part_objects()]
        if not sel:
            self.report({"ERROR"}, "Chưa chọn mảnh")
            return {"CANCELLED"}
        done = 0
        for ob in sel:
            anchor = _piece_anchor(ob)
            t = bl.tm_from_mesh(ob.data, ob.matrix_world)
            t2 = prepmod.rebuild(t, "mesh lai %s" % ob.name, log=_log)    # tam mong: lam day truoc, khong thung lo
            if t2 is None:
                self.report({"WARNING"}, "%s: không dựng lại được" % ob.name)
                continue
            props = {k: ob[k] for k in ("wc_color", "wc_kind", "wc_kind_auto", "wc_host", "wc_label") if k in ob}
            name, coll = ob.name, ob.users_collection[0]
            nops = _plan_len(ctx.scene)
            arch = _archive([ob])
            ob.name = name + " (cu)"
            arch = [ob.name]
            o2 = bl.object_from_tm(t2, name, coll=coll, per_face=False)
            for k, v in props.items():
                o2[k] = v
            uvmod.center_origin(o2)
            kind = props.get("wc_kind") or props.get("wc_kind_auto", "M")
            look.apply_piece(o2, kind, props.get("wc_color", ""), unwrap=(kind != "D"))
            _append_plan_op(ctx.scene, {"op": "remesh", "anchor": anchor, "manual": True, "label": "mesh lai %s" % name})
            _push_undo(arch, [o2], nops)
            done += 1
        _DRAW["cache"] = {}
        self.report({"INFO"}, "Đã mesh lại %d mảnh" % done)
        return {"FINISHED"}


class WC_OT_join(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.join"
    bl_label = "Ghép mảnh đã chọn"
    bl_description = "Ghép các mảnh đang chọn thành một (giữ màu mảnh active). Ghi vào plan.json để Cắt lại không mất"

    def execute(self, ctx):
        sel = [o for o in ctx.selected_objects if o.type == "MESH" and o in part_objects()]
        if len(sel) < 2:
            self.report({"ERROR"}, "Chọn ít nhất 2 mảnh (Shift + click)")
            return {"CANCELLED"}
        act = ctx.active_object if ctx.active_object in sel else sel[0]
        anchors = [_piece_anchor(o) for o in [act] + [o for o in sel if o is not act]]
        nops = _plan_len(ctx.scene)
        keep = []
        for o in sel:                                   # ban sao mesh cu de hoan tac
            c = o.copy()
            c.data = o.data.copy()
            bpy.context.scene.collection.objects.link(c)
            c.name = o.name + " (cu)"
            keep.append(c)
        arch = _archive(keep)
        col, kind = act.get("wc_color"), act.get("wc_kind")
        ctx.view_layer.objects.active = act
        bpy.ops.object.join()
        ob = ctx.view_layer.objects.active
        try:
            from .wc import look, uv as uvmod
            uvmod.center_origin(ob)
            k = kind or ob.get("wc_kind_auto", "M")
            look.apply_piece(ob, k, col or (ob.data.materials[0].name if ob.data.materials else ""), unwrap=(k != "D"))
        except Exception as e:                          # khong de loi trai UV lam mat thao tac ghep
            _log("[ghep] trai lai UV loi: %s" % e)
        pj = os.path.join(ROOT, "work", ctx.scene.wc_name, "plan.json")
        if os.path.exists(pj):
            plan = json.load(open(pj, encoding="utf-8"))
            plan.setdefault("ops", []).append({"op": "merge", "anchors": anchors, "manual": True,
                                               "label": "ghep tay %d manh" % len(anchors)})
            json.dump(plan, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        _push_undo(arch, [ob], nops)
        self.report({"INFO"}, "Đã ghép %d mảnh" % len(anchors))
        return {"FINISHED"}


SHELL_HEAD_WORDS = ("mũ", "nón", "mu ", "helmet", "hood", "khăn trùm")


def _far_anchor(ob, others, n=400):
    """Diem neo = dinh cua `ob` XA cac manh khac nhat. Tam mat lon nhat (_piece_anchor) cua mu lai nam dung mat tiep
    giap mu / than -> cat lai toan bo chon nham manh (2026-10-07)."""
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    W = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    if len(W) > n:
        W = W[::int(np.ceil(len(W) / n))]
    lo, hi = W.min(0), W.max(0)
    pad = 0.25 * float((hi - lo).max())
    trees = []
    for o in others:
        if o is ob or not o.data.vertices:
            continue
        bb = np.array([(o.matrix_world @ Vector(c))[:] for c in o.bound_box])
        if np.any(bb.max(0) < lo - pad) or np.any(bb.min(0) > hi + pad):
            continue
        dg = bpy.context.evaluated_depsgraph_get()
        tr = BVHTree.FromObject(o, dg)
        trees.append((tr, o.matrix_world.inverted()))
    if not trees:
        return [float(x) for x in W[0]]
    best, bd = W[0], -1.0
    for p in W:
        d = min((tr.find_nearest(mi @ Vector(p))[3] or 1e9) for tr, mi in trees)
        if d > bd:
            best, bd = p, d
    return [float(x) for x in best]


class WC_OT_shell_split(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.shell_split"
    bl_label = "Tách vỏ + dựng phần bên trong"
    bl_description = ("Chọn mảnh VỎ đặc (mũ úp lên đầu...). Tool lấy mảnh thứ hai đang chọn, hoặc tự tìm mảnh chạm vỏ "
                      "nhiều nhất, cắt nó ở cổ, biến vỏ thành lớp rỗng và dựng phần bên trong (đầu) vừa khít trong vỏ. "
                      "Hoàn tác được, ghi plan.json (wc/shell.py)")
    thickness: bpy.props.FloatProperty(name="Độ dày vỏ (% cỡ vỏ)", default=4.0, min=1.0, max=15.0)

    def invoke(self, ctx, event):
        return ctx.window_manager.invoke_props_dialog(self)

    def execute(self, ctx):
        import numpy as np
        from .wc import bl, plan as planmod, shell, look, std, uv as uvmod
        sc = ctx.scene
        parts = [o for o in part_objects() if not o.get("wc_decor") and _kind(o) != "D"]
        sel = [o for o in ctx.selected_objects if o in parts]
        outer = ctx.active_object if ctx.active_object in sel else (sel[0] if sel else None)
        if outer is None:
            self.report({"ERROR"}, "Chọn mảnh vỏ (vd mũ); thêm Shift + click mảnh bên trong nếu muốn chỉ định")
            return {"CANCELLED"}
        bpy.context.view_layer.update()
        lo = np.min([np.array(o.bound_box).min(0) for o in parts], axis=0)
        hi = np.max([np.array(o.bound_box).max(0) for o in parts], axis=0)
        side = float((hi - lo).max()) or 10.0
        to = bl.tm_from_mesh(outer.data, outer.matrix_world)
        others = [o for o in sel if o is not outer]
        inner = others[0] if others else None
        if inner is None:                                # manh cham vo nhieu nhat (loc truoc theo hop bao)
            from mathutils import Vector
            from mathutils.bvhtree import BVHTree
            eps = shell.CONTACT_REL * side
            olo, ohi = to.V.min(0) - eps, to.V.max(0) + eps
            C = to.face_centers()
            C = C[::max(1, int(np.ceil(len(C) / 2000)))]
            dg = bpy.context.evaluated_depsgraph_get()
            best = (0.0, None)
            for o in parts:
                if o is outer:
                    continue
                bb = np.array([(o.matrix_world @ Vector(c))[:] for c in o.bound_box])
                if np.any(bb.max(0) < olo) or np.any(bb.min(0) > ohi):
                    continue
                tr, mi = BVHTree.FromObject(o, dg), o.matrix_world.inverted()
                k = 0
                for c in C:                              # nhu shell.contact: dau trong/ngoai chi xet khi gan
                    q = mi @ Vector(c)
                    loc, nrm, _, d = tr.find_nearest(q, 4 * eps)
                    if loc is not None and (d < eps or (q - loc).dot(nrm) < 0):
                        k += 1
                k /= max(1, len(C))
                if k > best[0]:
                    best = (k, o)
            inner = best[1]
            if inner is not None:
                _log("[tach vo] manh trong tu chon: %s (cham %.0f%% mat vo)" % (inner.name, 100 * best[0]))
        if inner is None:
            self.report({"ERROR"}, "Không thấy mảnh nào chạm vỏ - chọn thêm mảnh bên trong")
            return {"CANCELLED"}

        def colname(o):
            return o.get("wc_color") or std.canonical(o.data.materials[0].name if o.data.materials else "") \
                or std.mat_name(15, "White")
        ti = bl.tm_from_mesh(inner.data, inner.matrix_world)
        to.col = np.zeros(len(to.F), np.int64)
        ti.col = np.ones(len(ti.F), np.int64)
        R = planmod.Run([to, ti], [colname(outer), colname(inner)], verbose=False)
        size_o = float((to.V.max(0) - to.V.min(0)).max())
        op = {"op": "shell", "outer": _far_anchor(outer, parts), "inner": _far_anchor(inner, parts),
              "t": self.thickness / 100.0 * size_o, "manual": True, "label": "tach vo %s" % outer.name}
        try:
            res = shell.op_shell(R, op)
        except Exception as e:
            for ln in R.log[-6:]:
                _log(ln)
            self.report({"ERROR"}, "Không tách được: %s" % e)
            return {"CANCELLED"}
        for ln in R.log:
            _log(ln)
        nops = _plan_len(sc)
        lab_o = outer.get("wc_label") or (outer.name.split(" ", 1)[1] if " " in outer.name else "vỏ")
        core_lab = "đầu" if any(w in (lab_o + " ").lower() for w in SHELL_HEAD_WORDS) else "trong %s" % lab_o
        src_of = {"khoi 0": outer, "khoi 1": inner}
        old_names = {outer: outer.name, inner: inner.name}
        coll = outer.users_collection[0]
        hosts = {d.name: d.get("wc_host") for d in part_objects() if d.get("wc_host") in (outer.name, inner.name)}
        _archive([outer, inner])
        for o in (outer, inner):
            o.name = o.name + " (cu)"
        arch = [outer.name, inner.name]
        new, core_ob = [], None
        for p in R.pieces:
            src = src_of.get(p.src, inner)
            if p is res["shell"]:
                nm, lab = old_names[outer], outer.get("wc_label", "")
            elif p is res["core"]:
                nm, lab = "%s.1 %s" % (old_names[inner].split(" ")[0], core_lab), core_lab
            else:
                nm, lab = old_names[src], src.get("wc_label", "")
            tm2 = p.tm
            if sc.wc_bevel3 > 0 and (p.tm.cap >= 0).any():
                from .wc import fillet as FL
                tm2 = FL.fillet(p.tm, sc.wc_bevel3, log=_log)
            o2 = bl.object_from_tm(tm2, nm, coll=coll, per_face=False)
            uvmod.center_origin(o2)
            plo, phi = p.tm.bbox()
            forced = src.get("wc_kind") if p is not res["core"] else None
            kind = forced or std.classify((phi - plo).tolist(), side)
            o2["wc_kind_auto"] = kind
            if forced:
                o2["wc_kind"] = forced
            col = R.piece_color(p)
            o2["wc_color"] = col
            if lab:
                o2["wc_label"] = lab
            look.apply_piece(o2, kind, col, unwrap=True, density=_uv_density())
            new.append(o2)
            if p is res["core"]:
                core_ob = o2
        # mieng dan D (mat, ma...) cua manh trong -> gan vao manh moi gan nhat (mat thuong nam tren phan trong)
        from mathutils import Vector
        cands = [o for o in new if o.name != old_names[outer]]
        for dn, h in hosts.items():
            d = bpy.data.objects.get(dn)
            if d is None or h != old_names[inner] or not cands or not d.data.vertices:
                continue
            c = d.matrix_world @ (sum((v.co for v in d.data.vertices), Vector()) / len(d.data.vertices))
            d["wc_host"] = min(cands, key=lambda o: (o.matrix_world @ o.closest_point_on_mesh(
                o.matrix_world.inverted() @ c)[1] - c).length).name
        _append_plan_op(sc, op)
        _push_undo(arch, new, nops)
        UNDO[-1]["hosts"] = hosts
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        if core_ob is not None:
            core_ob.select_set(True)
            ctx.view_layer.objects.active = core_ob
        _DRAW["cache"] = {}
        self.report({"INFO"}, "Đã tách vỏ %s (dày %.2f), dựng %s, cắt %s ở cổ" % (
            old_names[outer], op["t"], core_ob.name if core_ob else "phần trong", old_names[inner]))
        return {"FINISHED"}


# ------------------------------------------------------------------ ke hoach cat: xem truoc, chinh, xac nhan
PLAN_NO_PLANES = ("color", "kind", "drop", "decal", "merge", "part")
PLAN_TRACE = {"name": None, "trace": {}}     # ket qua chay thu ke hoach: {chi so: [(planes, TM manh)]}


def load_trace(sc, path=None):
    """plan_trace.npz (tien trinh nen chay thu ke hoach) -> PLAN_TRACE {chi so: [(planes, V, E)]}."""
    import numpy as np
    path = path or os.path.join(ROOT, "work", sc.wc_name, "plan_trace.npz")
    if not os.path.exists(path):
        return 0
    z = np.load(path)
    tr = {}
    for k, i in enumerate(z["idx"].tolist()):
        V, F, P = z["V%d" % k].astype(float), z["F%d" % k], z["P%d" % k].astype(float)
        E = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1), axis=0)
        tr.setdefault(i, []).append(([(p[:3], p[3:]) for p in P], V, E))
    PLAN_TRACE["name"], PLAN_TRACE["trace"] = sc.wc_name, tr
    _DRAW["cache"] = {}
    return len(tr)


def plan_dry_run(sc):
    """Ghi bat/tat + so mui vao plan.json roi CHAY THU o tien trinh nen (khong treo Blender) -> load_trace."""
    save_plan_ops(sc)

    def done(rc, lines):
        p = _grab(lines, "TRACE_READY")
        if p:
            load_trace(sc, p)
    return start_job("trace", sc.wc_name, ["trace", "--name", sc.wc_name], done)


class WCPlanOp(bpy.types.PropertyGroup):
    enabled: BoolProperty(default=True, description="Bỏ tick = không thực hiện nhát này")
    label: StringProperty()
    summary: StringProperty()
    index: IntProperty(default=-1)
    n: IntProperty(default=0, min=0, max=24, description="Số múi / lát (0 = không áp dụng)")


class WC_UL_plan(bpy.types.UIList):
    def draw_item(self, ctx, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text="%d. %s · %s" % (index + 1, item.label or "-", item.summary))
        if item.n:
            row.prop(item, "n", text="")


def _op_summary(o):
    k = o.get("op", "?")
    if k == "cut":
        return "cắt rời (mặt phẳng)"
    if k == "split":
        return "chia %d mảnh qua tâm" % (2 ** len(o.get("normals") or o.get("axes", ["x"])))
    if k == "sectors":
        return "múi cam %s%s" % (o.get("n", 4), (" × %d tầng" % o["layers"]) if o.get("layers", 1) > 1 else "")
    if k == "slices":
        return "%s lát" % (len(o["at"]) + 1 if o.get("at") else o.get("n", 2))
    if k == "grid":
        return "lưới %s" % o.get("grid")
    return k


def load_plan_ops(sc):
    """plan.json -> danh sach o panel (bo cac thao tac to mau tu dong)."""
    sc.wc_plan_ops.clear()
    pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
    if not os.path.exists(pj):
        return 0
    plan = json.load(open(pj, encoding="utf-8"))
    for i, o in enumerate(plan.get("ops", [])):
        if o.get("paint") or o.get("op") in ("color",):
            continue
        it = sc.wc_plan_ops.add()
        it.index = i
        it.label = (o.get("label") or "")[:60]
        it.summary = _op_summary(o)
        it.enabled = not o.get("skip", False)
        it.n = int(o.get("n", 0)) if o.get("op") in ("sectors", "slices") and not o.get("at") else 0
    sc.wc_plan_idx = 0
    return len(sc.wc_plan_ops)


def save_plan_ops(sc):
    """Ghi lai bat/tat + so mui vao plan.json truoc khi tach."""
    pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
    plan = json.load(open(pj, encoding="utf-8"))
    ops = plan.get("ops", [])
    for it in sc.wc_plan_ops:
        if 0 <= it.index < len(ops):
            o = ops[it.index]
            if it.enabled:
                o.pop("skip", None)
            else:
                o["skip"] = True
            if it.n and o.get("op") in ("sectors", "slices"):
                o["n"] = int(it.n)
    json.dump(plan, open(pj, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def load_prep_preview(sc):
    """Cac part / khoi roi sau buoc chuan bi (moi khoi mot mau) -> collection xem truoc ke hoach."""
    path = os.path.join(ROOT, "work", sc.wc_name, "prep.blend")
    if not os.path.exists(path):
        return 0
    coll = _fresh(COLL_PREP)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("K")]
    n = 0
    for o in dst.objects:
        if o is not None and o.type == "MESH":
            coll.objects.link(o)
            o.hide_select = True
            n += 1
    _show_only(COLL_PREP)
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == "VIEW_3D":
                a.spaces.active.shading.color_type = "MATERIAL" if a.spaces.active.shading.type == "SOLID" else \
                    a.spaces.active.shading.color_type
    return n


def _prep_objects():
    c = bpy.data.collections.get(COLL_PREP)
    return [o for o in c.all_objects if o.type == "MESH"] if c else []


def _op_planes(o, objs):
    """Mat phang xem truoc cho MOT thao tac ke hoach (giong loi cat): (planes [(diem, truc, huong|None)], khoi dich)."""
    import numpy as np
    import math
    from .wc.tm import piece_frame, piece_axes
    q = o.get("anchor") or o.get("target") or o.get("at") or (o.get("anchors") or [None])[0] \
        or (o.get("targets") or [None])[0]
    if q is None or not objs:
        return [], None
    q = np.asarray(q, float)
    best, bv = None, None
    for ob in objs:
        lo = np.array([min(c[i] for c in ob.bound_box) for i in range(3)]) + np.array(ob.matrix_world.translation)
        hi = np.array([max(c[i] for c in ob.bound_box) for i in range(3)]) + np.array(ob.matrix_world.translation)
        inside = bool(np.all(q >= lo - 0.05) and np.all(q <= hi + 0.05))
        vol = float(np.prod(np.maximum(hi - lo, 1e-3)))
        key = (0 if inside else 1, vol if inside else float(np.linalg.norm((lo + hi) / 2 - q)))
        if bv is None or key < bv:
            best, bv = ob, key
    ob = best
    W = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    if not len(W):
        return [], ob
    k = o.get("op")
    if k in PLAN_NO_PLANES:
        return [], ob
    if k == "cut":
        n = np.asarray(o.get("normal", (0, 0, 1)), float)
        n /= np.linalg.norm(n) or 1.0
        return [(np.asarray(o["at"], float), n, None)], ob
    F = _tris(ob)
    R = np.eye(3) if o.get("world") else piece_frame(W, F)
    axes = piece_axes(W, F)[0]
    named = {"long": axes[0], "mid": axes[1], "short": axes[2]}

    def ax(v, default="z"):
        v = default if v is None else v
        if isinstance(v, str):
            s = v.lower()
            if s in named:
                return named[s]
            e = np.array({"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[s[-1]], float) * (-1 if s.startswith("-") else 1)
            return R @ e
        v = np.asarray(v, float)
        return v / (np.linalg.norm(v) or 1.0)
    c = np.asarray(o["center"], float) if o.get("center") else W.mean(0)
    planes = []
    if k == "split":
        for n in (o.get("normals") or o.get("axes", ["x"])):
            planes.append((c, ax(n), None))
    elif k in ("slices", "grid"):
        sets = [(o.get("axis", "z"), o.get("n", 2), o.get("at"))] if k == "slices" else \
            [(R[:, i], g, None) for i, g in enumerate(o.get("grid", [2, 2, 1]))]
        for a_, n_, at in sets:
            a = ax(a_) if not isinstance(a_, np.ndarray) else a_
            d = W @ a
            fr = at or [i / int(n_) for i in range(1, int(n_))]
            for f in fr:
                planes.append((c + a * (d.min() + (d.max() - d.min()) * float(f) - c @ a), a, None))
    elif k == "sectors":
        a = ax(o.get("axis", "z"))
        t = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        e1 = np.cross(a, t)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(a, e1)
        n_ = max(2, int(o.get("n", 4)))
        st = math.radians(float(o.get("start", 0)))
        for i in range(n_):
            ang = st + 2 * math.pi * i / n_
            planes.append((c, a, math.cos(ang) * e1 + math.sin(ang) * e2))
        lay = int(o.get("layers", 1))
        d = W @ a
        for i in range(1, lay):
            planes.append((c + a * (d.min() + (d.max() - d.min()) * i / lay - c @ a), a, None))
    return planes, ob


def _planes_geom(planes, s):
    import numpy as np
    tris, lines = [], []
    for p, a, d in planes:
        p, a = np.asarray(p, float), np.asarray(a, float)
        if d is None:
            u = np.cross(a, [0, 0, 1.0] if abs(a[2]) < 0.9 else [1.0, 0, 0])
            u /= np.linalg.norm(u)
            w = np.cross(a, u)
            q = [p + s * (su * u + sw * w) for su, sw in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        else:
            d = np.asarray(d, float)
            q = [p - s * a, p + s * a, p + s * a + s * d, p - s * a + s * d]
        tris += [q[0], q[1], q[2], q[0], q[2], q[3]]
        lines += [q[0], q[1], q[1], q[2], q[2], q[3], q[3], q[0]]
    return [tuple(x) for x in tris], [tuple(x) for x in lines]


def _draw_plan():
    """Ve nhat dang chon trong danh sach ke hoach: vien khoi dich (vang) + mat phang cat (do)."""
    import numpy as np
    sc = bpy.context.scene
    if not getattr(sc, "wc_plan_preview", False) or not len(sc.wc_plan_ops):
        return
    objs = _prep_objects()
    lc = bpy.context.view_layer.layer_collection.children.get(COLL_PREP)
    if not objs or (lc is not None and lc.hide_viewport):
        return
    i = sc.wc_plan_idx
    if not 0 <= i < len(sc.wc_plan_ops):
        return
    it = sc.wc_plan_ops[i]
    key = ("plan", sc.wc_name, it.index, it.n, it.enabled)
    geo = _DRAW["cache"].get(key)
    if geo is None and PLAN_TRACE["name"] == sc.wc_name and it.index in PLAN_TRACE["trace"]:
        ed, tris, lines = [], [], []
        for pl, V, E in PLAN_TRACE["trace"][it.index]:
            P = V[E.ravel()]
            ed += [tuple(x) for x in P]
            ext = float((V.max(0) - V.min(0)).max())
            s = ext * 0.62 if (len(pl) != 1 or it.summary.startswith("chia") or not it.summary.startswith("cắt")) \
                else min(ext * 0.62, 2.5)
            tr_, li_ = _planes_geom([(c, n, None) for c, n in pl], s)
            tris += tr_
            lines += li_
        geo = (ed, tris, lines)
        _DRAW["cache"] = {key: geo}
    if geo is None:
        pj = os.path.join(ROOT, "work", sc.wc_name, "plan.json")
        ops = json.load(open(pj, encoding="utf-8")).get("ops", [])
        o = dict(ops[it.index]) if 0 <= it.index < len(ops) else {}
        if it.n and o.get("op") in ("sectors", "slices"):
            o["n"] = it.n
        planes, ob = _op_planes(o, objs)
        ed = []
        s = 1.0
        if ob is not None:
            mw = ob.matrix_world
            ed = [tuple(mw @ ob.data.vertices[j].co) for e in ob.data.edges for j in e.vertices]
            W = np.array([(mw @ v.co)[:] for v in ob.data.vertices])
            s = float((W.max(0) - W.min(0)).max()) * 0.62
        if o.get("op") == "cut":
            s = min(s, 1.6)
        tris, lines = _planes_geom(planes, s)
        geo = (ed, tris, lines)
        _DRAW["cache"] = {key: geo}
    ed, tris, lines = geo
    import gpu
    from gpu_extras.batch import batch_for_shader
    sh = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    if ed:
        gpu.state.line_width_set(1.5)
        b = batch_for_shader(sh, "LINES", {"pos": ed})
        sh.bind()
        sh.uniform_float("color", (1.0, 0.82, 0.1, 0.6 if it.enabled else 0.25))
        b.draw(sh)
    if tris:
        gpu.state.depth_test_set("LESS_EQUAL")
        b = batch_for_shader(sh, "TRIS", {"pos": tris})
        sh.uniform_float("color", (1.0, 0.15, 0.25, 0.3) if it.enabled else (0.5, 0.5, 0.5, 0.15))
        b.draw(sh)
        gpu.state.depth_test_set("NONE")
        gpu.state.line_width_set(2.0)
        b = batch_for_shader(sh, "LINES", {"pos": lines})
        sh.uniform_float("color", (1.0, 0.15, 0.25, 0.9) if it.enabled else (0.5, 0.5, 0.5, 0.4))
        b.draw(sh)
    gpu.state.blend_set("NONE")
    gpu.state.line_width_set(1.0)


def _plan_idx_changed(self, ctx):
    for w in ctx.window_manager.windows:
        for a in w.screen.areas:
            if a.type == "VIEW_3D":
                a.tag_redraw()


class WC_OT_plan_only(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.plan_only"
    bl_label = "Claude lập kế hoạch (xem trước)"
    bl_description = "Claude viết kế hoạch cắt nhưng CHƯA cắt: xem từng nhát trên từng part, bật/tắt, đổi số múi rồi Xác nhận"

    def execute(self, ctx):
        sc = ctx.scene
        p = bpy.path.abspath(sc.wc_model)
        if not os.path.exists(p):
            self.report({"ERROR"}, "Chưa có model (bước 2)")
            return {"CANCELLED"}
        args = ["split", "--in", p, "--name", sc.wc_name, "--turn", str(sc.wc_turn), "--tilt", str(sc.wc_tilt), "--plan-only",
                "--min", str(sc.wc_min), "--max", str(sc.wc_max), "--prompt", sc.wc_model_prompt]

        def done(rc, lines):
            if _grab(lines, "PLAN_READY"):
                load_prep_preview(sc)
                load_plan_ops(sc)
                load_trace(sc, _grab(lines, "TRACE_READY"))
        start_job("plan", sc.wc_name, args, done)
        return {"FINISHED"}


class WC_OT_parts_only(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.parts_only"
    bl_label = "Tách theo part (không cắt)"
    bl_description = "Mỗi part / khối rời của model Tripo thành một mảnh, không cắt gì. Sau đó tự chia / ghép từng mảnh"
    reprep: BoolProperty(default=False)

    def execute(self, ctx):
        sc = ctx.scene
        p = bpy.path.abspath(sc.wc_model)
        if not os.path.exists(p):
            self.report({"ERROR"}, "Chưa có model (bước 2)")
            return {"CANCELLED"}
        args = ["split", "--in", p, "--name", sc.wc_name, "--turn", str(sc.wc_turn), "--tilt", str(sc.wc_tilt), "--parts-only"] +             (["--reprep"] if self.reprep else []) + (["--bumps", "--reprep"] if sc.wc_bumps else []) + [
                "--min", str(sc.wc_min), "--max", str(sc.wc_max), "--bevel", "%.3f" % sc.wc_bevel3, "--tiny", "%.4f" % (sc.wc_tiny / 100.0),
                "--prompt", sc.wc_model_prompt, "--paint" if sc.wc_autopaint else "--no-paint"]

        def done(rc, lines):
            r = _grab(lines, "SPLIT_READY")
            if r and os.path.exists(r):
                sc.wc_plan_ops.clear()
                load_parts(r)
                if CHAIN["stage"] == "split":
                    chain_next(sc, "refine" if sc.wc_autorefine else "decor")
                elif sc.wc_autorefine:                  # tach bo phan xong -> xem tiep tung bo phan (2026-10-06)
                    def _go():
                        if running():
                            return 0.5
                        bpy.ops.woolcut.refine(auto=True)
                        return None
                    bpy.app.timers.register(_go, first_interval=0.3)
            elif CHAIN["stage"] == "split":
                CHAIN["stage"] = None
                sc.wc_decor_msg = "Tự chạy dừng: tách bộ phận lỗi (xem Nhật ký)"
        start_job("split", sc.wc_name, args, done)
        return {"FINISHED"}


class WC_OT_plan_confirm(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.plan_confirm"
    bl_label = "Xác nhận tách"
    bl_description = "Cắt theo kế hoạch (các nhát đang tick, số múi đã chỉnh)"

    def execute(self, ctx):
        sc = ctx.scene
        if not len(sc.wc_plan_ops):
            self.report({"ERROR"}, "Chưa có kế hoạch")
            return {"CANCELLED"}
        save_plan_ops(sc)
        args = ["split", "--name", sc.wc_name, "--keep-plan", "--rounds", "0", "--min", str(sc.wc_min),
                "--max", str(sc.wc_max), "--bevel", "%.3f" % sc.wc_bevel3, "--tiny", "%.4f" % (sc.wc_tiny / 100.0), "--prompt", sc.wc_model_prompt,
                "--paint" if sc.wc_autopaint else "--no-paint"]

        def done(rc, lines):
            r = _grab(lines, "SPLIT_READY")
            if r and os.path.exists(r):
                load_parts(r)
        start_job("split", sc.wc_name, args, done)
        return {"FINISHED"}


class WC_OT_plan_update(bpy.types.Operator):
    bl_idname = "woolcut.plan_update"
    bl_label = "Cập nhật xem trước"
    bl_description = "Chạy thử lại kế hoạch với các nhát đang tick / số múi đã đổi (chỉ hình học, vài giây)"

    def execute(self, ctx):
        if not plan_dry_run(ctx.scene):
            self.report({"ERROR"}, "Đang chạy việc khác")
            return {"CANCELLED"}
        return {"FINISHED"}


class WC_OT_plan_reload(bpy.types.Operator):
    bl_idname = "woolcut.plan_reload"
    bl_label = "Đọc lại kế hoạch"
    bl_description = "Đọc lại plan.json (sau khi sửa tay) và hiện các part để xem trước"

    def execute(self, ctx):
        sc = ctx.scene
        n = load_plan_ops(sc)
        load_prep_preview(sc)
        if not load_trace(sc):
            plan_dry_run(sc)
        self.report({"INFO"}, "%d nhát cắt" % n)
        return {"FINISHED"}


class WC_OT_export(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.export"
    bl_label = "Đặt tên S/M/D & xuất FBX"
    bl_description = "Ghi đúng các mảnh đang có trong viewport (giữ mọi sửa tay) rồi xuất FBX chuẩn bộ gốc"

    def execute(self, ctx):
        sc = ctx.scene
        objs = part_objects()
        if not objs:
            self.report({"ERROR"}, "Chưa có mảnh (bước 3)")
            return {"CANCELLED"}
        work = os.path.join(ROOT, "work", sc.wc_name)
        os.makedirs(work, exist_ok=True)
        path = os.path.join(work, "parts_edit.blend")
        bpy.data.libraries.write(path, set(objs), fake_user=False)

        def done(rc, lines):
            f = _grab(lines, "EXPORT_READY")
            if f and os.path.exists(f):
                import_fbx_result(f, sc.wc_name)
        start_job("export", sc.wc_name, ["export", "--name", sc.wc_name, "--in", path, "--size", "%.3f" % sc.wc_size,
                                         "--pivot", "center" if sc.wc_pivot_center else "origin"], done)
        return {"FINISHED"}


class WC_OT_stop(bpy.types.Operator):
    bl_idname = "woolcut.stop"
    bl_label = "Dừng"

    def execute(self, ctx):
        CHAIN["stage"] = None
        p = JOB["proc"]
        if p and p.poll() is None:
            p.kill()
        return {"FINISHED"}


# ------------------------------------------------------------------ mau / loai tung manh
def _pal_items(self, ctx):
    from .wc import std
    out = []
    for n, nm, _, _ in std.PALETTE:
        if nm and n in std.NOMINAL:
            mn = std.mat_name(n, nm)
            out.append((mn, "%d %s" % (n, nm), ""))
    return out


def _get_color(self):
    from .wc import std
    m = self.data.materials[0].name if getattr(self, "data", None) and self.data.materials else ""
    m = std.canonical(m) or re.sub(r"[.][0-9]{3}$", "", m)
    items = [i[0] for i in _pal_items(self, None)]
    if m not in items:
        m = self.get("wc_color", "")
    return items.index(m) if m in items else 0


def _uv_density():
    try:
        return 2.148 * bpy.context.scene.wc_size / 10.0      # manh o co 10, xuat ra co wc_size
    except AttributeError:
        return 2.148


def _kind(ob):
    k = ob.get("wc_kind") or ob.get("wc_kind_auto") or "S"
    return k


def _set_color(self, value):
    from .wc import look
    mn = [i[0] for i in _pal_items(self, None)][value]
    look.apply_piece(self, _kind(self), mn, unwrap=False)    # D: doi o mau Deco; M/S: doi material (giu UV)


KIND_ITEMS = [("AUTO", "Tự động", ""), ("M", "M (quấn len)", ""), ("S", "S (tĩnh)", ""), ("D", "D (trang trí)", "")]


def _get_kind(self):
    k = self.get("wc_kind", "")
    return ["AUTO", "M", "S", "D"].index(k) if k in ("M", "S", "D") else 0


def _set_kind(self, value):
    from .wc import look, std
    before = _kind(self)
    k = ["AUTO", "M", "S", "D"][value]
    if k == "AUTO":
        if "wc_kind" in self:
            del self["wc_kind"]
    else:
        self["wc_kind"] = k
    after = _kind(self)
    if (before == "D") != (after == "D"):                    # doi giua D (Deco) va M/S (bang mau): doi vat lieu + UV
        col = self.get("wc_color") or std.mat_name(15, "White")
        look.apply_piece(self, after, col, unwrap=True, density=_uv_density())


# ------------------------------------------------------------------ tab "Da lam": danh sach model (2026-10-07)
LIB = {}          # ten -> wc/library.info cua lan quet gan nhat (ve panel khong doc o dia)


class WCLibItem(bpy.types.PropertyGroup):
    stage: StringProperty()
    mb: FloatProperty()
    when: StringProperty()
    fbx: BoolProperty()
    pick: BoolProperty(default=False, description="Tích để xoá / dọn nhiều model một lần")


class WC_UL_lib(bpy.types.UIList):
    def draw_item(self, ctx, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        row = layout.row(align=True)
        row.prop(item, "pick", text="")                # tich chon nhieu model (nguoi dung 2026-10-07)
        sp = row.split(factor=0.58)
        sp.label(text=item.name, icon="CHECKMARK" if item.fbx else "MESH_DATA" if item.stage == "Đã tách" else "FILE_BLANK")
        r = sp.row()
        r.alignment = "RIGHT"
        r.label(text="%.0f MB · %s" % (item.mb, item.when))


def _lib_picked(sc):
    return [it.name for it in sc.wc_lib_items if it.pick]


def _lib_refresh(sc):
    from .wc import library
    keep = sc.wc_lib_items[sc.wc_lib_idx].name if 0 <= sc.wc_lib_idx < len(sc.wc_lib_items) else ""
    picked = set(_lib_picked(sc))                  # giu dau tich qua lan quet lai
    LIB.clear()
    sc.wc_lib_items.clear()
    for r in library.scan():
        LIB[r["name"]] = r
        it = sc.wc_lib_items.add()
        it.name, it.stage, it.when, it.fbx = r["name"], r["stage"], r["when"], bool(r["fbx"])
        it.mb = (r["size_work"] + r["size_out"]) / 2 ** 20
        it.pick = r["name"] in picked
    names = [it.name for it in sc.wc_lib_items]
    sc.wc_lib_idx = names.index(keep) if keep in names else names.index(sc.wc_name) if sc.wc_name in names else 0


def _step_changed(self, ctx):
    if self.wc_step == "LIB":
        try:
            _lib_refresh(self)
        except Exception as e:
            _log("[da lam] quet loi: %s" % e)


def _lib_sel(sc):
    if 0 <= sc.wc_lib_idx < len(sc.wc_lib_items):
        n = sc.wc_lib_items[sc.wc_lib_idx].name
        return LIB.get(n), n
    return None, ""


def _lib_busy(name):
    return (running() and JOB.get("name") == name) or (running("batch") and JOBS["batch"].get("name") == name)


def _view_source(path, turn, tilt):
    """File goc -> xoay / lat + chuan hoa nhu buoc chuan bi (canh dai nhat 10, tam X/Y = 0, day Z = 0): trung cho voi
    cac manh, bat tat collection la so sanh truoc / sau."""
    import math
    from mathutils import Vector
    import_model(path, turn)
    coll = bpy.data.collections.get(COLL_MODEL)
    piv = next((o for o in coll.objects if o.type == "EMPTY"), None) if coll else None
    if piv is None:
        return
    piv.rotation_euler = (math.radians(tilt or 0.0), 0, math.radians(turn or 0.0))

    def box():
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in coll.all_objects if o.type == "MESH" for c in o.bound_box]
        return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])) \
            if pts else (None, None)
    lo, hi = box()
    if lo is None:
        return
    s = 10.0 / (max(hi - lo) or 1.0)
    piv.scale = (s, s, s)
    lo, hi = box()
    piv.location -= Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))


class WC_OT_lib_refresh(bpy.types.Operator):
    bl_idname = "woolcut.lib_refresh"
    bl_label = "Quét lại danh sách"

    def execute(self, ctx):
        _lib_refresh(ctx.scene)
        return {"FINISHED"}


class WC_OT_lib_view_src(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.lib_view_src"
    bl_label = "Xem model gốc"
    bl_description = ("Nạp file gốc (Tripo), xoay và chuẩn hoá như bước chuẩn bị - nằm đúng chỗ các mảnh. "
                      "Bấm 'Mở mảnh đã tách' để so sánh")

    def execute(self, ctx):
        info, n = _lib_sel(ctx.scene)
        if not info or not info["src_exists"]:
            self.report({"ERROR"}, "Không còn file gốc: %s" % (info or {}).get("src", "?"))
            return {"CANCELLED"}
        _view_source(info["src"], info["turn"], info["tilt"])
        self.report({"INFO"}, "Model gốc của %s (xoay %+.0f°)" % (n, info["turn"] or 0))
        return {"FINISHED"}


class WC_OT_lib_open(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.lib_open"
    bl_label = "Mở mảnh đã tách"
    bl_description = ("Đặt model này làm model đang làm (tên, file gốc, góc xoay - để Tách / Cắt lại không chuẩn bị "
                      "lại) và nạp các mảnh: bản chỉnh tay lúc xuất (parts_edit) nếu có, không thì bản cắt (parts)")

    def execute(self, ctx):
        sc = ctx.scene
        info, n = _lib_sel(sc)
        if not info:
            return {"CANCELLED"}
        blend = os.path.join(info["path"], "parts_edit.blend" if info["has_edit"] else "parts.blend")
        if not os.path.exists(blend):
            self.report({"ERROR"}, "%s chưa tách mảnh" % n)
            return {"CANCELLED"}
        auto = sc.wc_autoload
        sc.wc_autoload = False                      # doi file model: chi doi ten / prompt, KHONG tu nap + tu chay chuoi
        try:
            if info["src"]:
                sc.wc_model = info["src"]
        finally:
            sc.wc_autoload = auto
        sc.wc_name = n
        sc.wc_turn = float(info["turn"] or 0.0)
        if hasattr(sc, "wc_tilt"):
            sc.wc_tilt = float(info["tilt"] or 0.0)
        load_parts(blend)
        self.report({"INFO"}, "Đã mở %s (%s)" % (n, os.path.basename(blend)))
        return {"FINISHED"}


class WC_OT_lib_files(bpy.types.Operator):
    bl_idname = "woolcut.lib_files"
    bl_label = "Ảnh trước / sau"
    bl_description = "Mở ảnh model sau bước chuẩn bị (plan_iso) và ảnh các mảnh sau khi tách (parts_all)"
    mode: StringProperty(default="images")

    def execute(self, ctx):
        info, n = _lib_sel(ctx.scene)
        if not info:
            return {"CANCELLED"}
        opened = 0
        if self.mode == "images":
            for f in ("plan_iso.png", "parts_all.png"):
                p = os.path.join(info["path"], f)
                if os.path.exists(p):
                    os.startfile(p)
                    opened += 1
        if not opened:
            os.startfile(info["path"])
        return {"FINISHED"}


def _confirm(op, ctx, event, title, message, ok):
    try:
        return ctx.window_manager.invoke_confirm(op, event, title=title, message=message, confirm_text=ok, icon="WARNING")
    except TypeError:                                # Blender cu: khong co title / message
        return ctx.window_manager.invoke_confirm(op, event)


LIB_SCOPES = [("SEL", "Model đang chọn", ""), ("PICK", "Các model đã tích", ""), ("ALL", "Tất cả model", "")]


def _lib_targets(sc, scope):
    """Ten model ma thao tac nham toi: dong dang chon / cac dong da tich / tat ca."""
    if scope == "ALL":
        return [it.name for it in sc.wc_lib_items]
    if scope == "PICK":
        return _lib_picked(sc)
    _info, n = _lib_sel(sc)
    return [n] if n else []


class WC_OT_lib_pick(bpy.types.Operator):
    bl_idname = "woolcut.lib_pick"
    bl_label = "Tích model"
    bl_description = "Tích / bỏ tích mọi model trong danh sách"
    mode: StringProperty(default="ALL")

    def execute(self, ctx):
        for it in ctx.scene.wc_lib_items:
            it.pick = self.mode == "ALL"
        return {"FINISHED"}


class WC_OT_lib_clean(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.lib_clean"
    bl_label = "Dọn file tạm"
    bl_description = ("Xoá ảnh render từng góc, ảnh decor / tách sâu, bản sao lưu .blend1 (tạo lại được khi cắt lại). "
                      "Giữ kế hoạch, mảnh, chỉnh tay, FBX và ảnh Claude cần đọc lại")
    scope: EnumProperty(items=LIB_SCOPES, default="SEL")

    def invoke(self, ctx, event):
        names = _lib_targets(ctx.scene, self.scope)
        if not names:
            self.report({"WARNING"}, "Chưa tích / chọn model nào")
            return {"CANCELLED"}
        mb = sum(LIB[k]["size_temp"] for k in names if k in LIB) / 2 ** 20
        who = names[0] if len(names) == 1 else "%d model" % len(names)
        return _confirm(self, ctx, event, "Dọn file tạm", "%s: xoá %.0f MB file tạm?" % (who, mb), "Dọn")

    def execute(self, ctx):
        from .wc import library
        sc = ctx.scene
        names = [k for k in _lib_targets(sc, self.scope) if not _lib_busy(k)]
        freed = sum(library.clean(k) for k in names)
        _lib_refresh(sc)
        self.report({"INFO"}, "Đã giải phóng %.0f MB (%d model)" % (freed / 2 ** 20, len(names)))
        return {"FINISHED"}


class WC_OT_lib_delete(_Locked, bpy.types.Operator):
    bl_idname = "woolcut.lib_delete"
    bl_label = "Xoá model"
    bl_description = ("Xoá vĩnh viễn thư mục work của model (kế hoạch, mảnh, chỉnh tay, ảnh) - dòng đang chọn hoặc "
                      "các model đã tích. File gốc giữ nguyên")
    scope: EnumProperty(items=LIB_SCOPES[:2], default="SEL")
    with_out: BoolProperty(name="Xoá cả FBX đã xuất", default=False)

    def invoke(self, ctx, event):
        if not _lib_targets(ctx.scene, self.scope):
            self.report({"WARNING"}, "Chưa tích / chọn model nào")
            return {"CANCELLED"}
        return ctx.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, ctx):
        names = [k for k in _lib_targets(ctx.scene, self.scope) if k in LIB]
        col = self.layout.column(align=True)
        if not names:
            col.label(text="Chưa tích / chọn model nào")
            return
        mb = sum(LIB[k]["size_work"] for k in names) / 2 ** 20
        col.label(text="Xoá vĩnh viễn %d model (%.0f MB):" % (len(names), mb), icon="TRASH")
        for k in names[:12]:
            busy = "  - ĐANG CHẠY, sẽ bỏ qua" if _lib_busy(k) else ""
            col.label(text="   %s · %s · %.0f MB%s" % (k, LIB[k]["stage"], LIB[k]["size_work"] / 2 ** 20, busy))
        if len(names) > 12:
            col.label(text="   … và %d model khác" % (len(names) - 12))
        col.label(text="Gồm kế hoạch, mảnh, chỉnh tay, ảnh - không hoàn tác được")
        col.label(text="File gốc (Downloads / inbox) giữ nguyên", icon="FILE_3D")
        fbx = [k for k in names if LIB[k]["fbx"]]
        if fbx:
            col.separator()
            col.prop(self, "with_out", text="Xoá cả FBX đã xuất của %d model (%.0f MB)" % (
                len(fbx), sum(LIB[k]["size_out"] for k in fbx) / 2 ** 20))

    def execute(self, ctx):
        from .wc import library
        sc = ctx.scene
        names = [k for k in _lib_targets(sc, self.scope) if k in LIB]
        done, skipped, freed = [], [], 0
        for k in names:
            if _lib_busy(k):
                skipped.append(k)
                continue
            freed += library.delete(k, with_out=self.with_out and bool(LIB[k]["fbx"]))
            done.append(k)
            if sc.wc_name == k:
                _log("[da lam] da xoa %s - cac manh dang mo trong canh van con (chua luu)" % k)
        _log("[da lam] xoa %d model: %s" % (len(done), ", ".join(done)))
        _lib_refresh(sc)
        self.report({"WARNING" if skipped else "INFO"}, "Đã xoá %d model, giải phóng %.0f MB%s" % (
            len(done), freed / 2 ** 20, ("; bỏ qua (đang chạy): " + ", ".join(skipped)) if skipped else ""))
        return {"FINISHED"}


# ------------------------------------------------------------------ TACH HANG LOAT (2026-10-07)
# Nguoi dung: "nem nhieu model vao, nap lan luot va tach, sau do t vao soat, tach tiep de xuat FBX". Moi file: run.py auto
# (tim mat truoc -> tach bo phan + dat ten + to mau neu bat) tren O "batch" rieng; xong file nay moi chay file sau.
MODEL_EXTS = (".glb", ".gltf", ".fbx", ".obj")
QUEUE = {"run": False}
QUEUE_ICON = {"chờ": "TIME", "đang chạy": "PLAY", "xong": "CHECKMARK", "lỗi": "ERROR", "bỏ qua": "FORWARD"}


class WCQueueItem(bpy.types.PropertyGroup):
    path: StringProperty()
    status: StringProperty(default="chờ")
    msg: StringProperty()


class WC_UL_queue(bpy.types.UIList):
    def draw_item(self, ctx, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        sp = layout.split(factor=0.62)
        sp.label(text=item.name, icon=QUEUE_ICON.get(item.status, "DOT"))
        sp.label(text=item.status)


def _queue_add_paths(sc, paths):
    have = {os.path.normcase(os.path.abspath(it.path)) for it in sc.wc_queue if it.status in ("chờ", "đang chạy")}
    n = 0
    for p in paths:
        p = os.path.abspath(bpy.path.abspath(p))
        if not os.path.isfile(p) or os.path.splitext(p)[1].lower() not in MODEL_EXTS:
            continue
        if os.path.normcase(p) in have:
            continue
        it = sc.wc_queue.add()
        it.path, it.name, it.status = p, model_name(p), "chờ"
        have.add(os.path.normcase(p))
        n += 1
    return n


def _queue_args(sc, it):
    a = ["auto", "--in", it.path, "--name", it.name, "--min", str(sc.wc_min), "--max", str(sc.wc_max),
         "--bevel", "%.3f" % sc.wc_bevel3, "--tiny", "%.4f" % (sc.wc_tiny / 100.0),
         "--paint" if sc.wc_autopaint else "--no-paint"]
    if getattr(sc, "wc_bumps", False):
        a.append("--bumps")
    if sc.wc_queue_redo:
        a.append("--force")
    if not sc.wc_queue_facing:
        a.append("--no-facing")
    return a


def _queue_next(sc):
    """Chay file 'cho' tiep theo tren O batch; het thi dung va quet lai danh sach Da lam."""
    if not QUEUE["run"] or running("batch"):
        return
    it = next((x for x in sc.wc_queue if x.status == "chờ"), None)
    if it is None:
        QUEUE["run"] = False
        _log("[hang loat] xong hang doi")
        if sc.wc_step == "LIB":
            _lib_refresh(sc)
        _redraw()
        return
    it.status, it.msg = "đang chạy", ""
    key = it.path

    def done(rc, lines):
        x = next((q for q in sc.wc_queue if q.path == key), None)
        if x is not None:
            if _grab(lines, "AUTO_READY") is not None:
                x.status, x.msg = "xong", _sep_short(_grab(lines, "AUTO_READY"), sc)
            elif _grab(lines, "AUTO_SKIP") is not None:
                x.status, x.msg = "bỏ qua", _grab(lines, "AUTO_SKIP")
            else:
                x.status = "lỗi"
                x.msg = (_grab(lines, "AUTO_FAIL") or next((ln for ln in reversed(lines) if ln.strip()), "") or
                         "mã %s" % rc)[:120]
        if sc.wc_step == "LIB":
            try:
                _lib_refresh(sc)
            except Exception as e:
                _log("[hang loat] quet lai loi: %s" % e)

        def _go():
            _queue_next(sc)
            return None
        bpy.app.timers.register(_go, first_interval=0.5)
    if not start_job("batch", it.name, _queue_args(sc, it), done, slot="batch"):
        it.status = "chờ"


class WC_OT_queue_add(bpy.types.Operator):
    bl_idname = "woolcut.queue_add"
    bl_label = "Thêm model vào hàng đợi"
    bl_description = "Chọn nhiều file model (glb / gltf / fbx / obj) để tách lần lượt"
    directory: StringProperty(subtype="DIR_PATH", options={"SKIP_SAVE", "HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"SKIP_SAVE", "HIDDEN"})
    filepath: StringProperty(subtype="FILE_PATH", options={"SKIP_SAVE", "HIDDEN"})
    filter_glob: StringProperty(default="*.glb;*.gltf;*.fbx;*.obj", options={"HIDDEN"})

    def invoke(self, ctx, event):
        if self.directory and len(self.files):      # tha file vao khung 3D (FileHandler) -> them luon
            return self.execute(ctx)
        ctx.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, ctx):
        sc = ctx.scene
        paths = [os.path.join(self.directory, f.name) for f in self.files if f.name]
        if not paths and self.filepath:
            paths = [self.filepath]
        n = _queue_add_paths(sc, paths)
        if sc.wc_step != "LIB":
            sc.wc_step = "LIB"
        self.report({"INFO"}, "Thêm %d model vào hàng đợi" % n)
        return {"FINISHED"}


class WC_OT_queue_add_dir(bpy.types.Operator):
    bl_idname = "woolcut.queue_add_dir"
    bl_label = "Thêm cả thư mục"
    bl_description = "Thêm mọi file model (glb / gltf / fbx / obj) trong một thư mục vào hàng đợi"
    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, ctx, event):
        ctx.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, ctx):
        d = bpy.path.abspath(self.directory)
        paths = sorted(os.path.join(d, f) for f in os.listdir(d)) if os.path.isdir(d) else []
        n = _queue_add_paths(ctx.scene, paths)
        self.report({"INFO"}, "Thêm %d model từ %s" % (n, d))
        return {"FINISHED"}


class WC_OT_queue_remove(bpy.types.Operator):
    bl_idname = "woolcut.queue_remove"
    bl_label = "Bỏ khỏi hàng đợi"
    bl_description = "Bỏ dòng đang chọn / các dòng đã xong / tất cả (không xoá file, không xoá model đã tách)"
    mode: StringProperty(default="SEL")

    def execute(self, ctx):
        sc = ctx.scene
        q = sc.wc_queue
        if self.mode == "SEL":
            idx = [sc.wc_queue_idx] if 0 <= sc.wc_queue_idx < len(q) else []
        elif self.mode == "DONE":
            idx = [i for i, it in enumerate(q) if it.status in ("xong", "bỏ qua")]
        else:
            idx = list(range(len(q)))
        for i in sorted(idx, reverse=True):
            if q[i].status != "đang chạy":
                q.remove(i)
        sc.wc_queue_idx = min(sc.wc_queue_idx, max(0, len(q) - 1))
        return {"FINISHED"}


class WC_OT_queue_start(bpy.types.Operator):
    bl_idname = "woolcut.queue_start"
    bl_label = "Chạy hàng đợi"
    bl_description = ("Tách lần lượt từng model đang chờ (tìm mặt trước -> tách bộ phận + đặt tên, tô màu theo ô ở "
                      "bước 3) - chạy nền, vẫn soát được model khác. Model đã tách thì bỏ qua")

    @classmethod
    def poll(cls, ctx):
        return not running("batch") and any(it.status in ("chờ", "lỗi") for it in ctx.scene.wc_queue)

    def execute(self, ctx):
        for it in ctx.scene.wc_queue:
            if it.status == "lỗi":                    # chay lai muc loi
                it.status, it.msg = "chờ", ""
        QUEUE["run"] = True
        _queue_next(ctx.scene)
        return {"FINISHED"}


class WC_OT_queue_stop(bpy.types.Operator):
    bl_idname = "woolcut.queue_stop"
    bl_label = "Dừng hàng đợi"
    bl_description = "Dừng ngay model đang tách (cả Blender nền / Claude con) và không chạy tiếp"

    def execute(self, ctx):
        QUEUE["run"] = False
        J = JOBS["batch"]
        p = J["proc"]
        if p and p.poll() is None:
            try:                                       # giet ca cay tien trinh (Blender nen, Claude CLI con)
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError:
                p.kill()
        for it in ctx.scene.wc_queue:
            if it.status == "đang chạy":
                it.status, it.msg = "chờ", "đã dừng"
        return {"FINISHED"}


if hasattr(bpy.types, "FileHandler"):
    class WC_FH_queue(bpy.types.FileHandler):
        """Keo tha file model vao khung 3D -> chon 'WoolCut: them vao hang doi tach'."""
        bl_idname = "WC_FH_queue"
        bl_label = "WoolCut: thêm vào hàng đợi tách"
        bl_import_operator = "woolcut.queue_add"
        bl_file_extensions = ";".join(MODEL_EXTS)

        @classmethod
        def poll_drop(cls, ctx):
            return ctx.area is not None and ctx.area.type == "VIEW_3D"
    QUEUE_CLASSES = (WCQueueItem, WC_UL_queue, WC_OT_queue_add, WC_OT_queue_add_dir, WC_OT_queue_remove,
                     WC_OT_queue_start, WC_OT_queue_stop, WC_FH_queue)
else:
    QUEUE_CLASSES = (WCQueueItem, WC_UL_queue, WC_OT_queue_add, WC_OT_queue_add_dir, WC_OT_queue_remove,
                     WC_OT_queue_start, WC_OT_queue_stop)


def _draw_queue(layout, sc):
    box = layout.box()
    head = box.row()
    head.label(text="Tách hàng loạt", icon="SEQ_STRIP_DUPLICATE")
    n_wait = sum(1 for it in sc.wc_queue if it.status == "chờ")
    n_done = sum(1 for it in sc.wc_queue if it.status in ("xong", "bỏ qua"))
    head.label(text="chờ %d · xong %d / %d" % (n_wait, n_done, len(sc.wc_queue)))
    row = box.row(align=True)
    row.operator("woolcut.queue_add", text="Thêm file…", icon="FILE_NEW")
    row.operator("woolcut.queue_add_dir", text="Thêm thư mục…", icon="FILE_FOLDER")
    if not len(sc.wc_queue):
        box.label(text="Hoặc kéo thả file .glb / .fbx vào khung 3D", icon="INFO")
        box.label(text="  rồi chọn 'WoolCut: thêm vào hàng đợi tách'")
        return
    box.template_list("WC_UL_queue", "", sc, "wc_queue", sc, "wc_queue_idx", rows=4)
    if 0 <= sc.wc_queue_idx < len(sc.wc_queue):
        it = sc.wc_queue[sc.wc_queue_idx]
        box.label(text=os.path.basename(it.path), icon="FILE_3D")
        if it.msg:
            for ln in _wrap(it.msg, 50)[:2]:
                box.label(text=ln)
    row = box.row(align=True)
    row.operator("woolcut.queue_remove", text="Bỏ dòng", icon="X").mode = "SEL"
    row.operator("woolcut.queue_remove", text="Bỏ mục xong", icon="CHECKMARK").mode = "DONE"
    row.operator("woolcut.queue_remove", text="Bỏ hết", icon="TRASH").mode = "ALL"
    row = box.row(align=True)
    row.prop(sc, "wc_queue_facing", text="Tự tìm mặt trước")
    row.prop(sc, "wc_queue_redo", text="Làm lại model đã tách")
    if running("batch"):
        J = JOBS["batch"]
        row = box.row()
        row.label(text="Đang tách %s (%ds)" % (J["name"], time.time() - J["t0"]), icon="TIME")
        row.operator("woolcut.queue_stop", text="Dừng", icon="CANCEL")
        if J["lines"]:
            box.label(text=J["lines"][-1][:60])
    else:
        box.operator("woolcut.queue_start", text="Chạy hàng đợi (%d model)" % n_wait, icon="PLAY")
    box.label(text="Dùng ô tô màu, xoá li ti, bo cong ở bước 3; model Claude ở tab Cài đặt", icon="BLANK1")


def _draw_library(layout, sc):
    _draw_queue(layout, sc)
    tot = sum(it.mb for it in sc.wc_lib_items)
    tmp = sum(r["size_temp"] for r in LIB.values()) / 2 ** 20
    row = layout.row()
    row.label(text="%d model · %.0f MB (tạm %.0f MB)" % (len(sc.wc_lib_items), tot, tmp))
    row.operator("woolcut.lib_refresh", text="", icon="FILE_REFRESH")
    layout.template_list("WC_UL_lib", "", sc, "wc_lib_items", sc, "wc_lib_idx", rows=8)
    picked = _lib_picked(sc)
    row = layout.row(align=True)
    row.operator("woolcut.lib_pick", text="Tích tất cả", icon="CHECKBOX_HLT").mode = "ALL"
    row.operator("woolcut.lib_pick", text="Bỏ tích", icon="CHECKBOX_DEHLT").mode = "NONE"
    if picked:
        mb = sum(LIB[k]["size_work"] + LIB[k]["size_out"] for k in picked if k in LIB) / 2 ** 20
        box = layout.box()
        box.label(text="Đã tích %d model · %.0f MB" % (len(picked), mb), icon="CHECKBOX_HLT")
        row = box.row(align=True)
        row.operator("woolcut.lib_delete", text="Xoá %d model đã tích" % len(picked), icon="TRASH").scope = "PICK"
        row.operator("woolcut.lib_clean", text="Dọn tạm", icon="BRUSH_DATA").scope = "PICK"
    info, n = _lib_sel(sc)
    if not info:
        layout.label(text="Bấm làm mới để quét thư mục work", icon="INFO")
        return
    box = layout.box()
    col = box.column(align=True)
    col.label(text=n, icon="OBJECT_DATA")
    col.label(text="%s · sửa lần cuối %s" % (info["stage"], info["when"]))
    col.label(text="Gốc: %s" % (os.path.basename(info["src"]) or "?"), icon="FILE_3D" if info["src_exists"] else "ERROR")
    if info["src"] and not info["src_exists"]:
        col.label(text="  file gốc đã bị xoá / di chuyển")
    col.label(text="Chuẩn bị: %d khối, %s, xoay %+.0f°%s" % (
        info["shells"], "có màu" if info["textured"] else "không màu", info["turn"] or 0,
        (", lật %+.0f°" % info["tilt"]) if info["tilt"] else ""))
    if info["parts"]:
        k = info["kinds"]
        col.label(text="Mảnh: %d (M %d · S %d · D %d)" % (info["parts"], k.get("M", 0), k.get("S", 0), k.get("D", 0)))
    for i, ln in enumerate(_wrap("Thay đổi: " + (info["ops_text"] or "chưa có"), 46)):
        col.label(text=ln if i == 0 else "   " + ln)
    col.label(text="Đặt tên %d · decor %d · chỉnh tay khi xuất: %s" % (
        info["labels"], info["decor"], "có" if info["has_edit"] else "không"))
    col.label(text="FBX: %s" % (info["fbx_when"] or "chưa xuất"), icon="CHECKMARK" if info["fbx"] else "BLANK1")
    if info["prompt"]:
        col.label(text="Prompt: %s…" % info["prompt"][:48])
    col.label(text="Dung lượng: %.0f MB (file tạm %.0f MB)" % (
        (info["size_work"] + info["size_out"]) / 2 ** 20, info["size_temp"] / 2 ** 20))
    row = box.row(align=True)
    row.operator("woolcut.lib_view_src", icon="FILE_3D")
    row.operator("woolcut.lib_open", icon="IMPORT")
    row = box.row(align=True)
    row.operator("woolcut.lib_files", text="Ảnh trước / sau", icon="IMAGE_DATA").mode = "images"
    row.operator("woolcut.lib_files", text="Thư mục", icon="FILE_FOLDER").mode = "folder"
    row = box.row(align=True)
    row.operator("woolcut.lib_clean", text="Dọn file tạm (%.0f MB)" % (info["size_temp"] / 2 ** 20),
                 icon="BRUSH_DATA").scope = "SEL"
    row.operator("woolcut.lib_delete", icon="TRASH").scope = "SEL"
    layout.operator("woolcut.lib_clean", text="Dọn file tạm TẤT CẢ model (%.0f MB)" % tmp, icon="BRUSH_DATA").scope = "ALL"


# ------------------------------------------------------------------ panel
class WCPrefs(bpy.types.AddonPreferences):
    bl_idname = __name__
    tripo_key: StringProperty(name="Tripo API key", subtype="PASSWORD")
    # m_<chuc nang> / e_<chuc nang> (model / effort) them ngay duoi class, theo CLAUDE_TASKS

    def draw(self, ctx):
        self.layout.prop(self, "tripo_key")
        _draw_claude_models(self.layout, self, ctx)


for _k, _vi, _g in CLAUDE_TASKS:
    WCPrefs.__annotations__["m_" + _k] = EnumProperty(name="Model", items=CLAUDE_MODELS, default="PRESET",
                                                      description="Model Claude cho: %s" % CLAUDE_TASK_HELP.get(_k, _vi))
    WCPrefs.__annotations__["e_" + _k] = EnumProperty(name="Effort", items=CLAUDE_EFFORTS, default="PRESET",
                                                      description="Mức suy nghĩ cho: %s" % CLAUDE_TASK_HELP.get(_k, _vi))


def _draw_claude_models(layout, prefs, ctx):
    """Bang model / effort tung chuc nang (Preferences cua addon va khung 'Model Claude' o panel dung chung)."""
    box = layout.box()
    box.label(text="Model Claude cho từng chức năng", icon="SETTINGS")
    sc = getattr(ctx, "scene", None)
    if sc is not None and hasattr(sc, "wc_speed"):
        row = box.row()
        row.label(text="Chế độ chung")
        row.prop(sc, "wc_speed", text="")
    # cot ten rong 40% (truoc chia deu 3 cot -> "Tach sau (xem ca m..." bi cat, nguoi dung 2026-10-07)
    sp = box.split(factor=0.4)
    sp.label(text="Chức năng")
    r = sp.row(align=True)
    r.label(text="Model")
    r.label(text="Effort")
    for k, vi, _g in CLAUDE_TASKS:
        sp = box.split(factor=0.4, align=True)
        sp.label(text=vi)
        r = sp.row(align=True)
        r.prop(prefs, "m_" + k, text="")
        r.prop(prefs, "e_" + k, text="")
    row = box.row(align=True)
    row.operator("woolcut.claude_models", text="Dùng gợi ý", icon="CHECKMARK").mode = "RECOMMEND"
    row.operator("woolcut.claude_models", text="Tất cả theo chế độ", icon="LOOP_BACK").mode = "RESET"
    col = box.column(align=True)
    col.label(text="Gợi ý: Opus cho đặt tên, tô màu, decor,", icon="INFO")
    col.label(text="chia mảnh; Sonnet cho viết prompt", icon="BLANK1")


class WC_OT_claude_models(bpy.types.Operator):
    bl_idname = "woolcut.claude_models"
    bl_label = "Đặt model Claude"
    bl_description = "Dùng gợi ý (Opus cho đặt tên / tô màu / decor / chia mảnh, Sonnet cho viết prompt) hoặc đưa tất cả về theo chế độ chung"
    mode: StringProperty(default="RECOMMEND")

    def execute(self, ctx):
        p = _prefs()
        if p is None:
            self.report({"ERROR"}, "Chưa bật addon WoolCut trong Preferences")
            return {"CANCELLED"}
        for k, _vi, _g in CLAUDE_TASKS:
            mo, ef = CLAUDE_RECOMMENDED.get(k, ("", "")) if self.mode == "RECOMMEND" else ("", "")
            setattr(p, "m_" + k, mo.upper() if mo else "PRESET")
            setattr(p, "e_" + k, ef.upper() if ef else "PRESET")
        ctx.preferences.is_dirty = True                 # luu Preferences (tu luu neu bat Auto-Save Preferences)
        _redraw()
        return {"FINISHED"}


class _P:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "WoolCut"


class WC_PT_main(_P, bpy.types.Panel):
    bl_label = "WoolCut"

    def draw(self, ctx):
        sc = ctx.scene
        col = self.layout.column(align=True)
        row = col.row()
        row.enabled = not running()
        row.prop(sc, "wc_name", text="Tên")
        if running():
            row = col.row()
            row.label(text="Đang chạy: %s (%ds)" % (JOB["kind"], time.time() - JOB["t0"]), icon="TIME")
            row.operator("woolcut.stop", text="", icon="CANCEL")
            if JOB["lines"]:
                col.label(text=JOB["lines"][-1][:60])
        row = col.row(align=True)
        row.operator("woolcut.view_game", text="Xem như trong game", icon="SHADING_TEXTURE").game = True
        row.operator("woolcut.view_game", text="Màu phẳng", icon="SHADING_SOLID").game = False
        col.separator()
        # bam buoc nao chi hien buoc do (2026-10-02); hang 2 = cong cu (Da lam, Cai dat - 2026-10-07)
        row = col.row(align=True)
        for k in ("1", "2", "3", "4", "ALL"):
            row.prop_enum(sc, "wc_step", k)
        row = col.row(align=True)
        row.prop_enum(sc, "wc_step", "LIB", icon="ASSET_MANAGER")
        row.prop_enum(sc, "wc_step", "SET", icon="PREFERENCES")


class WC_PT_models(_P, bpy.types.Panel):
    """Tab "Cai dat" (nguoi dung 2026-10-07: "them 1 tab cai dat") - chi hien khi bam Cai dat o hang nut buoc."""
    @classmethod
    def poll(cls, ctx):
        return ctx.scene.wc_step == "SET"

    bl_label = "Cài đặt"
    bl_parent_id = "WC_PT_main"

    def draw(self, ctx):
        p = _prefs()
        if p is None:
            self.layout.label(text="Bật addon WoolCut trong Preferences", icon="ERROR")
            return
        _draw_claude_models(self.layout, p, ctx)
        box = self.layout.box()
        box.label(text="Tripo", icon="WORLD")
        box.prop(p, "tripo_key", text="API key")
        box.label(text="Lưu trong Preferences của Blender (giữ qua mọi file)", icon="INFO")


class WC_PT_library(_P, bpy.types.Panel):
    """Tab "Da lam" (nguoi dung 2026-10-07): danh sach model, xem goc, da thay doi ra sao, don / xoa cho do ton dung luong."""
    @classmethod
    def poll(cls, ctx):
        return ctx.scene.wc_step == "LIB"

    bl_label = "Model đã làm"
    bl_parent_id = "WC_PT_main"

    def draw(self, ctx):
        _draw_library(self.layout, ctx.scene)


class WC_PT_1(_P, bpy.types.Panel):
    @classmethod
    def poll(cls, ctx):
        return ctx.scene.wc_step in ("1", "ALL")

    bl_label = "1 · Prompt (Claude)"
    bl_parent_id = "WC_PT_main"

    def draw(self, ctx):
        sc = ctx.scene
        col = self.layout.column()
        if running("prompt"):
            col.label(text="Claude đang viết prompt… (%ds)" % (time.time() - JOBS["prompt"]["t0"]), icon="TIME")
        col.row().prop(sc, "wc_pmode", expand=True)
        col.prop(sc, "wc_ptype", text="Dạng")
        col.prop(sc, "wc_theme", text="Chủ đề")
        col.prop(sc, "wc_idea", text="Ý tưởng")
        col.operator("woolcut.prompt", icon="OUTLINER_OB_LIGHT")
        if sc.wc_prompt:
            img = sc.wc_prompt_mode == "IMAGE"
            box = col.box()
            if sc.wc_prompt_name:
                box.label(text=sc.wc_prompt_name + ("  · prompt ảnh" if img else "  · text → 3D"), icon="FILE_TEXT")
            for line in _wrap(sc.wc_prompt_vi or sc.wc_prompt, 44):
                box.label(text=line)
            box.operator("woolcut.copy_prompt", icon="COPYDOWN",
                         text="Copy prompt ảnh (dán vào công cụ tạo ảnh)" if img else "Copy prompt (dán lên web Tripo)")
            if img:
                # soat ANH truoc khi len 3D: lam lai anh re hon lam lai model (100 credit)
                sub = box.column(align=True)
                sub.label(text="Soát ảnh trước khi đưa vào Image to 3D:", icon="VIEWZOOM")
                for c in [x.strip() for x in sc.wc_prompt_check.split("·") if x.strip()] + [
                        "Mảng da / thân cùng màu ≤ 1/4 model", "Chỗ chạm nhau khác màu, đồ cầm xa thân",
                        "Toàn thân, nền trơn, không hoạ tiết in"]:
                    for i, ln in enumerate(_wrap(c, 46)):
                        sub.label(text=("• " if i == 0 else "   ") + ln)
                sub.label(text="Web Tripo: Smart Mesh · P2.0 · Quad · ~11–12k mặt", icon="INFO")


class WC_PT_2(_P, bpy.types.Panel):
    @classmethod
    def poll(cls, ctx):
        return ctx.scene.wc_step in ("2", "ALL")

    bl_label = "2 · Model (Tripo)"
    bl_parent_id = "WC_PT_main"

    def draw(self, ctx):
        if running():
            self.layout.label(text="Đang chạy %s… chờ xong" % JOB["kind"], icon="TIME")
            return
        sc = ctx.scene
        col = self.layout.column()
        col.prop(sc, "wc_prompt", text="Prompt")
        col.prop(sc, "wc_faces", text="Số mặt")
        row = col.row(align=True)
        op = row.operator("woolcut.gen", text="Ước tính")
        op.send = False
        op = row.operator("woolcut.gen", text="Gửi Tripo", icon="ERROR")
        op.send = True
        col.separator()
        col.prop(sc, "wc_model", text="Model")
        row = col.row(align=True)
        row.operator("woolcut.load_model", icon="IMPORT")
        row.prop(sc, "wc_autoload", text="Tự nạp khi chọn")
        col.prop(sc, "wc_autochain", text="Tự chạy hết: mặt trước → tách → tách sâu → decor")
        row = col.row(align=True)
        row.label(text="Xoay %+.0f°" % sc.wc_turn)
        row.operator("woolcut.turn", text="-90").deg = -90
        row.operator("woolcut.turn", text="+90").deg = 90
        row = col.row(align=True)
        row.label(text="Lật %+.0f°" % sc.wc_tilt)
        op = row.operator("woolcut.turn", text="Lật ↑")
        op.deg, op.tilt = 0, 90
        op = row.operator("woolcut.turn", text="Lật ↓")
        op.deg, op.tilt = 0, -90
        row = col.row(align=True)
        row.operator("woolcut.facing", icon="VIEW_CAMERA")
        row.prop(sc, "wc_autoface", text="Tự làm khi nạp")


def _sep_kind(sc):
    k = sc.wc_ptype.lower()
    from .wc import sep
    return k if k in sep.TARGET else "char"


_SEP = {}


def _sep_measure(name):
    """Model prep truoc 2026-10-07 chua co "sep" trong prep.json: do mot lan tu prep.npz (~0.3 s), nho theo mtime.
    Chi doc, khong ghi lai prep.json."""
    npz = os.path.join(ROOT, "work", name, "prep.npz")
    if not os.path.exists(npz):
        return None
    key = (npz, os.path.getmtime(npz))
    if key not in _SEP:
        try:
            import numpy as np
            from .wc import sep
            from .wc.tm import TM
            z = np.load(npz)
            tms, i = [], 0
            while "V%d" % i in z:
                tms.append(TM(z["V%d" % i], z["F%d" % i], z["C%d" % i]))
                i += 1
            _SEP[key] = sep.measure(tms)
        except Exception as e:
            _log("[do tach] loi: %s" % e)
            _SEP[key] = None
    return _SEP[key]


def _draw_sep(col, meta, sc):
    """Do de tach (prep.json "sep", wc/sep.py) so voi bo goc cung dang o buoc 1 - biet som model nao kho tach."""
    m = meta.get("sep") or _sep_measure(meta.get("name") or sc.wc_name)
    if not m:
        return
    from .wc import sep, categories as cat
    k = _sep_kind(sc)
    lvl, why = sep.verdict(m, k)
    why = [w for w in why if not w.startswith("Model không có màu")]   # da bao o tren
    g = sep.TARGET[k]
    if lvl == "ok":
        col.label(text="Dễ tách: %d bộ phận màu, mảng lớn nhất %.0f%% (mẫu %d / %.0f%%)" % (
            m["parts"], 100 * m["largest"], g["parts"], 100 * g["largest"]), icon="CHECKMARK")
        return
    box = col.box()
    box.label(text="%s so với mẫu %s" % ("Rất khó tách" if lvl == "rat kho" else "Khó tách",
                                         cat.FORMATS[k]["vi"].lower()), icon="ERROR")
    for w in why:
        for ln in _wrap(w, 48):
            box.label(text=ln)
    box.label(text="Tạo lại theo 'Prompt ảnh' ở bước 1 sẽ dễ tách hơn", icon="INFO")


def _sep_short(name, sc):
    """Mot dong cho hang doi: 'khó tách: mảng 42%, 14 bộ phận' (rong neu de tach / chua co so do)."""
    try:
        m = json.load(open(os.path.join(ROOT, "work", name, "prep.json"), encoding="utf-8")).get("sep")
        m = m or _sep_measure(name)
    except (OSError, ValueError):
        return ""
    if not m:
        return ""
    from .wc import sep
    lvl, _ = sep.verdict(m, _sep_kind(sc))
    if lvl == "ok":
        return "dễ tách: %d bộ phận" % m["parts"]
    return "%s: mảng %.0f%%, %d bộ phận" % ("rất khó tách" if lvl == "rat kho" else "khó tách", 100 * m["largest"],
                                            m["parts"])


class WC_PT_3(_P, bpy.types.Panel):
    @classmethod
    def poll(cls, ctx):
        return ctx.scene.wc_step in ("3", "ALL")

    bl_label = "3 · Tách mảnh"
    bl_parent_id = "WC_PT_main"

    def draw(self, ctx):
        if running():
            self.layout.label(text="Đang chạy %s… chờ xong" % JOB["kind"], icon="TIME")
            return
        sc = ctx.scene
        col = self.layout.column()
        pj = os.path.join(ROOT, "work", sc.wc_name, "prep.json")
        if os.path.exists(pj):
            try:
                meta = json.load(open(pj, encoding="utf-8"))
                if len(meta.get("names", [])) <= 1:
                    col.label(text="Model không có màu: chỉ tách theo hình", icon="ERROR")
                if os.path.abspath(meta.get("src", "")) != os.path.abspath(bpy.path.abspath(sc.wc_model)) and sc.wc_model:
                    col.label(text="Tên này đang chứa model khác - sẽ dựng lại", icon="ERROR")
                _draw_sep(col, meta, sc)
            except (OSError, ValueError):
                pass
        # 2026-10-05: bo Claude lap ke hoach / tach tu dong - nguoi dung tach bo phan roi tu chia tung mesh
        col.operator("woolcut.parts_only", text="Tách bộ phận + đặt tên", icon="OUTLINER_OB_GROUP_INSTANCE").reprep = False
        row = col.row(align=True)
        row.prop(sc, "wc_autorefine", text="Rồi tách sâu (xem cả model)")
        row.prop(sc, "wc_refine_rounds", text="Lần")
        row = col.row(align=True)
        row.operator("woolcut.refine", icon="VIEWZOOM")
        row.prop(sc, "wc_refine_min", text="Từ %")
        col.prop(sc, "wc_autopaint", text="Tô màu theo bảng khi tách")
        col.prop(sc, "wc_bumps", text="Tự tách u nhô (chỉ model liền 1 khối)")
        row = col.row(align=True)
        row.prop(sc, "wc_tiny", text="Xoá mảnh li ti < (% cỡ)")
        row.operator("woolcut.drop_tiny", text="", icon="TRASH")
        col.prop(sc, "wc_bevel3", text="Bo cong mép cắt")
        row = col.row(align=True)
        row.operator("woolcut.open", text="Bảng mảnh").what = "sheet"
        row.operator("woolcut.open", text="Thư mục").what = "work"
        objs = part_objects()
        if objs:
            cnt = collections.Counter(o.get("wc_kind") or o.get("wc_kind_auto", "?") for o in objs)
            col.label(text="%d mảnh: %d M · %d S · %d D" % (len(objs), cnt["M"], cnt["S"], cnt["D"]))
            ob = ctx.active_object
            if ob and ob in objs:
                box = col.box()
                box.label(text=ob.name, icon="MESH_DATA")
                box.prop(ob, "wc_color_ui", text="Màu")
                box.prop(ob, "wc_kind_ui", text="Loại")
            box = col.box()
            box.label(text="Chia mảnh đang chọn", icon="MOD_EDGESPLIT")
            box.prop(sc, "wc_split_preview", text="Xem trước nhát cắt (đỏ) + viền mảnh chọn (vàng)")
            box.prop(sc, "wc_split_pattern", text="")
            row = box.row(align=True)
            row.prop(sc, "wc_split_n", text="N")
            row.prop(sc, "wc_split_m", text="M")
            row = box.row(align=True)
            row.label(text="Xoay mặt cắt (độ):")
            row.prop(sc, "wc_split_world", text="Trục thế giới", toggle=True)
            row.operator("woolcut.split_rot_reset", text="", icon="LOOP_BACK")
            row = box.row(align=True)
            row.prop(sc, "wc_split_rot", index=0, text="X")
            row.prop(sc, "wc_split_rot", index=1, text="Y")
            row.prop(sc, "wc_split_rot", index=2, text="Z")
            row = box.row(align=True)
            row.operator("woolcut.split_piece", text="Chia", icon="MOD_EXPLODE")
            box.prop(sc, "wc_piece_hint", text="", placeholder="Yêu cầu cho Claude, vd: tách mũ và vành mũ khỏi đầu")
            box.operator("woolcut.ai_split_piece", icon="SHADERFX")
            row.operator("woolcut.undo_split", text="Hoàn tác (%d)" % len(UNDO) if UNDO else "Hoàn tác", icon="LOOP_BACK")
            row = col.row(align=True)
            row.operator("woolcut.join", text="Ghép", icon="AUTOMERGE_ON")
            row.operator("woolcut.label", text="", icon="SORTALPHA")
            row.operator("woolcut.remesh_piece", text="Mesh lại", icon="MOD_REMESH")
            row.operator("woolcut.drop_piece", text="Xoá", icon="TRASH")
            col.operator("woolcut.shell_split", text="Tách vỏ + dựng phần bên trong", icon="MOD_SOLIDIFY")
            col.operator("woolcut.paint_ai", text="Claude tô màu theo bảng", icon="BRUSH_DATA")
            col.operator("woolcut.split", text="Cắt lại toàn bộ (áp lại các lần chia)", icon="FILE_REFRESH").mode = "recut"
            box = col.box()
            row = box.row(align=True)
            nd = sum(1 for o in objs if o.get("wc_decor"))
            row.prop(sc, "wc_decor_open", text="", emboss=False,
                     icon="TRIA_DOWN" if sc.wc_decor_open else "TRIA_RIGHT")      # thu gon / mo rong (2026-10-05)
            row.label(text="Decor (%d/%d tick, đã gắn %d)" % (sum(1 for it in sc.wc_decor_items if it.enabled),
                                                            len(sc.wc_decor_items), nd), icon="OUTLINER_OB_POINTCLOUD")
            row.operator("woolcut.decor_tick", text="", icon="FILE_REFRESH").mode = "reload"
            if sc.wc_decor_open:
                if not len(sc.wc_decor_items):
                    box.operator("woolcut.decor_tick", text="Nạp danh sách decor", icon="IMPORT").mode = "reload"
                row = box.row(align=True)
                row.operator("woolcut.decor_tick", text="Tick tất cả").mode = "all"
                row.operator("woolcut.decor_tick", text="Bỏ tất cả").mode = "none"
                row.operator("woolcut.decor_tick", text="Chỉ mặt").mode = "face"
                box.template_list("WC_UL_decor", "", sc, "wc_decor_items", sc, "wc_decor_idx", rows=6)
            box.operator("woolcut.decor_ai", icon="SHADERFX")
            if sc.wc_decor_msg:
                box.label(text=sc.wc_decor_msg, icon="INFO")
            if sc.wc_decor_open:
                box.operator("woolcut.decor_clear", icon="TRASH")
                box.label(text="Bỏ decor thừa: chọn decor → Xoá (có Hoàn tác)", icon="INFO")
        # 2026-10-07 nguoi dung: bo nut "Lam lai tu dau (dung khoi lai)" - prep tu dung lai khi doi model / PREP_VERSION


class WC_PT_4(_P, bpy.types.Panel):
    @classmethod
    def poll(cls, ctx):
        return ctx.scene.wc_step in ("4", "ALL")

    bl_label = "4 · Đặt tên & xuất FBX"
    bl_parent_id = "WC_PT_main"

    def draw(self, ctx):
        if running():
            self.layout.label(text="Đang chạy %s… chờ xong" % JOB["kind"], icon="TIME")
            return
        col = self.layout.column()
        col.prop(ctx.scene, "wc_size", text="Cỡ (cạnh dài nhất)")
        col.prop(ctx.scene, "wc_pivot_center", text="Tâm mỗi mảnh ở giữa mảnh")
        col.label(text="BearArt 8,2 · trung vị bộ gốc 6,1", icon="INFO")
        col.operator("woolcut.export", icon="EXPORT")
        col.operator("woolcut.open", text="Mở thư mục out").what = "out"


class WC_PT_log(_P, bpy.types.Panel):
    bl_label = "Nhật ký"
    bl_parent_id = "WC_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, ctx):
        col = self.layout.column(align=True)
        for ln in list(LOG)[-28:]:
            col.label(text=ln[:70])


CLASSES = (WC_OT_refine, WC_OT_split_rot_reset, WC_OT_ai_split_piece, WCDecorItem, WC_UL_decor, WC_OT_paint_ai, WC_OT_decor_ai, WC_OT_decor_tick, WC_OT_decor_clear, WC_OT_label, WC_OT_drop_tiny, WC_OT_drop_piece, WC_OT_remesh_piece, WCPlanOp, WC_UL_plan, WC_OT_plan_only, WC_OT_parts_only, WC_OT_plan_confirm, WC_OT_plan_reload, WC_OT_plan_update, WC_OT_prompt, WC_OT_copy_prompt, WC_OT_facing, WC_OT_view_game, WC_OT_prompt_from_step1, WC_OT_gen, WC_OT_load_model, WC_OT_turn, WC_OT_split, WC_OT_split_piece,
           WC_OT_undo_split, WC_OT_open, WC_OT_join, WC_OT_shell_split,
           WC_OT_export, WC_OT_stop, WC_OT_claude_models, WCLibItem, WC_UL_lib, WC_OT_lib_refresh, WC_OT_lib_view_src,
           WC_OT_lib_open, WC_OT_lib_files, WC_OT_lib_pick, WC_OT_lib_clean, WC_OT_lib_delete, WCPrefs, WC_PT_main, WC_PT_1, WC_PT_2,
           WC_PT_3, WC_PT_4, WC_PT_library, WC_PT_models, WC_PT_log) + QUEUE_CLASSES


def register():
    # module con cu (wc.tm, wc.plan...) con trong sys.modules -> "Reload Scripts" chi nap lai __init__, con wc.* van ban
    # cu (2026-10-05: fillet.py moi goi plane_cut(shift_rel=) cua tm.py cu -> loi bi nuot, khong bo cong). Xoa de nap moi.
    for k in [k for k in sys.modules if k.startswith(__name__ + ".wc")]:
        del sys.modules[k]
    for c in CLASSES:
        bpy.utils.register_class(c)
    S = bpy.types.Scene
    S.wc_name = StringProperty(default="Model")
    S.wc_idea = StringProperty(default="")
    from .wc import categories as cat
    S.wc_ptype = EnumProperty(name="Dạng", items=[(k.upper(), vi, hint) for k, vi, hint in cat.items_formats()],
                              default="CHAR")
    S.wc_theme = EnumProperty(name="Chủ đề", items=[(k.upper(), vi, en) for k, vi, en in cat.items_themes()],
                              default="FREE")
    S.wc_prompt = StringProperty(default="")
    S.wc_prompt_vi = StringProperty(default="")
    # 2026-10-07: nguoi dung tao model tren web Tripo bang Image to 3D -> mac dinh viet prompt TAO ANH
    S.wc_pmode = EnumProperty(name="Kiểu", default="IMAGE", items=[
        ("IMAGE", "Ảnh → 3D (web)", "Prompt tạo ẢNH, rồi đưa ảnh vào Image to 3D trên web Tripo. Theo số liệu 108 model "
                                    "gốc: nhân vật mặc nhiều lớp đồ, ~26 bộ phận màu, mảng cùng màu ≤ 1/4"),
        ("TEXT", "Text → 3D", "Prompt dán thẳng vào Text to 3D (web hoặc nút Gửi Tripo ở bước 2)")])
    S.wc_prompt_mode = StringProperty(default="TEXT")     # kieu cua prompt DANG CO (copy / gui Tripo dua vao)
    S.wc_prompt_check = StringProperty(default="")        # dieu can soat tren anh (prompt anh)
    S.wc_faces = IntProperty(default=8000, min=500, max=20000)
    S.wc_model = StringProperty(default="", subtype="FILE_PATH", update=_model_changed)
    S.wc_size = FloatProperty(default=8.2, min=1.0, max=50.0, description="Cạnh dài nhất của model khi mở trong Blender")
    S.wc_turn = FloatProperty(default=-90.0)
    S.wc_min = IntProperty(default=15, min=1, max=200)
    S.wc_max = IntProperty(default=35, min=1, max=300)
    S.wc_rounds = IntProperty(default=1, min=0, max=3)
    S.wc_split_pattern = EnumProperty(items=SPLIT_PATTERNS, default="AUTO")
    S.wc_split_preview = BoolProperty(default=True)
    S.wc_pivot_center = BoolProperty(default=True, description="Tắt: tâm mọi mảnh ở gốc model như BearArt")
    S.wc_prompt_name = StringProperty(default="")
    S.wc_autorefine = BoolProperty(default=True, description="Tách bộ phận xong: Claude xem cả model, tách mảnh gộp hai "
                                   "bộ phận theo nếp gấp, ghép mảnh bị xé (vỏ mũ + mặt = đầu), tay → cánh tay + bàn tay...")
    S.wc_refine_rounds = IntProperty(default=3, min=1, max=4, description="Số lần xem cả model (mỗi lần: tách / ghép / "
                                     "đổi tên rồi xem lại); dừng sớm khi Claude thấy hết chỗ sửa")
    S.wc_refine_min = FloatProperty(default=2.5, min=0.2, max=50.0, description="Chỉ xem bộ phận chiếm ít nhất % thể "
                                    "tích model này")
    S.wc_tilt = FloatProperty(default=0.0, description="Lật model quanh trục X (độ): model nằm ngửa / úp")
    S.wc_split_rot = bpy.props.FloatVectorProperty(size=3, default=(0.0, 0.0, 0.0), min=-180.0, max=180.0, step=500,
                                                   precision=0, update=_rot_changed,
                                                   description="Xoay mặt cắt quanh trục X / Y / Z thế giới (độ) - "
                                                               "khung đỏ xem trước xoay theo")
    S.wc_split_world = BoolProperty(default=False, update=_rot_changed,
                                    description="Bật: mặt cắt theo trục thế giới (không tự nghiêng theo khối dài)")
    S.wc_autochain = BoolProperty(default=False, description="Nạp model xong tự chạy: tìm mặt trước → tách bộ phận + đặt "
                                  "tên (+ tô màu nếu bật) → Claude gắn decor (các decor đang tick). ~3-5 phút")
    S.wc_piece_hint = StringProperty(default="", description="Yêu cầu cho Claude khi chia mảnh đang chọn, vd: "
                                     "tách mũ và vành mũ khỏi đầu; tách yên khỏi thân")
    S.wc_bumps = BoolProperty(default=False, description="Ép tách mắt, mũi, tai... thành khối riêng trước khi cắt. "
                              "Chỉ dùng cho model LIỀN MỘT KHỐI; model đã chia part thì làm băm nát chi tiết")
    S.wc_decor_items = CollectionProperty(type=WCDecorItem)
    S.wc_decor_idx = IntProperty(default=0)
    S.wc_decor_msg = StringProperty(default="")
    S.wc_decor_open = BoolProperty(default=True, description="Mở / thu gọn danh sách decor")

    def _init_decor():
        for scn in bpy.data.scenes:
            try:
                if not len(scn.wc_decor_items):
                    load_decor_items(scn)
            except Exception:
                pass
        return None
    bpy.app.timers.register(_init_decor, first_interval=0.5)
    S.wc_autoload = BoolProperty(default=True, description="Chọn file model là nạp vào cảnh ngay (và tự tìm mặt trước)")
    S.wc_tiny = FloatProperty(default=2.5, min=0.0, max=10.0, description="Xoá mảnh có cạnh dài nhất nhỏ hơn % này "
                              "của cỡ model (vật li ti khó nhìn thấy). 0 = giữ hết")
    S.wc_plan_ops = CollectionProperty(type=WCPlanOp)
    S.wc_plan_idx = IntProperty(default=0, update=_plan_idx_changed)
    S.wc_plan_preview = BoolProperty(default=True, update=_plan_idx_changed)
    S.wc_step = EnumProperty(name="Bước", items=[("1", "1 Prompt", "Bước 1: Claude viết prompt"),
                                                 ("2", "2 Model", "Bước 2: tạo / nạp model Tripo"),
                                                 ("3", "3 Tách", "Bước 3: tách mảnh, chia, tô màu"),
                                                 ("4", "4 Xuất", "Bước 4: đặt tên, xuất FBX"),
                                                 ("ALL", "Tất cả", "Hiện mọi bước"),
                                                 ("LIB", "Đã làm", "Danh sách model đã làm: xem gốc, thay đổi, "
                                                                   "dung lượng, dọn / xoá"),
                                                 ("SET", "Cài đặt", "Model Claude cho từng chức năng, khoá Tripo")],
                             default="ALL", update=_step_changed)
    S.wc_lib_items = CollectionProperty(type=WCLibItem)
    S.wc_lib_idx = IntProperty(default=0)
    S.wc_queue = CollectionProperty(type=WCQueueItem)
    S.wc_queue_idx = IntProperty(default=0)
    S.wc_queue_facing = BoolProperty(default=True, description="Mỗi model: Claude tìm mặt trước rồi mới tách "
                                     "(tắt: file web xoay 0, file Tripo API trong inbox xoay -90)")
    S.wc_queue_redo = BoolProperty(default=False, description="Tách lại cả model đã tách trước đó (GHI ĐÈ kế hoạch, "
                                   "chỉnh tay, đặt tên). Tắt: bỏ qua model đã có")
    S.wc_bevel3 = FloatProperty(default=0.15, min=0.0, max=0.5, description="Bán kính bo tròn mép cắt (cạnh model 10). "
                               "0 = mép vuông; mảnh kề nhau thành rãnh tròn như model mẫu")
    S.wc_autoface = BoolProperty(default=True, description="Nạp model xong: chụp 4 hướng, Claude chọn mặt trước rồi xoay")
    S.wc_model_prompt = StringProperty(default="", description="Prompt đã tạo model này - Claude đọc khi lập kế "
                                       "hoạch cắt, soát và tô màu (tự điền khi model do bước 2 tạo)")
    if _DRAW["handle"] is None:
        _DRAW["handle"] = bpy.types.SpaceView3D.draw_handler_add(_draw_preview, (), "WINDOW", "POST_VIEW")
    S.wc_split_n = IntProperty(default=2, min=2, max=16, description="Số múi / lát (N)")
    S.wc_split_m = IntProperty(default=2, min=1, max=8, description="Số tầng (M)")
    S.wc_autopaint = BoolProperty(default=True, description="Sau khi cắt: Claude chọn màu bảng cho từng mảnh "
                                  "(model không màu: tô toàn bộ; có texture: sửa màu sai)")
    S.wc_speed = EnumProperty(items=[("NORMAL", "Vừa", "Lập kế hoạch effort medium (mặc định)"),
                                     ("FAST", "Nhanh", "Sonnet, effort low - nhanh, kém kỹ hơn"),
                                     ("CAREFUL", "Kỹ", "Effort high - chậm, kỹ nhất")], default="NORMAL")
    S.wc_remesh = BoolProperty(default=False, description="Tắt: giữ nguyên bề mặt Tripo, chỉ thêm đường cắt")
    bpy.types.Object.wc_color_ui = EnumProperty(items=_pal_items, get=_get_color, set=_set_color)
    bpy.types.Object.wc_kind_ui = EnumProperty(items=KIND_ITEMS, get=_get_kind, set=_set_kind)


def unregister():
    if _PREV["coll"] is not None:
        from bpy.utils import previews as _pv
        _pv.remove(_PREV["coll"])
        _PREV["coll"] = None
    if _DRAW["handle"] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW["handle"], "WINDOW")
        _DRAW["handle"] = None
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    for k in ("wc_name", "wc_idea", "wc_prompt", "wc_prompt_vi", "wc_faces", "wc_model", "wc_turn", "wc_min",
              "wc_max", "wc_rounds", "wc_remesh", "wc_size", "wc_speed", "wc_ptype", "wc_autopaint", "wc_theme",
              "wc_split_pattern", "wc_split_n", "wc_split_m",
              "wc_split_preview", "wc_prompt_name", "wc_pivot_center", "wc_model_prompt", "wc_autoface", "wc_bevel3", "wc_step", "wc_plan_ops", "wc_plan_idx", "wc_plan_preview", "wc_tiny", "wc_autoload", "wc_decor_items", "wc_decor_idx", "wc_decor_msg", "wc_decor_open", "wc_bumps", "wc_piece_hint", "wc_autochain", "wc_split_rot", "wc_split_world", "wc_tilt", "wc_autorefine", "wc_refine_rounds", "wc_refine_min", "wc_lib_items", "wc_lib_idx", "wc_queue", "wc_queue_idx", "wc_queue_facing", "wc_queue_redo", "wc_pmode", "wc_prompt_mode",
              "wc_prompt_check"):
        if hasattr(bpy.types.Scene, k):
            delattr(bpy.types.Scene, k)
    for k in ("wc_color_ui", "wc_kind_ui"):
        if hasattr(bpy.types.Object, k):
            delattr(bpy.types.Object, k)
