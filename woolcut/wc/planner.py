"""Buoc 3b - CLAUDE LAP KE HOACH CAT (chay bang python he thong, goi Claude CLI).

Claude doc anh luoi toa do (prep) -> viet plan.json. Sau khi cat, Claude doc bang manh + canh bao ->
sua ke hoach (vong soat). Claude chi duoc Read anh trong thu muc work, khong sua file, khong chay lenh."""
import os, re, sys, json, shutil, subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(HERE, "data", "ref")

RULES = r"""
# Muc tieu
Tach model AI (Tripo, mot khoi lien nhieu mau) thanh cac MANH de to len trong game Wooler, giong cach hoa si
chia model goc (xem anh mau gau BearArt: data/ref/bearart_*.png va con muc nguoi dung tu tach squid_user_split.png):
- moi bo phan mot khoi kin, MOT mau: dau, tai, mom/mat, mu, vanh mu, tay, chan, duoi, than, do vat, de...
- khoi to (dau, than) chia tiep 2-4 MUI bang mat phang qua tam (dau gau BearArt = 8 mui: trai/phai x
  truoc/sau x tren/duoi; than = 4 mui). De tron chia 4 cung (sectors).
- duong noi giua hai manh la MAT PHANG; manh khong vun, khong lat mong vo nghia.
- TRUOC khi ban lap ke hoach, tool da TU tach: (a) cac U NHO RA tren khoi lon (mat, mui, nut, tai, duoi, tay ngan)
  thanh khoi rieng - cat o chan u; (b) chi tiet / mang mau phang tuong phan (mat ve, long tai, quang mat gau
  truc) thanh mieng dan. Xem bang "khoi roi": tai / mat / duoi da la khoi rieng thi KHONG cat lai. Chi cat nhung
  bo phan con DINH vao khoi lon (tay dai, chan, mu, co...).
- U NHO RA THAP (mom quanh mui, ma, bung tron nho, mieng) tool KHONG tu bat duoc: tu cat bang "cut" mat phang
  song song be mat ngay sau u (normal huong ra ngoai, snap 0.2) TRUOC khi chia mui. Duong chia mui (split /
  sectors) KHONG duoc di qua mat, mui, mom, duoi, nut - neu se di qua thi tach chi tiet do ra truoc.
- KHONG nhat thiet manh nao cung phai cat: bo phan rieng nho (tay, chan, ong xa, dua, thia, nut, banh nho...) GIU
  NGUYEN mot manh. Chi chia mui KHOI TO (dau, than, de, banh xe lon, than xe) - tool bo qua lenh chia khoi < 3%
  the tich model. So manh S/M [min, max] chi la tham khao; tool khong ep cat / gop de dat so.

# He toa do
Model da chuan hoa: canh dai nhat = 10, tam X/Y = 0, day Z = 0. MAT TRUOC nhin ve -Y.
Anh plan_front: ngang = X, doc = Z. plan_right (nhin tu +X): ngang = Y (truoc o ben TRAI), doc = Z.
plan_back: ngang = X nguoc. plan_left: ngang = Y nguoc. plan_top: ngang = X, doc = Y. So ghi toa do THAT.
Doc toa do moi diem tu IT NHAT HAI anh (vd x,z tu front; y,z tu right).

# Thao tac (JSON). Muc tieu chi bang DIEM trong toa do model.
{"op":"cut","label":"co","at":[x,y,z],"normal":[nx,ny,nz],"snap":0.4}
   Cat CUC BO: chi vong giao tuyen quanh `at` (co, goc tai, goc tay, chan cot). `at` phai nam TRONG vat lieu,
   o dung cho thắt. snap>0: tool tu dich +-snap va nghieng <=20 do toi tiet dien HEP NHAT (cat chuan o cho thắt).
   snap 0: cat dung mat phang ban chi (dung cho mu, tui, vat dinh tren mat cong).
   normal huong tu khoi chinh RA phan bi cat (vd tai trai: tu tam dau ra dinh tai).
{"op":"part","label":"mom","target":[x,y,z],"color":["Cream"]}
   Tach vung mau quanh target bang mat phang khop bien mau. CHI dung khi bien mau gan PHANG (mom, ban chan,
   chop duoi, giay). Mu/tui/yem nam tren mat cong -> dung "cut" voi mat phang tu chon. Sai mau > 25% tool bo qua.
{"op":"split","label":"dau 4 mui","target":[x,y,z],"axes":["x","y"]}     chia mui qua tam khoi (x: trai/phai,
   y: truoc/sau, z: tren/duoi). "normals":[[..]] neu can nghieng.
{"op":"sectors","label":"de","target":[x,y,z],"n":4,"start":45}       MUI CAM quanh truc qua tam: n bat ky (3, 4, 5,
   6, 8...); "axis":"x"/"y" cho khoi nam ngang (trong nam, ong); "layers": 3 = mui cam x tang (Totoro 4 mui x 3 tang).
{"op":"slices","label":"duoi","target":[x,y,z],"axis":"y","n":2}       lat song song deu; "at":[0.3,0.7] vi tri tuy y.
{"op":"grid","label":"than xe","target":[x,y,z],"grid":[3,2,2]}         luoi o vuong theo 3 truc (than xe bus 3x2x2).
Khoi DAI NAM NGHIENG (ong kinh, chan may, tay gio cheo, can cau) tool tu xoay he truc theo truc khoi: "axis":"z"
   / "x" cua ong nghieng = truc ong -> lat cat vuong goc ong, mui cam quanh ong. Muon ro rang: "axis":"long" (truc
   dai cua khoi), "mid", "short". KIEM diem target nam TRONG dung bo phan muon chia (doc toa do it nhat 2 anh) -
   target lech sang khoi ben canh la cat nham ca bo phan khac.
Chon kieu chia theo HINH khoi: cau / dau tron -> split x,y(,z) hoac sectors; khoi dai (than xe, ghe dai) -> grid /
slices doc chieu dai; khoi tru dung (trong, coc, de tron) -> sectors (+ layers); khoi tru nam -> sectors axis ngang.
{"op":"merge","targets":[[x,y,z],[x,y,z]]}   {"op":"drop","target":[x,y,z]}
{"op":"color","target":[x,y,z],"color":"Orange"}   {"op":"kind","target":[x,y,z],"kind":"S|M|D"}
{"op":"decal","target":[x,y,z],"color":"Black"}   (ep mot vung mau thanh D neu tool khong tu tach)

# Thu tu nen theo (rut tu lan thu con cao dua thu)
1. Tach DO VAT / phu kien dinh vao de hay than truoc (hom thu: cat chan cot; cot / than hop).
2. Phan nho ra: tai, tay, chan, duoi, vanh mu, tui (cat o goc). Cat phu kien dinh tren duoi/than (tui) TRUOC
   khi cat duoi, vi quai tui noi cac khoi thanh vong -> cat duoi truoc se khong tach roi.
3. Mu: cat bang mat phang o BANG MU (snap 0), sau khi da tach tai (khong thi mat phang cat ca dinh tai).
4. Co (dau / than), roi mom/mat (part neu bien mau phang).
5. Cuoi cung chia mui khoi to: dau, than (split), de (sectors). Khong chia khoi nho (< 1/5 model).
Mot vung cung mau phu ca bo phan (canh tay kem) thi KHONG can part.

# Tra loi
CHI mot khoi JSON: {"name": "...", "notes": "1-2 cau", "ops": [...]} - khong giai thich them ngoai JSON.
"""


NOCOLOR = """
!! MODEL KHONG CO MAU (khong texture): anh plan_* to MOI KHOI ROI mot mau pastel ngau nhien chi de nhin - do KHONG
phai mau that. Khong dung "part" / "decal" / "color". Tach thuan theo hinh: cut o cho thắt, split / sectors khoi to.
Cac khoi roi (tripo_part) thuong da la bo phan - kiem tra tung khoi xem co can cat nua khong."""


