"""DANH SACH MODEL DA LAM (nguoi dung 2026-10-07: "list cac model da lam, xem model goc, da thay doi ra sao, xoa model
de tranh ton dung luong"). Moi model = thu muc work/<Ten> (+ file out/<Ten>.*). Khong can bpy: addon (tab "Da lam") va
python he thong deu dung duoc.

Dung luong (do 2026-10-07, 34 model, work 1,2 GB): ~70% la anh render PNG + ban sao luu .blend1 - tao lai duoc.
  clean(ten)  : xoa FILE TAM (anh render tung goc, anh decor / tach sau, .blend1, blend dau vao cua Claude); GIU ke hoach,
                manh (parts*.blend), buoc chuan bi, anh ghep Claude doc lai (plan_*, parts_sheet / _all / _ids_all).
  delete(ten) : xoa ca thu muc work/<Ten> (+ out/<Ten>.* neu with_out). KHONG BAO GIO xoa file goc (Downloads / inbox)."""
import os, json, glob, time, shutil, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(HERE, "work")
OUT = os.path.join(HERE, "out")
# blend dau vao cho cac buoc Claude (moi lan chay ghi lai)
TEMP_BLENDS = ("struct_in.blend", "refine_in.blend", "parts_decor.blend", "piece_ai.blend", "parts_paint.blend")
# anh Claude con doc lai khi bam nut (dat ten / to mau / soat) ma khong cat lai -> giu
KEEP_PNG = ("plan_front.png", "plan_right.png", "plan_back.png", "plan_left.png", "plan_top.png", "plan_iso.png",
            "facing.png", "parts_sheet.png", "parts_all.png", "parts_ids_all.png")
OPS_VI = collections.OrderedDict([
    ("chia", ("split", "slices", "sectors", "grid", "crease", "cut", "part")), ("ghép", ("merge",)),
    ("xoá", ("drop",)), ("mesh lại", ("remesh",)), ("tách vỏ", ("shell",)), ("tô màu", ("color",)),
    ("đổi loại", ("kind",)), ("miếng dán", ("decal",))])


def clean_name(name):
    """= wc/export.clean_name (ten file FBX trong out/)."""
    import re
    s = re.sub(r"[^A-Za-z0-9]", "", name)
    if not s or not s[0].isalpha():
        s = "Model" + s
    return s