PROMPT_NOTE = """
# Prompt da dung de tao model (Y DO cua nguoi lam - anh moi la SU THAT)
"%s"
- Liet ke cac bo phan prompt goi ten (mom, mang bung, ma, dem chan, vanh mu, quai, banh xe, nut...) va tim tung
  cai tren anh. Bo phan nao CO tren anh (u noi, ranh, doi mau) thi PHAI thanh manh rieng - tach truoc khi chia mui.
- Tripo hay gop hoac bo bot chi tiet: bo phan prompt co ma anh khong thay (dap chim, khong ranh, khong doi mau)
  thi KHONG bia nhat cat; ghi ten bo phan thieu vao "notes".
- Mau trong prompt la mau Y DO cua tung bo phan (quan trong khi model khong co mau).
- DECOR prompt ke (cham, sao, tim, hoa nho, nut, dinh tan, ma hong, dem chan, soi tren de...) la manh D: tool tu
  tach theo mau / u noi TRUOC moi nhat cat, khong ton nhat cat cho tung cai. Anh thay decor ma tool chua tach
  (con dinh vao mieng lon) thi them {"op":"decal"} cho no; dung bien mot nhom decor thanh S/M."""


def model_prompt(name):
    """Prompt cua model dang tach (work/<Ten>/prompt.txt > tripo.json canh file goc), rong neu khong co."""
    from . import prompt as pr
    work = os.path.join(HERE, "work", name)
    src = ""
    try:
        src = json.load(open(os.path.join(work, "prep.json"), encoding="utf-8")).get("src", "")
    except (OSError, ValueError):
        pass
    return pr.find_prompt(src, name, work)


def prompt_note(name, tag):
    mp = model_prompt(name)
    print("[%s] %s" % (tag, ("doc prompt cua model: %s..." % mp[:90]) if mp else "khong co prompt cua model - chi nhin anh"))
    return (PROMPT_NOTE % mp.replace('"', "'")) if mp else ""


def claude_exe():
    exe = shutil.which("claude") or os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
    if not os.path.exists(exe) and not shutil.which("claude"):
        raise SystemExit("Khong tim thay claude CLI")
    return exe


# Toc do Claude CLI (2026-10-02: lap ke hoach mac dinh mat ~13 phut). WOOLCUT_SPEED=fast|normal|careful (panel)
SPEED = {
    "fast":    {"plan": ("sonnet", "low"), "paint": ("sonnet", "low"), "pick": ("sonnet", "low")},
    "normal":  {"plan": (None, "medium"), "paint": ("sonnet", "low"), "pick": ("sonnet", "medium")},
    "careful": {"plan": (None, "high"), "paint": (None, "medium"), "pick": (None, "medium")},
}


# Tung chuc nang goi Claude (khoa, ten o panel, nhom SPEED mac dinh). Nguoi dung 2026-10-07: "them setting de chinh model
# cho cac chuc nang" -> panel / Preferences ghi WOOLCUT_MODELS = {khoa: [model, effort]}; trong = theo che do chung.
TASKS = [                                   # ten ngan: cot panel hep (ten dai bi cat, 2026-10-07)
    ("prompt", "Viết prompt", "paint"),
    ("facing", "Tìm mặt trước", "plan"),
    ("label", "Đặt tên", "paint"),
    ("paint", "Tô màu", "paint"),
    ("decor", "Gắn decor", "paint"),
    ("refine", "Tách sâu", "plan"),
    ("piece", "Chia mảnh chọn", "pick"),
    ("plan", "Kế hoạch (cũ)", "plan"),
    ("review", "Soát (cũ)", "plan"),
]
# Goi y (2026-10-07): Sonnet/low dat ten sai ~30/73 manh (gau xe may 2), to mau ra cau vong (chim) -> Opus; viet prompt
# giu Sonnet (nhanh, nguoi dung duyet lai). Cac chuc nang khac: theo che do chung (da la Opus).
RECOMMENDED = {"prompt": ("sonnet", "low"), "label": ("opus", "medium"), "paint": ("opus", "medium"),
               "decor": ("opus", "medium"), "piece": ("opus", "medium")}


def model_for(kind, task="plan"):
    """(model, effort) cho mot chuc nang: WOOLCUT_MODELS (JSON {kind: [model, effort]}, panel ghi; "" = theo che do,
    "default" = model mac dinh cua Claude CLI) > che do chung WOOLCUT_SPEED (fast | normal | careful)."""
    model, effort = SPEED.get(os.environ.get("WOOLCUT_SPEED", "normal"), SPEED["normal"])[task]
    try:
        over = json.loads(os.environ.get("WOOLCUT_MODELS") or "{}").get(kind) or []
    except (ValueError, AttributeError):
        over = []
    if len(over) > 0 and over[0]:
        model = None if over[0] == "default" else over[0]
    if len(over) > 1 and over[1]:
        effort = over[1]
    return model, effort


def run_claude(prompt, cwd, timeout=1800, task="plan", kind=None):
    exe = claude_exe()
    model, effort = model_for(kind or task, task)
    cmd = [exe, "-p", prompt, "--output-format", "text", "--allowedTools", "Read",
           "--disallowedTools", "Bash", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch", "NotebookEdit",
           "--add-dir", REF]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    print("[claude] %s: model %s, effort %s" % (kind or task, model or "mac dinh", effort))
    env = dict(os.environ, WOOLCUT_NO_TRIPO="1", PRIMFORGE_NO_TRIPO="1")
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=env)
    return p.returncode, p.stdout, p.stderr


def extract_json(text):
    """Khoi JSON ngoai cung dau tien chua "ops"."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cands = [m.group(1)] if m else []
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                cands.append(text[start:i + 1])
    for c in cands:
        try:
            d = json.loads(c)
            if isinstance(d, dict) and "ops" in d:
                return d
        except ValueError:
            continue
    return None


def plan(name, nmin=15, nmax=35, idea=""):
    work = os.path.join(HERE, "work", name)
    meta = json.load(open(os.path.join(work, "prep.json"), encoding="utf-8"))
    shells = "\n".join("  khoi %d: %d mat, mau chinh %s, hop %s .. %s" % (
        s["id"], s["faces"], (s["color"] or "?").replace("Color_", "").replace("_mat", ""), s["lo"], s["hi"])
        for s in meta["shells"])
    colors = ", ".join(n.replace("Color_", "").replace("_mat", "").split("_", 1)[-1] for n in meta["names"])
    prompt = RULES + """
# Model can tach: %s %s
Anh (doc bang Read, trong thu muc hien tai): plan_front.png, plan_right.png, plan_back.png, plan_left.png,
plan_top.png (co luoi toa do), plan_iso.png. Anh mau: %s (bearart_ids_iso.png = moi manh mot mau,
bearart_game.png = trong game, squid_user_split.png = nguoi dung tu tach).
Cac khoi roi Tripo da tach san (moi khoi roi da la mot manh):
%s
Mau co trong model (dung dung ten nay cho "color"): %s%s
So manh S/M muc tieu: %d..%d.%s
Doc ky anh truoc, roi viet ke hoach.""" % (name, ("(y tuong: %s)" % idea) if idea else "", REF, shells, colors,
                                          NOCOLOR if len(meta["names"]) <= 1 else "", nmin, nmax,
                                          prompt_note(name, "plan"))
    rc, out, err = run_claude(prompt, work, kind="plan")
    d = extract_json(out)
    if d is None:
        raise SystemExit("Claude khong tra ve ke hoach JSON:\n%s\n%s" % (out[-3000:], err[-2000:]))
    d.setdefault("name", name)
    d["min"], d["max"] = nmin, nmax
    path = os.path.join(work, "plan.json")
    if os.path.exists(path):
        shutil.copy(path, os.path.join(work, "plan_prev.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)
    print("[plan] Claude: %s" % d.get("notes", ""))
    print("[plan] %d thao tac -> %s" % (len(d["ops"]), path))
    return path


FACING = """# Viec: tim MAT TRUOC cua model 3D
Doc anh facing.png (Read, thu muc hien tai): 6 o = CUNG mot model, camera dung yen. A, B, C, D = xoay 4 goc quanh truc
dung. E = model LAT cho DINH (phia tren) quay ra truoc; F = LAT cho DAY quay ra truoc - chi chon E / F khi model dang
NAM (nhan vat nam ngua / up, mat nhin len troi hoac xuong dat; xe lat nghieng) va o do moi thay mat truoc DUNG THANG.
Chon o model QUAY MAT VE NGUOI XEM va DUNG THANG (dau o tren, chan / banh / de o duoi):
- nhan vat / con vat: thay mat CHINH DIEN (hai mat, mom/mui o giua) - khong phai mat nghieng, khong phai lung/duoi;
- do vat: mat truoc (may: man hinh / nut bam; tui: mat co khoa / hoa tiet);
- XE (xe may, o to, tau, xe dap...): chon o nhin thay DAU XE CHINH DIEN - den pha tron o giua, ghi dong / kinh chan gio
  doi xung, xe HEP (thay mot banh truoc chinh dien). KHONG chon o nhin NGANG thay ca hai banh (do la suon xe), khong
  chon o thay yen / den hau (duoi xe). Xe may do choi 2026-10-05 tung bi chon nham o nhin ngang;