def _du(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    n = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                n += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return n


def _json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def work_dir(name):
    """Duong dan work/<Ten> - chi nhan ten la thu muc con TRUC TIEP cua work (chong xoa nham ngoai)."""
    if not name or name in (".", "..") or os.sep in name or "/" in name or "\\" in name:
        raise ValueError("tên model không hợp lệ: %r" % name)
    p = os.path.realpath(os.path.join(WORK, name))
    if os.path.dirname(p) != os.path.realpath(WORK):
        raise ValueError("ngoài thư mục work: %s" % p)
    return p


def out_files(name):
    cn = clean_name(name)
    fs = glob.glob(os.path.join(OUT, cn + ".*")) + glob.glob(os.path.join(OUT, cn + "_*"))
    return sorted(f for f in set(fs) if os.path.isfile(f))


def temp_files(name):
    d = work_dir(name)
    out = []
    for root, _dirs, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            top = os.path.dirname(p) == d
            if f.endswith(".blend1") or (top and f in TEMP_BLENDS) or \
                    (f.lower().endswith(".png") and not (top and f in KEEP_PNG)):
                out.append(p)
    return out


def ops_summary(ops):
    """'chia 9 · ghép 1 · tô màu 27' tu danh sach thao tac plan.json."""
    cnt = collections.Counter(o.get("op") for o in ops or [] if not o.get("skip"))
    parts = []
    for vi, keys in OPS_VI.items():
        n = sum(cnt.get(k, 0) for k in keys)
        if n:
            parts.append("%s %d" % (vi, n))
    other = sum(n for k, n in cnt.items() if not any(k in ks for ks in OPS_VI.values()))
    if other:
        parts.append("khác %d" % other)
    return " · ".join(parts)


def info(name):
    d = work_dir(name)
    files = [os.path.join(r, f) for r, _ds, fs in os.walk(d) for f in fs]
    mtime = max((os.path.getmtime(f) for f in files), default=os.path.getmtime(d))
    prep = _json(os.path.join(d, "prep.json"), {}) or {}
    parts = (_json(os.path.join(d, "parts.json"), {}) or {}).get("parts", [])
    plan = _json(os.path.join(d, "plan.json"), {}) or {}
    labels = _json(os.path.join(d, "labels.json"), []) or []
    decor = _json(os.path.join(d, "decor.json"), []) or []
    outs = out_files(name)
    fbx = next((f for f in outs if f.lower().endswith(".fbx")), "")
    src = prep.get("src", "")
    prompt = ""
    try:
        from . import prompt as pr
        prompt = pr.find_prompt(src, name, d)
    except Exception:
        pass
    kinds = collections.Counter(p.get("kind") for p in parts)
    temp = temp_files(name)
    stage = ("Đã xuất FBX" if fbx else "Đã tách" if parts else "Mới chuẩn bị" if prep else "Trống")
    score = _json(os.path.join(d, "score.json"), None) or {}          # bang cham diem gan nhat (2026-10-07)
    draft = sorted(f for f in (os.listdir(os.path.join(d, "draft")) if os.path.isdir(os.path.join(d, "draft")) else [])
                   if f.lower().endswith(".fbx"))
    try:
        from . import learn
        good = learn.get(name) is not None
    except Exception:
        good = False
    return dict(
        name=name, path=d, mtime=mtime, when=time.strftime("%d/%m %H:%M", time.localtime(mtime)), stage=stage,
        src=src, src_exists=bool(src) and os.path.exists(src), turn=prep.get("turn", 0.0), tilt=prep.get("tilt", 0.0),
        prep_version=prep.get("prep_version"), shells=len(prep.get("shells", [])), colors=len(prep.get("names", [])),
        textured=len(prep.get("names", [])) > 1, parts=len(parts), kinds=dict(kinds),
        ops=len(plan.get("ops", [])), ops_text=ops_summary(plan.get("ops", [])),
        manual=sum(1 for o in plan.get("ops", []) if o.get("manual")), labels=len(labels), decor=len(decor),
        has_edit=os.path.exists(os.path.join(d, "parts_edit.blend")),
        has_parts=os.path.exists(os.path.join(d, "parts.blend")),
        fbx=fbx, fbx_when=time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(fbx))) if fbx else "",
        prompt=prompt, size_work=_du(d), size_out=sum(os.path.getsize(f) for f in outs),
        size_temp=sum(os.path.getsize(f) for f in temp), n_temp=len(temp),
        score=score.get("score"), grade=score.get("grade", ""), score_draft=bool(score.get("draft")),
        draft=os.path.join(d, "draft", draft[0]) if draft else "", good=good)


def scan():
    """Moi model trong work/, moi nhat truoc."""
    if not os.path.isdir(WORK):
        return []
    rows = []
    for n in os.listdir(WORK):
        if os.path.isdir(os.path.join(WORK, n)):
            try:
                rows.append(info(n))
            except (OSError, ValueError):
                continue
    return sorted(rows, key=lambda r: -r["mtime"])


def clean(name):
    """Xoa file tam cua model -> so byte giai phong."""
    n = 0
    for p in temp_files(name):
        try:
            s = os.path.getsize(p)
            os.remove(p)
            n += s
        except OSError:
            pass
    return n


def delete(name, with_out=False):
    """Xoa work/<Ten> (+ out/<Ten>.* neu with_out) -> so byte giai phong. Khong dung file goc (Downloads / inbox)."""
    d = work_dir(name)
    n = _du(d) if os.path.isdir(d) else 0
    if os.path.isdir(d):
        shutil.rmtree(d)
    if with_out:
        for f in out_files(name):
            try:
                n += os.path.getsize(f)
                os.remove(f)
            except OSError:
                pass
    return n


if __name__ == "__main__":                  # python woolcut/wc/library.py : bang tom tat
    tot = 0
    for r in scan():
        tot += r["size_work"] + r["size_out"]
        print("%-34s %-13s %3d manh  %5.0f MB (tam %4.0f MB)  %s  %s" % (
            r["name"], r["stage"], r["parts"], (r["size_work"] + r["size_out"]) / 2 ** 20, r["size_temp"] / 2 ** 20,
            r["when"], r["ops_text"]))
    print("TONG %.0f MB" % (tot / 2 ** 20))