- canh nho: goc nhin chinh, vat chinh khong bi che, cua / bang hieu huong ra ngoai.
%s
Truoc khi chon, MO TA ngan tung o (thay mat / suon / lung, rong hay hep) roi moi chon.
Tra ve CHI mot khoi JSON: {"views": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "...", "F": "..."}, "pick": "A",
"why": "1 cau tieng Viet co dau"}"""


def facing(name, src=""):
    """Claude chon o A-D trong work/<Ten>/facing.png -> goc xoay (do). None neu khong chon duoc."""
    from . import prompt as pr
    work = os.path.join(HERE, "work", name)
    mp = pr.find_prompt(src, name, work)
    note = ('Prompt da tao model (de biet mat truoc la gi): "%s"' % mp.replace('"', "'")[:700]) if mp else ""
    rc, out, err = run_claude(FACING % note, work, timeout=600, task="plan", kind="facing")   # sonnet/low chon nham o nhin ngang
    d = {}
    dec = json.JSONDecoder()
    for i, ch in enumerate(out):                         # JSON long nhau ("views": {...}) -> raw_decode tung '{'
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(out[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and "pick" in obj:
            d = obj
            break
    turns = {"A": (0, 0), "B": (90, 0), "C": (180, 0), "D": (-90, 0), "E": (0, 90), "F": (0, -90)}
    pick = str(d.get("pick", "")).strip().upper()[:1]
    if pick not in turns:
        print("[mat truoc] Claude khong chon duoc: %s" % (out[-500:] or err[-500:]))
        return None
    print("[mat truoc] Claude chon %s: %s" % (pick, d.get("why", "")))
    return turns[pick]                               # (xoay quanh Z, lat quanh X)


LABEL_RULES = """# Viec: DAT TEN tung bo phan cua model 3D (model da tach san theo part)
Doc anh (Read, thu muc hien tai): parts_ids_all.png (8 goc, moi manh mot mau), parts_sheet.png (tung manh rieng co ten
P01...), plan_front.png (anh luoi toa do). Danh sach manh kem tam (x,y,z; mat truoc nhin -Y, trai nguoi xem = -X).
Dat ten TIENG VIET CO DAU, 1-3 tu, theo y nghia bo phan: "đầu", "thân", "tai trái", "tay phải", "mõm", "bánh trước",
"ống xả trái", "yên", "đế", "quyển sách", "bút chì"... Phan biet trai/phai theo toa do X (X < 0 = trai).
Manh D (trang tri nho) dat ten ngan: "mắt", "nút", "ốc", "chấm", "sao"...
Tra ve CHI mot khoi JSON: {"labels": {"P01": "đầu", "P02": "thân", ...}} - dua TAT CA manh."""


def label(name):
    """Claude dat ten bo phan -> work/<Ten>/labels.json [{name, anchor, label}] (addon doi ten object theo diem neo)."""
    work = os.path.join(HERE, "work", name)
    res = json.load(open(os.path.join(work, "parts.json"), encoding="utf-8"))
    rows = "\n".join("  %s %s co=%.2f tam=%s" % (r["name"], r["kind"], r["size"], r.get("center")) for r in res["parts"])
    prompt = LABEL_RULES + "\n# Model %s\nCac manh:\n%s%s" % (name, rows, prompt_note(name, "dat ten"))
    rc, out, err = run_claude(prompt, work, task="paint", kind="label")
    d = None
    for m in re.finditer(r"\{.*\}", out, re.S):
        try:
            d = json.loads(m.group(0))
            break
        except ValueError:
            continue
    if not d or not isinstance(d.get("labels"), dict):
        print("[dat ten] Claude khong tra ve ten: %s" % (out[-500:] or err[-500:]))
        return 0
    by = {r["name"]: r for r in res["parts"]}
    rows = [{"name": k, "anchor": by[k].get("anchor") or by[k].get("center"), "label": str(v).strip()[:40]}
            for k, v in d["labels"].items() if k in by and str(v).strip()]
    with open(os.path.join(work, "labels.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    print("[dat ten] %d bo phan -> labels.json" % len(rows))
    return len(rows)


DECOR_RULES = """# Viec: GAN DECOR (mieng trang tri nho, manh D) len model len dan da tach manh - nhu model mau cua nguoi dung:
mat hat den + cham sang, ma hong, mui, mieng; sao / tim / hoa / not nhac / nut ao rai tren ao, tui, than do vat; hoa, sao,
qua nho rai tren mat de. Decor lam model sinh dong, KHONG che mat bo phan chinh.
Doc anh (Read): decor_front.png, decor_right.png, decor_left.png, decor_back.png, decor_top.png (luoi toa do THAT, moi
manh mot mau), decor_iso.png; %s (bang decor duoc phep dung, ten o duoi tung o).
He toa do: canh dai nhat model ~10, mat truoc nhin -Y, trai nguoi xem = -X, Z len tren.
Luat:
- CHI dung decor trong danh sach duoc phep. KHONG can dung het - chi chon cai HOP voi model va chu de (do an -> qua, banh;
  am nhac -> not nhac; bien -> sao...). Moi model thuong 6-24 decor.
- Nhan vat / con vat co mat: neu CHUA co mat (khong co manh D nho mau den o mat truoc dau) thi gan mat (eye_round /
  eye_oval) DOI XUNG qua X, + eye_shine nho (~1/3 mat) o goc tren mat; them ma hong (blush) duoi mat, mui o giua neu
  hop. Mat cach nhau ~ 1/3 be ngang dau. Da co mat thi KHONG gan lai.
- Co (size) = canh dai nhat cua decor theo don vi model: mat 0.35-0.7 (theo co dau), cham sang 0.12-0.2, ma 0.4-0.7,
  sao / tim / hoa rai 0.3-0.8, decor lon (meo, kem, banh) 0.6-1.2. Khong to hon 1/4 manh chu.
- "host" = TEN manh chu (dung y ten trong danh sach), khong gan len manh D khac. "at" = diem [x, y, z] gan be mat noi
  muon dat (doc tu it nhat 2 anh), "view" = huong nhin thay ro diem do: front (tu -Y), back, left (tu -X), right (tu +X),
  top. Tool ban tia theo huong do vao manh chu de dinh vi chinh xac.
- "rot" = xoay quanh phap tuyen (do) cho tu nhien (sao / tim nghieng -20..20), "color" chi cho decor doi mau (ten mau
  bang: Black, White, Pink, Red, Yellow, Orange, Blue, Sky, Green, Purple, Brown, Cream...), tuong phan voi manh chu.
- Rai decor deu, khong chong len nhau, cach nhau >= co decor. Doi xung khi hop ly.
- THIEU decor DON GIAN can thiet (no, la cay, giot nuoc, tia chop, banh xe nho, kinh, rang tho...)? Duoc TAO MOI toi da 3
  cai trong "new_decor" bang cach ghep khoi co ban, roi dung id do trong "decor". Toa do decor: ~1 don vi, MAT TRUOC
  nhin -Y (mat sau +Y ap vao be mat), dau +Z, decor nen DET (be day y ~0.2-0.4). Khoi: sphere / box (bo tron) / cylinder
  (truc Z) / cone (dinh +Z) / torus (vong trong mat phang XZ, size y = do day ong) / star ("points", "inner") / arc
  (cung trong mat XZ, "from", "to" do, "tube"). Moi khoi: "size" [x,y,z] (duong kinh), "at" [x,y,z], "rot" [do x,y,z].
  Chi tao khi thuc su can va decor co san khong thay duoc.
Tra ve CHI mot khoi JSON:
{"notes": "1 cau", "new_decor": [{"id": "ai_bow", "vi": "nơ", "en": "ribbon bow", "group": "misc", "color": "Pink",
 "parts": [{"shape": "sphere", "size": [0.5, 0.3, 0.4], "at": [-0.28, 0, 0], "rot": [0, 0, 15]},
           {"shape": "sphere", "size": [0.5, 0.3, 0.4], "at": [0.28, 0, 0], "rot": [0, 0, -15]},
           {"shape": "sphere", "size": [0.2, 0.32, 0.2], "at": [0, 0, 0]}]}],
 "decor": [{"decor": "eye_round", "host": "P05 đầu", "at": [x, y, z], "view": "front", "size": 0.5, "rot": 0,
 "color": "Black"}, ...]}"""


def decor(name, allowed=None):
    """Claude chon + dat decor -> work/<Ten>/decor_plan.json. allowed = danh sach id decor duoc tick (None = tat ca)."""
    sys.path.insert(0, HERE)
    from wc import decor as dmod, std
    work = os.path.join(HERE, "work", name)
    cat = dmod.catalog()
    if allowed:
        cat = [c for c in cat if c["id"] in set(allowed)]
    if not cat:
        raise SystemExit("khong co decor nao duoc chon")
    parts = json.load(open(os.path.join(work, "decor_parts.json"), encoding="utf-8"))
    rows = "\n".join("  %-26s %s mau=%s hop=%s..%s%s" % (
        p["name"], p["kind"], (p["color"] or "").replace("Color_", "").replace("_mat", ""), p["lo"], p["hi"],
        (" (decor %s)" % p["decor"]) if p.get("decor") else "") for p in parts)
    prompt = (DECOR_RULES % dmod.SHEET) + "\n# Model %s\nCac manh (ten, loai, mau, hop bao):\n%s\n# Decor duoc phep (%d):\n%s%s" % (
        name, rows, len(cat), dmod.catalog_text(cat), prompt_note(name, "decor"))
    rc, out, err = run_claude(prompt, work, task="paint", kind="decor")
    d = None
    for m in re.finditer(r"\{.*\}", out, re.S):
        try:
            d = json.loads(m.group(0))
            break
        except ValueError:
            continue
    if not d or not isinstance(d.get("decor"), list):
        raise SystemExit("Claude khong tra ve decor: %s" % (out[-800:] or err[-800:]))
    ok_ids = {c["id"] for c in cat}
    names = {p["name"] for p in parts}
    # decor MOI Claude tao (nguoi dung 2026-10-05: "can decor moi don gian thi tao va thong bao")
    made = []
    full = dmod.catalog()
    have = {c["id"] for c in full}
    for nd in (d.get("new_decor") or [])[:3]:
        did = re.sub(r"[^a-z0-9_]", "", str(nd.get("id", "")).lower())
        if not did:
            continue
        if not did.startswith("ai_"):
            did = "ai_" + did
        err = dmod.valid_spec(nd)
        if err:
            print("[decor] bo decor moi %s: %s" % (did, err))
            continue
        try:
            col = std.resolve_color(nd.get("color") or "White")
            col_name = col.replace("Color_", "").replace("_mat", "").split("_", 1)[-1]
        except Exception:
            col_name = "White"
        entry = dict(id=did, vi=str(nd.get("vi") or did)[:30], en=str(nd.get("en") or "")[:80],
                     group=str(nd.get("group") or "misc"), mode="tint", color=col_name, dims=[1, 0.3, 1],
                     src="claude " + name, spec={"parts": nd["parts"]})
        full = [c for c in full if c["id"] != did] + [entry]
        if nd.get("id") != did:
            for x in d["decor"]:
                if x.get("decor") == nd.get("id"):
                    x["decor"] = did
        ok_ids.add(did)
        made.append(entry)
    if made:
        with open(dmod.CATALOG, "w", encoding="utf-8") as fh:
            json.dump(full, fh, ensure_ascii=False, indent=1)
    keep = [x for x in d["decor"] if x.get("decor") in ok_ids and x.get("host") in names and len(x.get("at", [])) == 3]
    with open(os.path.join(work, "decor_plan.json"), "w", encoding="utf-8") as fh:
        json.dump({"notes": d.get("notes", ""), "decor": keep, "new": [[m["id"], m["vi"]] for m in made]},
                  fh, ensure_ascii=False, indent=1)
    for m in made:
        print("[decor] Claude TAO decor moi: %s (%s) - %s" % (m["vi"], m["id"], m["en"]))
    print("[decor] Claude: %s" % d.get("notes", ""))
    print("[decor] %d/%d decor hop le -> decor_plan.json" % (len(keep), len(d["decor"])))
    return len(keep)


PIECE_RULES = """# Viec: CHIA MOT BO PHAN LON cua model len dan thanh cac BO PHAN CON co y nghia (nguoi dung quan len tung manh)
Doc anh (Read): piece_front.png, piece_right.png, piece_back.png, piece_left.png, piece_top.png (luoi toa do THAT,
chi hien bo phan nay), piece_iso.png, va context_iso.png (ca model, bo phan nay to DO de biet no nam o dau).
He toa do: mat truoc model nhin -Y, trai nguoi xem = -X, Z len tren.
- Tim cac khoi con nhan ra duoc trong bo phan nay (vd than xe: yen, tua lung, chan bun truoc / sau, op den, san de chan,
  than sau, hop duoi; nhan vat: dau / than / tay...). Cat o RANH, CHO THAT, hoac noi be mat doi huong ro giua chung.
- 2-6 manh, moi manh >= 8% bo phan, hinh gon; KHONG cat vun, khong cat ngang qua giua mot khoi tron.
- Thao tac (toa do THAT, doc tu it nhat 2 anh):
  {"op":"cut","label":"yen","at":[x,y,z],"normal":[nx,ny,nz],"snap":0.3}  cat CUC BO quanh "at": "at" nam TRONG vat lieu
     tai cho that / ranh; "normal" huong tu phan con lai RA phan bi cat; snap > 0 cho tool do cho hep nhat quanh do.
  {"op":"slices","label":"...","target":[x,y,z],"axis":"y","n":2}  lat deu (khoi dai don dieu)
  {"op":"split","label":"...","target":[x,y,z],"axes":["x"]}  chia doi qua tam
  {"op":"carve","label":"vanh mu","target":[x,y,z],"shape":"ring","center":[x,y,z],"axis":[0,0,1],"radius":R,
   "inner_radius":r,"height":h}  KHOET: manh moi = phan bo phan nam TRONG khoi bao; dung khi bo phan con XUYEN QUA / ON
   quanh khoi khac nen mat phang nao cung cat nham (vanh mu quanh dau: ring ngoai = mep vanh, trong = sat be mat dau,
   cao = do day vanh; ca chiec mu tren dau: cylinder / sphere bao phan mu ben tren; mang bung: sphere dep; tui: box).
   shape: ring (radius, inner_radius, height, axis), cylinder (radius, height, axis), box (size [x,y,z], rot [do]),
   sphere (size [x,y,z] = duong kinh). "target" = diem nam trong bo phan dang chia.
  VANH MU, CO AO, VONG / DAI quanh mot khoi khac: BAT BUOC dung carve "ring" (inner_radius = sat be mat khoi ben
  trong, height = do day vanh, axis = phap tuyen mat vanh). Mat phang cat se lay ca chom dau / than (2026-10-05 meo phu
  thuy: cat phang lay vanh mu kem chom dau).
  Thu tu: cat khoi nho / nho ra truoc (yen, op den...), cuoi cung moi chia khoi con lai.
Tra ve CHI mot khoi JSON: {"notes": "1 cau tieng Viet co dau: chia thanh nhung gi", "ops": [...]}"""


def piece_plan(name, label="", hint=""):
    """Claude lap ke hoach chia MOT manh -> work/<Ten>/piece_plan.json. hint = yeu cau cua nguoi dung (o panel)."""
    work = os.path.join(HERE, "work", name)
    req = ("\n# YEU CAU CUA NGUOI DUNG (lam DUNG theo): %s" % hint) if hint.strip() else ""
    prompt = PIECE_RULES + "\n# Model %s - bo phan: %s%s%s" % (name, label or "?", req, prompt_note(name, "chia manh"))
    rc, out, err = run_claude(prompt, work, kind="piece")
    d = None
    dec = json.JSONDecoder()
    for i, ch in enumerate(out):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(out[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("ops"), list):
            d = obj
            break
    if d is None:
        raise SystemExit("Claude khong tra ve ke hoach: %s" % (out[-800:] or err[-800:]))
    ok = [o for o in d["ops"] if o.get("op") in ("cut", "slices", "split", "sectors", "grid", "carve")]
    with open(os.path.join(work, "piece_plan.json"), "w", encoding="utf-8") as fh:
        json.dump({"notes": d.get("notes", ""), "ops": ok}, fh, ensure_ascii=False, indent=1)
    print("[chia manh] Claude: %s (%d nhat)" % (d.get("notes", ""), len(ok)))
    return len(ok)


REFINE_RULES = """# Viec: XEM KY MOT BO PHAN cua model len dan, quyet dinh co TACH TIEP thanh bo phan con khong
(nguoi dung 2026-10-06: tach ra cac bo phan co y nghia roi thi xem tiep TUNG bo phan; cho nao co NEP GAP ma phan do co
y nghia rieng thi tach ra thanh part rieng). Model len dan: moi manh mot mau, nguoi choi go tung manh.
Doc anh (Read, thu muc hien tai):
- context.png: ca model, bo phan nay to DO - de biet no la gi, nam o dau.
- piece_front.png, piece_right.png, piece_back.png, piece_left.png, piece_top.png (luoi toa do THAT), piece_iso.png:
  rieng bo phan nay, nhin du cac phia.
- cands.png: 2 o dau = ban do NEP GAP (vet do = nep lom, ranh). Cac o #k = UNG VIEN tool da cat thu THAT theo nep:
  phan to DO la phan se roi ra neu chon #k, phan xam giu lai. Nhat cat di dung tren nep / ranh nen dep va chinh xac hon
  moi nhat cat tu ve.
Quyet dinh:
1. Bo phan nay co gom nhieu bo phan con CO Y NGHIA RIENG khong? Nhan vat / con vat: dau, mu, tai, mom, mat, tay, ban tay,
   chan, giay, duoi, ao, quan, than. Xe: yen, than sau, san de chan, chan bun / op truoc, dau xe, den, ghi dong, gio.
   Do vat: nap, quai, de, than, nut, ngan keo, man hinh... Bo phan DON (banh xe, qua bong, con mat, cai nut, mot hop
   tron, mot ngon tay) -> {"split": false}.
2. Neu co: CHON ung vien #k ma phan DO = TRON VEN mot bo phan con (ca cai tai, ca canh tay, ca cai dau / mu, ca cai yen,
   ca ong quan). KHONG chon o lat xien qua giua mot khoi, o chi lay mot nua / mot mieng mong, o lay hai bo phan khac
   nhau dinh lien (vd tay + mot mieng bung). Doi xung (tai / tay / chan trai - phai) -> chon ca hai. Hai o gan giong
   nhau -> chon o sach hon. Chon LONG NHAU duoc (ca cai dau VA hai cai tai tren dau: tool cat phan nho truoc). Hai o
   CHONG LAN mot phan (vd hai nua mom, moi o lay mot nua + phan giua) -> chi chon mot (tool bo o sau).
3. Tach vua du: bo phan con nen >= ~1% bo phan; ca model can 17-39 manh len (manh lon / nho xen ke), khong bam vun.
4. Bo phan con CAN tach ma KHONG co ung vien -> them vao "ops" (toa do THAT doc tu anh luoi, doi chieu it nhat 2 anh):
   {"op":"crease","label":"tay phải","part":[[x,y,z],[x,y,z]],"rest":[[x,y,z],[x,y,z]]}  CAT THEO NEP giua hai nhom
     diem: "part" 2-3 diem TREN BE MAT bo phan con (mot o dau mut, mot gan goc), "rest" 2-3 diem tren phan con lai (mot
     sat cho noi, mot o xa). Tool tu tim duong nep giua hai nhom. Dung cho tay ap sat than, ao / quan, mang bung...
   {"op":"carve","label":"vành mũ","target":[x,y,z],"shape":"ring","center":[x,y,z],"axis":[0,0,1],"radius":R,
    "inner_radius":r,"height":h}  KHOET: vanh mu, co ao, vong / dai quanh mot khoi khac (shape: ring, cylinder, box
    [size, rot], sphere [size]).
   {"op":"cut","label":"...","at":[x,y,z],"normal":[nx,ny,nz],"snap":0.3}  cat phang cuc bo - chi khi cho noi that su
    phang (mat tiep giap hai khoi hop).
5. Dat ten TIENG VIET CO DAU, 1-3 tu, cho moi phan tach ra ("label") va "rest" = ten phan con lai sau khi tach.
   Trai / phai THEO NGUOI XEM nhu buoc dat ten: X < 0 = "trái", X > 0 = "phải" (mat truoc model nhin -Y).
Tra ve CHI mot khoi JSON:
{"split": true, "pick": [{"cand": 3, "label": "tai trái"}, {"cand": 4, "label": "tai phải"}], "ops": [], "rest": "đầu",
 "notes": "1 cau tieng Viet co dau: tach gi, vi sao"}"""


def _first_json(out, keys):
    dec = json.JSONDecoder()
    for i, ch in enumerate(out):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(out[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and any(k in obj for k in keys):
            return obj
    return None


def refine_piece(name, info, hint="", force=False):
    """Claude xem MOT manh (anh trong refine/<manh>/) -> {"ops": [...], "labels": [{tip, label}], "rest", "notes"}."""
    folder = info["dir"]
    cands = json.load(open(os.path.join(folder, "cands.json"), encoding="utf-8"))
    rows = "\n".join("  #%d: phan do = %.1f%% bo phan" % (c["k"], 100 * c["frac"]) for c in cands) or "  (khong co)"
    req = ""
    if hint.strip():
        req = "\n# YEU CAU CUA NGUOI DUNG (lam DUNG theo): %s" % hint.strip()
    if force:
        req += "\n# Nguoi dung CHU DONG chon manh nay de chia -> phai tach (split true), tru khi that su khong the."
    prompt = REFINE_RULES + "\n# Model %s - bo phan dang xem: \"%s\" (%d mat, %.1f%% the tich ca model)\nUng vien:\n%s%s%s" % (
        name, info.get("label") or info["name"], info["faces"], 100 * info.get("model_frac", 0), rows, req,
        prompt_note(name, "tach sau"))
    # co yeu cau tu buoc xem ca model -> chi con chon o: muc "pick" (nhanh); tu quyet thi muc plan
    rc, out, err = run_claude(prompt, folder, timeout=900, task="pick" if hint.strip() else "plan",
                              kind="piece" if force else "refine")     # force = nut "Claude chia manh dang chon"
    d = _first_json(out, ("split", "pick", "ops"))
    if d is None:
        print("[tach sau] %s: Claude khong tra ve JSON: %s" % (info["name"], (out[-300:] or err[-300:]).strip()))
        return None
    with open(os.path.join(folder, "claude.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    by = {c["k"]: c for c in cands}
    ops, labels = [], []
    picks = [p for p in (d.get("pick") or []) if isinstance(p, dict) and int(p.get("cand", -1)) in by]
    picks.sort(key=lambda p: by[int(p["cand"])]["frac"])          # nho truoc: tai roi moi den dau
    if d.get("split") is not False:
        extra = []
        for o in d.get("ops") or []:
            if not isinstance(o, dict) or o.get("op") not in ("crease", "carve", "cut", "split", "slices"):
                continue
            if o["op"] == "crease" and not (o.get("part") and o.get("rest")):
                continue
            k = _snap_cand(o, cands) if o["op"] == "crease" else None
            if k is not None and all(int(p_["cand"]) != k for p_ in picks):
                # diem Claude tu chi rot gon trong mot ung vien -> dung nhat cat cua ung vien (theo nep, kiem truoc)
                print("[tach sau] %s: '%s' khop ung vien #%d" % (info["name"], o.get("label", ""), k))
                picks.append({"cand": k, "label": o.get("label", "")})
                continue
            extra.append(o)
        picks = _drop_overlaps(info["name"], picks, by)
        picks.sort(key=lambda p_: by[int(p_["cand"])]["frac"])
        for p in picks:
            c = by[int(p["cand"])]
            lab = str(p.get("label") or "").strip()[:40]
            ops.append(dict(c["op"], label=lab, anchor=c["anchor"], cand=c["k"]))
            labels.append({"pts": c.get("pts") or [c["tip"]], "tip": c["tip"], "label": lab,
                           "rest_pts": (c.get("op") or {}).get("rest") or []})
        for o in extra:
            lab = str(o.get("label") or "").strip()[:40]
            ops.append(o)
            tip = (o.get("part") or [None])[0] if o["op"] == "crease" else o.get("center") if o["op"] == "carve" \
                else None
            if o["op"] == "cut" and o.get("at") and o.get("normal"):
                import math
                nn = o["normal"]
                ln = math.sqrt(sum(float(x) ** 2 for x in nn)) or 1.0
                tip = [float(a) + 0.3 * float(b) / ln for a, b in zip(o["at"], nn)]
            if tip and lab:
                pts = o.get("part") if o["op"] == "crease" else [tip]
                labels.append({"pts": pts, "tip": tip, "label": lab,
                               "rest_pts": o.get("rest") if o["op"] == "crease" else []})
    res = {"name": info["name"], "split": bool(ops), "ops": ops, "labels": labels,
           "rest": str(d.get("rest") or "").strip()[:40], "notes": str(d.get("notes") or "")}
    print("[tach sau] %s: %s (%d nhat)" % (info["name"], res["notes"] or ("khong tach" if not ops else ""), len(ops)))
    return res


def _inside(qs, c):
    """Ti le diem qs nam trong phan tach cua ung vien c (diem mau gan nhat thuoc part_s hay rest_s)."""
    import numpy as np
    ps, rs = np.asarray(c.get("part_s") or [], float), np.asarray(c.get("rest_s") or [], float)
    if not len(qs) or not len(ps) or not len(rs):
        return 0.0
    Q = np.asarray(qs, float)
    dp = ((Q[:, None] - ps[None]) ** 2).sum(2).min(1)
    dr = ((Q[:, None] - rs[None]) ** 2).sum(2).min(1)
    return float((dp < dr).mean())


def _drop_overlaps(name, picks, by):
    """Bo o chon CHONG LAN MOT PHAN voi o da chon truoc (gau 2026-10-06: hai nua mom 'ma trai / ma phai' chong nhau ->
    nhat sau cat vao manh cua nhat truoc). Long nhau (tai trong dau) hoac roi nhau thi giu."""
    keep = []
    for p in picks:
        c = by[int(p["cand"])]
        bad = None
        for q in keep:
            d = by[int(q["cand"])]
            a, b = _inside(c.get("part_s") or [], d), _inside(d.get("part_s") or [], c)
            if max(a, b) < 0.85 and max(a, b) > 0.15:
                bad = q
                break
        if bad is not None:
            print("[tach sau] %s: bo #%s '%s' (chong lan #%s '%s')" % (name, p["cand"], p.get("label", ""),
                                                                    bad["cand"], bad.get("label", "")))
            continue
        keep.append(p)
    return keep


def _snap_cand(o, cands):
    """Ung vien NHO NHAT chua moi diem "part" va khong chua diem "rest" nao cua nhat cat Claude tu chi (gau 2026-10-06:
    Claude tu chi diem cho chan trai -> Laplace lay ca hai chan; ung vien #8 dung y). None neu khong co."""
    best = None
    for c in cands:
        ps, rs = c.get("part_s"), c.get("rest_s")
        if not ps or not rs:
            continue
        S = [(p, True) for p in ps] + [(p, False) for p in rs]

        def side(q):
            return min(S, key=lambda s_: sum((float(a) - float(b)) ** 2 for a, b in zip(s_[0], q)))[1]
        if all(side(q) for q in o["part"]) and not any(side(q) for q in o["rest"]):
            if best is None or c["frac"] < best[0]:
                best = (c["frac"], c["k"])
    return best[1] if best else None


def refine_all(name, hint="", force=False, workers=4, hints=None):
    """Claude xem SONG SONG moi manh trong refine/index.json -> refine/refine_plan.json. hints = {ten manh: {want, parts}}
    tu buoc xem ca model: manh do PHAI tach theo yeu cau (force)."""
    from concurrent.futures import ThreadPoolExecutor
    root = os.path.join(HERE, "work", name, "refine")
    index = json.load(open(os.path.join(root, "index.json"), encoding="utf-8"))
    print("[tach sau] Claude xem %d bo phan (song song %d)..." % (len(index), min(workers, len(index))))
    sys.stdout.flush()
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(index)))) as ex:
        def one(info):
            h = (hints or {}).get(info["name"])
            if h:
                want = h.get("want", "")
                if h.get("parts"):
                    want += " -> thanh: %s (phan cuoi = phan con lai, dat vao \"rest\")" % ", ".join(h["parts"])
                return refine_piece(name, info, want, True)
            return refine_piece(name, info, hint, force)
        res = list(ex.map(one, index))
    plan = {"pieces": [r for r in res if r]}
    path = os.path.join(root, "refine_plan.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=1)
    n = sum(len(r["ops"]) for r in plan["pieces"])
    print("[tach sau] %d / %d bo phan can tach, %d nhat -> refine_plan.json" % (
        sum(1 for r in plan["pieces"] if r["ops"]), len(index), n))
    return path


STRUCT_RULES = """# Viec: XEM CA MODEL len dan da tach manh, doi chieu voi cac BO PHAN can co -> de xuat TACH / GHEP / DOI TEN
(nguoi dung 2026-10-07: "phai tao hinh dung dau con gau, tach dau va than; tay nen tach tay va ban tay; sua de dung duoc
voi cac model khac"). Model len dan: moi manh MOT mau, nguoi choi go tung manh -> moi manh phai la MOT bo phan TRON VEN,
nhin vao la ra hinh cua no (cai dau tron, ban tay, cai yen...), khong phai mot mieng vo hay mot khoi gop hai thu.
Doc anh (Read, thu muc hien tai):
- views.png: 6 goc, moi manh mot mau, CHU DEN in tren manh = MA MANH (P06, P01.3...).
- sheet.png: tung manh rieng (cung mau) + ma + ten hien tai.
- excess.png (chi co khi tool do duoc): manh co PHAN DU, phan tool se cat TO DO (xem luat 4).
Danh sach manh o duoi (ma, ten, loai, % the tich ca model, hop bao). He toa do: mat truoc nhin -Y, X < 0 = ben trai nguoi xem.
BO PHAN CHUAN de doi chieu (khong bat buoc du, model nao co gi thi theo do):
- Nhan vat / con vat: DAU = MOT khoi dau tron ven (mat + so + phan mu trum om liền dau); tai, mom / mui, sung, toc mai la
  manh rieng neu nho ra ro. THAN (minh / ao). Moi tay = CANH TAY + BAN TAY (2 manh, tach o co tay). Moi chan = CHAN +
  BAN CHAN / GIAY (tach o co chan / mep giay). Duoi, canh. Mu roi / khan / balo / do cam tay = manh rieng.
- Xe: than xe, yen, op truoc / dau xe, san de chan, chan bun, banh (lop + vanh neu ro), ghi dong, den, thung hang (than + nap).
- Do vat / canh: tung khoi chuc nang (than, nap, de, quai, nut, man hinh, ngan...).
LOI CAN SUA:
1. MOT MANH GOP HAI BO PHAN (mat dinh voi than, canh tay lien ban tay, chan lien giay, yen lien than xe) -> "split": ghi RO
   tach thanh nhung gi va o dau, "parts" = ten cac phan sau khi tach (phan muon tach ra truoc, phan con lai cuoi).
2. MOT BO PHAN BI XE thanh nhieu manh khong co y nghia rieng -> "merge" thanh mot, kem ten. Vd: vo mu trum / mu bao hiem
   OM KIN dau (co tai gau tren mu) + manh mat -> GHEP thanh mot cai DAU tron ven; hai nua mom; mot lat cua than. Mu roi
   ro rang (vanh, chop, quai) thi GIU rieng. Chi ghep cac manh CHAM nhau, va CHI khi tung manh rieng le KHONG ra hinh
   gi (vo rong co lo, mot nua, mot lat) ma ghep lai moi thanh MOT khoi tron. KHONG ghep tam / khung / nhan dan / man
   hinh / mieng mau khac nam tren be mat mot khoi (tam the ben hong thung, nhan tim, khung kinh, den): do la chi tiet
   trang tri co y nghia, giu rieng.
3. Ten sai (trai / phai theo NGUOI XEM; manh ghi "tai" ma thuc ra la ma / quai mu; banh truoc / sau nham) -> "rename".
   Dong co [NGHI SAI TEN] (ten chi tiet nho ma to bat thuong / vat ngang than): XEM KY anh - manh "canh tay" thuc ra la
   AO KHOAC kem ong tay, "mu" thuc ra la dau + than... -> rename dung (ao khoac, than...) hoac split neu gop hai bo phan.
4. PHAN THUA tren mot manh (nguoi dung 2026-10-08: "banh xe co phan du thi nen cat di"): gai nhon / vat mong nhau moc ra,
   kim mong, MANH CUA BO PHAN KHAC dinh sang (vat op dau xe dinh o dau phuoc), vien rang cua lom chom -> "trim". Tool CAT
   dung phan TO DO trong excess.png (neu co: phan tool do duoc mong hon han than chinh), va kin, khong dep thi MESH LAI tu
   than chinh. excess.png cung to nham CHI TIET THAT mong hon than (tay cam cay can bot, qua bong / nu, vanh mat, canh,
   quai, gong kinh) -> manh do KHONG ghi trim. Phan thua khong duoc to do van ghi "trim" (ghi ro cai gi).
5. MANH KHONG RO LA GI (manh vo, mau vun, khoi la khong thuoc bo phan nao, khong doan duoc) -> "unknown" kem ly do; nguoi
   dung se xem va an. Doan duoc thi dat ten (rename) chu khong dua vao day.
6. MANH XAU KHONG CUU DUOC (rach nat, vo mong meo mo, lom chom ca manh, nhin khong ra hinh bo phan; cat phan thua cung
   khong dep) -> "hide" kem ly do: tool AN (khong xuat FBX), nguoi dung xem lai o panel. Chi dung khi bo manh di model van
   doc duoc; manh chinh (dau, than, banh) xau thi "trim" chu khong an.
- Manh nao vua bi tach o mot dong "split" thi KHONG ghep trong cung lan nay (lan xem sau se ghep phan da tach ra).
- Khong dong vao manh D (decor nho, mau xam nhat); khong tach vun (< ~0,5% model); khong tach khoi tron don (banh, bong).
- Viec cat do tool lam theo NEP GAP that cua manh - chi can noi tach thanh gi, o dau.
Tra ve CHI mot khoi JSON:
{"split": [{"piece": "P06", "want": "tách phần mặt (trên) khỏi thân (dưới) ở rãnh cổ", "parts": ["mặt", "thân"]},
           {"piece": "P04", "want": "tách bàn tay khỏi cánh tay ở cổ tay", "parts": ["bàn tay phải", "cánh tay phải"]}],
 "merge": [{"pieces": ["P01", "P07"], "label": "đầu"}],
 "rename": [{"piece": "P02", "label": "má phải"}],
 "trim": [{"piece": "P23", "want": "cắt bỏ vạt nhàu ở đầu phuộc (mảnh ốp đầu xe dính sang)"}],
 "unknown": [{"piece": "P31", "why": "mẩu vụn không thuộc bộ phận nào"}],
 "hide": [{"piece": "P06", "why": "đèn pha rách nát, viền lởm chởm"}],
 "notes": "1 cau tieng Viet co dau: con sai / thieu gi"}
Khong con gi sua -> {"split": [], "merge": [], "rename": [], "trim": [], "unknown": [], "hide": [], "notes": "..."}"""
TRIM_LABEL = "phần thừa"          # phan Claude bao cat bo (trim) - sau khi cat theo nep thi bo manh mang ten nay


def structure(name, it=1, history=""):
    """Claude xem CA model (work/<Ten>/struct/) -> struct_plan.json {split, merge, rename, notes}."""
    root = os.path.join(HERE, "work", name, "struct")
    rows = json.load(open(os.path.join(root, "pieces.json"), encoding="utf-8"))
    lines = "\n".join("  %-7s %-18s %s %5.1f%%  hop %s..%s%s%s" % (
        r["short"], r["label"] or "?", r["kind"], 100 * r["frac"], r["lo"], r["hi"],
        "  [excess.png: do %.0f%%]" % (100 * r["excess"]) if r.get("excess") else "",
        "  [NGHI SAI TEN: %s]" % r["suspect"] if r.get("suspect") else "") for r in rows)
    prev = ("\n# Cac lan truoc da lam (dung lap lai): %s" % history) if history else ""
    prompt = STRUCT_RULES + "\n# Model %s - lan xem %d\nCac manh:\n%s%s%s" % (name, it, lines, prev,
                                                                           prompt_note(name, "xem ca model"))
    rc, out, err = run_claude(prompt, root, timeout=900, kind="refine")
    d = _first_json(out, ("split", "merge", "rename"))
    if d is None:
        raise SystemExit("Claude khong tra ve ke hoach: %s" % (out[-600:] or err[-600:]))
    by = {r["short"]: r for r in rows}

    def full(x):
        x = str(x).strip().split(" ")[0]
        r = by.get(x)
        return r["name"] if r and r["kind"] != "D" else None
    split = []
    for s in d.get("split") or []:
        nm = full(s.get("piece", ""))
        if nm and s.get("want"):
            parts = [str(p).strip()[:40] for p in (s.get("parts") or []) if str(p).strip()]
            split.append({"piece": nm, "want": str(s["want"]).strip()[:300], "parts": parts})
    busy = {s["piece"] for s in split}
    merge = []
    for m in d.get("merge") or []:
        ps = [full(x) for x in (m.get("pieces") or [])]
        if len(ps) >= 2 and all(ps) and not busy & set(ps) and str(m.get("label") or "").strip():
            merge.append({"pieces": ps, "label": str(m["label"]).strip()[:40]})
            busy |= set(ps)
    rename = [{"piece": full(r_.get("piece", "")), "label": str(r_.get("label") or "").strip()[:40]}
              for r_ in d.get("rename") or [] if full(r_.get("piece", "")) and str(r_.get("label") or "").strip()]
    trim = []                                      # cat phan thua TRUC TIEP (wc/trim.repair o panel), khong tach theo nep
    for tr in d.get("trim") or []:
        nm = full(tr.get("piece", ""))
        if nm and nm not in busy and not any(s["piece"] == nm for s in split):
            trim.append({"piece": nm, "want": str(tr.get("want") or "").strip()[:200]})
            busy.add(nm)
    hide = [{"piece": full(u.get("piece", "")), "why": str(u.get("why") or "").strip()[:120]}
            for u in d.get("hide") or [] if full(u.get("piece", "")) and full(u.get("piece", "")) not in busy]
    unknown = [{"piece": full(u.get("piece", "")), "why": str(u.get("why") or "").strip()[:120]}
               for u in d.get("unknown") or [] if full(u.get("piece", ""))]
    res = {"it": it, "split": split, "merge": merge, "rename": rename, "unknown": unknown, "trim": trim, "hide": hide,
           "notes": str(d.get("notes") or "")}
    with open(os.path.join(root, "struct_plan.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print("[xem ca model] Claude: %s" % res["notes"])
    print("[xem ca model] tach %d, ghep %d, doi ten %d" % (len(split), len(merge), len(rename)))
    for s in split:
        print("   tach %s: %s -> %s" % (s["piece"], s["want"], ", ".join(s["parts"])))
    for m in merge:
        print("   ghep %s -> %s" % (" + ".join(m["pieces"]), m["label"]))
    for u in unknown:
        print("   KHONG RO %s: %s" % (u["piece"], u["why"]))
    for x in trim:
        print("   CAT PHAN THUA %s: %s" % (x["piece"], x["want"]))
    for x in hide:
        print("   AN (xau) %s: %s" % (x["piece"], x["why"]))
    return os.path.join(root, "struct_plan.json")


def palette_lines():
    """Bang mau cho Claude: ten slot + mau nguoi choi thay trong game (Highlight Unity x1.4, theo PrimForge)."""
    sys.path.insert(0, HERE)
    from wc import std
    out = []
    for n, nm, _, files in std.PALETTE:
        if not nm or n not in std.NOMINAL:
            continue
        mn = std.mat_name(n, nm)
        if std.UNITY and not std.in_unity(mn):
            continue
        h = (std.UNITY.get(mn) or {}).get("h")
        game = "#%02x%02x%02x" % tuple(int(min(1.0, c * 1.4) * 255) for c in h) if h else "?"
        nom = "#%02x%02x%02x" % tuple(int(c * 255) for c in std.NOMINAL[n])
        out.append("  %2d = %-14s ten goi %s, trong game %s (dung trong %d file goc)" % (n, nm, nom, game, files))
    return "\n".join(out)


PAINT_RULES = r"""
# Viec: TO MAU tung manh bang BANG MAU cua game (giong cach to cac model mau cua nguoi dung)
- Moi manh MOT mau, chi chon trong bang duoi, tra bang SO SLOT (vd 9 = Orange, 2 = Black, 25 = Gray nhat).
- Cac MUI cua cung mot bo phan (dau chia 4 mui, than 2 mui, de 4 cung) to CUNG mau - nhu dau gau BearArt toan
  White. Hai bo phan khac nhau CHAM nhau thi khac mau, tuong phan ro (mu / dau, ao / than, tay / do vat).
- Ca model dung 8-14 mau tren cac manh M/S (level game can 8-14; manh D - mat, nut, decor - KHONG tinh vao so nay).
  Mat/mui thuong Black, ma hong Pink, de/co Green...
- Neu model DA co mau tu texture: giu mau dang co khi hop ly, chi sua manh ro rang sai (vd hop qua bi ra cam ma
  ten goi la nau, lang lo khac mau giua cac mui cung bo phan).
- Xem anh mau bearart_game.png (gau trong game) de theo phong cach: mau tuoi, ro, it mau trung gian.
Tra ve CHI mot khoi JSON: {"notes": "1 cau", "colors": {"P01": 15, "P02": 12, ...}} - dua TAT CA manh."""


def paint(name, full=None, src="parts", hint=""):
    """Claude chon mau bang cho tung manh -> paint.json + thao tac color vao plan.json (cat lai khong mat).
    src="parts": manh cua lan cat (parts.json + anh parts_*); src="paint": manh DANG CO trong canh do panel chup
    (paint_parts.json + anh paint_*, cli paint-views) - to xong gan mau tai cho, KHONG cat lai (2026-10-07)."""
    work = os.path.join(HERE, "work", name)
    res = json.load(open(os.path.join(work, "%s.json" % ("paint_parts" if src == "paint" else "parts")), encoding="utf-8"))
    meta = json.load(open(os.path.join(work, "prep.json"), encoding="utf-8"))
    nocolor = len(meta.get("names", [])) <= 1
    rows = "\n".join("  %s %s mau-hien-tai=%s co=%.2f tam=%s" % (
        r["name"], r["kind"], r["color"].replace("Color_", "").replace("_mat", "").split("_", 1)[-1], r["size"],
        r.get("center")) for r in res["parts"])
    pnote = prompt_note(name, "to mau")
    if pnote:
        pnote += ("\n- TO MAU: bo phan nao prompt gan mau thi dung mau do (doi sang slot gan nhat trong bang), tru khi "
                  "hai bo phan cham nhau thanh trung mau.")
    if hint:                       # bang cham diem (wc/score.py) bao thieu mau / mang mot mau qua lon (2026-10-07)
        pnote += ("\n# UU TIEN theo BANG CHAM DIEM game (vuot luat 'giu mau texture'): %s\n- Doi mau cac bo phan lon "
                  "(ao / yem / quan, tay, chan, vien, phu kien) sang mau tuong phan cho du so mau va de mang cung mau "
                  "lon nhat nho lai; cac mui cua MOT bo phan van cung mau, hai bo phan cham nhau khac mau." % hint)
    prompt = PAINT_RULES + """
# Model %s %s
Anh (Read, thu muc hien tai): {p}_sheet.png (tung manh: ten loai mau-hien-tai), {p}_all.png (8 goc mau hien
tai), {p}_ids_all.png (8 goc moi manh mot mau), {f}. Anh mau: %s/bearart_game.png
Cac manh:
%s
Bang mau (ten -> mau):
%s%s""".format(p=src, f="paint_plan_front.png" if src == "paint" else "plan_front.png") % (
        name, "(model KHONG co texture: moi manh dang White - hay to toan bo theo y nghia bo phan)" if nocolor
        else "(mau hien tai doc tu texture)", REF, rows, palette_lines(), pnote)
    rc, out, err = run_claude(prompt, work, task="paint", kind="paint")
    m = re.search(r"\{.*\}", out, re.S)
    d = None
    for cand in ([m.group(0)] if m else []):
        try:
            d = json.loads(cand)
        except ValueError:
            d = extract_json(out)
    if not d or not isinstance(d.get("colors"), dict):
        raise SystemExit("Claude khong tra ve bang mau:\n%s\n%s" % (out[-2000:], err[-1000:]))
    sys.path.insert(0, HERE)
    from wc import std
    by = {r["name"]: r for r in res["parts"]}
    # manh da dat ten ten la "P12 tay phai" nhung Claude hay tra ma "P12" (2026-10-07: chuoi nen to 0/55 manh vi
    # khong khop ten) -> tra theo ma o dau ten
    by_code = {}
    for r in res["parts"]:
        by_code.setdefault(r["name"].split(" ")[0], r)
    ops = []
    for pn, col in d["colors"].items():
        r = by.get(pn) or by_code.get(str(pn).split(" ")[0])
        if r is None or not r.get("center"):
            continue
        pn = r["name"]
        try:
            mn = std.resolve_color(col)
        except KeyError:
            print("[to mau] bo qua mau la: %s=%s" % (pn, col))
            continue
        if mn != r["color"]:
            op = {"op": "color", "target": r["center"], "color": mn, "paint": True, "label": pn}
            if r.get("anchor"):
                op["anchor"] = r["anchor"]          # diem tren be mat manh - chon dung manh ke ca manh rong
            ops.append(op)
            d.setdefault("apply", {})[pn] = mn      # ten manh -> material da giai: panel / paint-apply gan thang
    with open(os.path.join(work, "paint.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)      # giu ban Claude chon (ap lai duoc)
    path = os.path.join(work, "plan.json")
    plan = json.load(open(path, encoding="utf-8"))
    plan["ops"] = [o for o in plan.get("ops", []) if not o.get("paint")] + ops
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    print("[to mau] Claude: %s" % d.get("notes", ""))
    print("[to mau] doi mau %d/%d manh (ghi ca plan.json: cat lai khong mat)" % (len(ops), len(res["parts"])))
    return len(ops)


def review(name, nmin=15, nmax=35):
    """Claude xem ket qua cat (bang manh, anh mau, canh bao) va sua ke hoach. Tra ve True neu da sua."""
    work = os.path.join(HERE, "work", name)
    res = json.load(open(os.path.join(work, "parts.json"), encoding="utf-8"))
    cur = open(os.path.join(work, "plan.json"), encoding="utf-8").read()
    rows = "\n".join("  %s %s %s co=%.2f tam=%s%s" % (r["name"], r["kind"], r["color"].replace("Color_", "").replace("_mat", ""),
                                                   r["size"], r.get("center"), (" !! " + r["warn"]) if r.get("warn") else "")
                     for r in res["parts"])
    log = "\n".join(res.get("log", []))
    prompt = RULES + """
# Vong SOAT ket qua cat model %s
Ke hoach hien tai:
%s
Nhat ky thuc thi:
%s
Ket qua (%d manh S/M can %d..%d):
%s
%s
Anh ket qua (Read) - XEM DU CAC GOC:
  parts_ids_all.png = 8 goc (truoc, sau, trai, phai, tren, iso, iso sau, no tung), moi manh mot mau -> thay duong cat;
  parts_all.png     = cac goc do voi mau that;
  parts_sheet.png   = tung manh rieng (ten loai mau);
  plan_*.png        = anh luoi toa do de doc toa do khi sua.
Kiem tung goc: duong cat co xuyen qua mat / mui / tai / nut khong, lung va dinh dau co bi cat vun khong.
Kiem: bo phan nao bi cat sai (lat mong, manh vun, cat ngang qua bo phan), bo phan nao chua tach (con dinh khoi
khac / lan mau; doi chieu danh sach bo phan trong prompt), khoi to nao chua chia mui, thao tac nao bao loi (!!).
Sua toa do / thu tu / loai thao tac.
Neu ket qua DA TOT: tra ve {"ok": true, "ops": []}. Neu can sua: tra ve TOAN BO ke hoach moi (JSON nhu tren).""" % (
        name, cur, log[-6000:], sum(1 for r in res["parts"] if r["kind"] != "D"), nmin, nmax, rows,
        prompt_note(name, "soat"))
    rc, out, err = run_claude(prompt, work, kind="review")
    d = extract_json(out)
    if d is None:
        print("[soat] Claude khong tra JSON - giu ke hoach cu")
        return False
    if d.get("ok") and not d.get("ops"):
        print("[soat] Claude: ket qua dat")
        return False
    d.setdefault("name", name)
    d["min"], d["max"] = nmin, nmax
    shutil.copy(os.path.join(work, "plan.json"), os.path.join(work, "plan_prev.json"))
    with open(os.path.join(work, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)
    print("[soat] Claude sua ke hoach: %s (%d thao tac)" % (d.get("notes", ""), len(d["ops"])))
    return True
