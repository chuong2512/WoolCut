"""WoolCut - tao model len tu prompt: Claude viet prompt -> Tripo tao model -> Claude + Blender TACH MANH
(moi manh mot mau, cat phang nhu bo goc) -> dat ten S/M/D, xuat FBX.

Cong chay bang python he thong:
  python woolcut/run.py prompt [--idea "chu meo lam banh"]                 # 1: Claude viet prompt + thiet lap Tripo
  python woolcut/run.py gen    --prompt "..." --name Ten [--yes]           # 2: Tripo (khong --yes = chi uoc tinh credit)
  python woolcut/run.py gen    --task <task_id> --name Ten                 #    tai lai task cu, khong ton credit
  python woolcut/run.py split  --in <model.glb> --name Ten [--turn -90] [--min 15 --max 35] [--rounds 1]
                                                                          # 3 tron goi: prep -> Claude lap ke hoach -> cat -> Claude soat
  python woolcut/run.py prep   --in <model.glb> --name Ten [--turn -90] [--remesh]  # 3a: khoi kin (giu luoi Tripo) + mau + anh luoi
  python woolcut/run.py plan   --name Ten [--min 15 --max 35]             # 3b: Claude doc anh -> work/Ten/plan.json
  python woolcut/run.py cut    --name Ten [--min 15 --max 35]             # 3c: thuc thi plan.json (sua tay duoc)
  python woolcut/run.py review --name Ten                                 # 3d: Claude xem ket qua, sua plan.json
  python woolcut/run.py paint  --name Ten [--in canh.blend]              # 3e: Claude to mau bang (gan thang, khong cat lai)
  python woolcut/run.py export --name Ten [--in work/Ten/parts_edit.blend] # 4: ten S/M/D + FBX vao woolcut/out
  python woolcut/run.py auto   --in <model.glb> --name Ten [--paint] [--force] [--no-facing]
                                                                          # HANG LOAT: mat truoc -> tach bo phan + dat ten
  python woolcut/run.py struct --name Ten --in <manh.blend> [--it 1]     # XEM CA MODEL: Claude de xuat tach / ghep / doi ten
  python woolcut/run.py refine --name Ten --in <manh.blend> --pieces "P01 than|P06 xe" [--hint ".."] [--force] [--hints f.json]
                                                                          # TACH SAU: xem tung bo phan + nep gap -> Claude chon
"""
import os, sys, glob, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PREP_VERSION = 11            # = wc/prep.py PREP_VERSION (run.py khong import bpy nen ghi lai o day)
for _s in (sys.stdout, sys.stderr):                 # console Windows cp1252 khong in duoc tieng Viet co dau
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
CANDIDATES = [
    r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
]


def blender():
    env = os.environ.get("BLENDER_EXE")
    if env and os.path.exists(env):
        return env
    for c in CANDIDATES:
        if os.path.exists(c):
            return c
    hits = sorted(glob.glob(r"C:\Program Files\Blender Foundation\*\blender.exe"))
    if hits:
        return hits[-1]
    w = shutil.which("blender")
    if w:
        return w
    raise SystemExit("Khong tim thay blender.exe - dat bien moi truong BLENDER_EXE")


NOISE = ("Blender ", "Read ", "Fra:", "Saved:", " Time:", "FBX ", "Warning: ", "INFO:", "DeprecationWarning",
         "  world.use_nodes", "  m.use_nodes", "  w.use_nodes")


def run_blender(args):
    cmd = [blender(), "-b", "--factory-startup", "--python-exit-code", "1",
           "--python", os.path.join(HERE, "wc", "cli.py"), "--"] + args
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                         encoding="utf-8", errors="replace")
    for line in p.stdout:
        if line.strip() and not any(n in line for n in NOISE) and "render" not in line.split("|")[0]:
            sys.stdout.write(line)
            sys.stdout.flush()
    return p.wait()


def _opt(argv, key, default=None, cast=str):
    if key in argv:
        i = argv.index(key)
        if i + 1 < len(argv):
            return cast(argv[i + 1])
    return default


def save_prompt(argv):
    """--prompt "..." (o "Prompt cua model" o panel) -> work/<Ten>/prompt.txt; Claude doc khi cat / soat / to mau."""
    name = _opt(argv, "--name")
    if name and "--prompt" in argv:
        work = os.path.join(HERE, "work", name)
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, "prompt.txt"), "w", encoding="utf-8") as fh:
            fh.write((_opt(argv, "--prompt", "") or "").strip())


def facing_cmd(argv):
    """Tu tim mat truoc: Blender render 4 goc -> Claude chon -> in TURN: <do> (addon xoay theo)."""
    sys.path.insert(0, HERE)
    from wc import planner
    name, src = _opt(argv, "--name"), os.path.abspath(_opt(argv, "--in"))
    print("[mat truoc] Blender chup model 6 huong...")
    sys.stdout.flush()
    if run_blender(["facing", "--in", src, "--name", name]):
        return 1
    print("[mat truoc] Claude xem anh 6 huong...")
    sys.stdout.flush()
    t = planner.facing(name, src)
    if t is None:
        return 1
    print("TURN:", t[0])
    print("TILT:", t[1])
    return 0


def auto_cmd(argv):
    """TACH HANG LOAT (nguoi dung 2026-10-07: "nem nhieu model vao, nap lan luot va tach, sau do t vao soat"): MOT file
    -> tim mat truoc -> tach bo phan + dat ten (+ to mau neu --paint). Addon goi lan luot tung file trong hang doi.
    Model da tach (co parts.json) thi BO QUA (khong ghi de ke hoach / chinh tay), tru khi --force.
    In AUTO_READY: <Ten> | AUTO_SKIP: <Ten> - <ly do>."""
    sys.path.insert(0, HERE)
    from wc import planner, tripo
    name, src = _opt(argv, "--name"), os.path.abspath(_opt(argv, "--in") or "")
    if not name or not os.path.exists(src):
        print("AUTO_FAIL: khong thay file %s" % src)
        return 1
    work = os.path.join(HERE, "work", name)
    if os.path.exists(os.path.join(work, "parts.json")) and "--force" not in argv:
        print("AUTO_SKIP: %s - da tach truoc do (bo qua de khong ghi de)" % name)
        return 0
    # mat truoc: file Tripo API (inbox) nhin +X -> mac dinh -90; file tai tu web da nhin -Y -> 0
    turn = tripo.TURN if os.path.dirname(src).lower() == os.path.abspath(tripo.INBOX).lower() else 0.0
    tilt = 0.0
    if "--no-facing" not in argv:
        print("[hang loat] %s: tim mat truoc..." % name)
        sys.stdout.flush()
        if run_blender(["facing", "--in", src, "--name", name]) == 0:
            t = planner.facing(name, src)
            if t is not None:
                turn, tilt = float(t[0]), float(t[1])
        print("[hang loat] %s: xoay %+.0f, lat %+.0f" % (name, turn, tilt))
    keep = []
    for k in ("--min", "--max", "--bevel", "--tiny"):
        if _opt(argv, k) is not None:
            keep += [k, _opt(argv, k)]
    keep += [f for f in ("--paint", "--no-paint", "--bumps", "--reprep") if f in argv]
    if "--force" in argv:
        keep.append("--reprep")
    rc = split_cmd(["--in", src, "--name", name, "--turn", str(turn), "--tilt", str(tilt), "--parts-only"] + keep)
    if rc:
        print("AUTO_FAIL: %s - tach loi (ma %s)" % (name, rc))
        return rc
    print("AUTO_READY: %s" % name)
    return 0


def split_cmd(argv):
    """prep (neu chua co hoac doi file) -> plan -> cut -> soat x rounds."""
    sys.path.insert(0, HERE)
    from wc import planner
    name = _opt(argv, "--name")
    src = _opt(argv, "--in")
    nmin, nmax = _opt(argv, "--min", 15, int), _opt(argv, "--max", 35, int)
    rounds = _opt(argv, "--rounds", 1, int)
    work = os.path.join(HERE, "work", name)
    pj = os.path.join(work, "prep.json")
    need_prep = "--reprep" in argv or not os.path.exists(pj)
    if not need_prep and src:
        import json
        old = json.load(open(pj, encoding="utf-8"))
        need_prep = os.path.abspath(old.get("src", "")) != os.path.abspath(src)
        if abs(float(old.get("tilt", 0.0)) - _opt(argv, "--tilt", 0.0, float)) > 0.5:
            print("[prep] goc lat doi -> chuan bi lai")
            need_prep = True
        if abs(float(old.get("turn", 0.0)) - _opt(argv, "--turn", 0.0, float)) > 0.5:
            print("[prep] goc xoay doi (%s -> %s) -> chuan bi lai" % (old.get("turn"), _opt(argv, "--turn")))
            need_prep = True
        if old.get("prep_version", 0) < PREP_VERSION:
            print("[prep] buoc chuan bi cu (ban %s < %d) -> chuan bi lai" % (old.get("prep_version"), PREP_VERSION))
            need_prep = True
    if need_prep:
        args = ["prep", "--in", src, "--name", name, "--turn", str(_opt(argv, "--turn", 0.0, float)),
                "--tilt", str(_opt(argv, "--tilt", 0.0, float))]
        if "--remesh" in argv:
            args.append("--remesh")
        if "--bumps" in argv:
            args.append("--bumps")
        if run_blender(args):
            return 1
    plan_json = os.path.join(work, "plan.json")
    parts_only = "--parts-only" in argv
    if parts_only:                       # moi part Tripo = mot manh, khong cat (nguoi dung 2026-10-02)
        import json as _j, shutil as _sh
        if os.path.exists(plan_json):
            _sh.copy(plan_json, os.path.join(work, "plan_prev.json"))
        with open(plan_json, "w", encoding="utf-8") as fh:
            _j.dump({"name": name, "notes": "Tach theo part Tripo - khong cat", "ops": []}, fh, indent=1)
        print("[plan] tach theo part: khong cat (ke hoach cu -> plan_prev.json)")
        rounds = 0
    elif "--keep-plan" not in argv or not os.path.exists(plan_json):
        print("[plan] Claude dang doc anh va lap ke hoach cat (1-3 phut)...")
        sys.stdout.flush()
        planner.plan(name, nmin, nmax)
    if "--plan-only" in argv:            # chi lap ke hoach: nguoi dung xem truoc, chinh, xac nhan o panel
        print("[xem truoc] chay thu ke hoach (chi hinh hoc)...")
        sys.stdout.flush()
        run_blender(["trace", "--name", name])
        print("PLAN_READY:", plan_json)
        return 0
    cut = ["cut", "--name", name, "--min", str(nmin), "--max", str(nmax)]
    if _opt(argv, "--bevel") is not None:
        cut += ["--bevel", _opt(argv, "--bevel")]
    if _opt(argv, "--tiny") is not None:
        cut += ["--tiny", _opt(argv, "--tiny")]
    if run_blender(cut):
        return 1
    for r in range(rounds):
        print("[soat] vong %d: Claude xem ket qua..." % (r + 1))
        sys.stdout.flush()
        if not planner.review(name, nmin, nmax):
            break
        if run_blender(cut):
            return 1
    import json as _json
    colorless = len(_json.load(open(pj, encoding="utf-8")).get("names", [])) <= 1
    if "--paint" in argv or (colorless and "--no-paint" not in argv):
        print("[to mau] Claude to mau bang cho tung manh%s..." % (" (model khong co mau)" if colorless else ""))
        sys.stdout.flush()
        try:
            if planner.paint(name) and run_blender(["paint-apply", "--name", name]):   # gan thang, khong cat lai
                return 1
        except SystemExit as e:
            print("[to mau] bo qua: %s" % e)
    if parts_only or "--label" in argv:
        print("[dat ten] Claude dat ten tung bo phan...")
        sys.stdout.flush()
        try:
            planner.label(name)
        except SystemExit as e:
            print("[dat ten] bo qua: %s" % e)
    print("SPLIT_READY:", os.path.join(work, "parts.blend"))
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = sys.argv[1]
    if cmd in ("prep", "cut", "export", "trace", "decor-lib", "decor-views", "decor-custom", "piece-views", "refine-views",
               "struct-views", "paint-views", "paint-apply"):
        args = list(sys.argv[1:])
        if "--in" in args:                        # Blender hieu duong dan tuong doi theo file .blend -> doi tuyet doi
            i = args.index("--in") + 1
            if i < len(args):
                args[i] = os.path.abspath(args[i])
        return run_blender(args)
    if cmd in ("split", "plan", "review", "paint"):
        save_prompt(sys.argv[2:])
    if cmd == "split":
        return split_cmd(sys.argv[2:])
    if cmd == "auto":
        return auto_cmd(sys.argv[2:])
    if cmd == "piece-plan":
        sys.path.insert(0, HERE)
        from wc import planner
        a = sys.argv[2:]
        save_prompt(a)
        name, piece = _opt(a, "--name"), _opt(a, "--piece")
        print("[chia manh] chup anh manh %s..." % piece)
        sys.stdout.flush()
        if run_blender(["piece-views", "--name", name, "--in", os.path.abspath(_opt(a, "--in")), "--piece", piece]):
            return 1
        print("[chia manh] Claude xem va lap ke hoach...")
        sys.stdout.flush()
        planner.piece_plan(name, _opt(a, "--label", piece), _opt(a, "--hint", "") or "")
        print("PIECE_PLAN_READY:", os.path.join(HERE, "work", name, "piece_plan.json"))
        return 0
    if cmd == "refine":
        sys.path.insert(0, HERE)
        from wc import planner
        a = sys.argv[2:]
        save_prompt(a)
        name = _opt(a, "--name")
        pieces = _opt(a, "--pieces", "") or ""
        print("[tach sau] chup anh + do nep gap tung bo phan...")
        sys.stdout.flush()
        if run_blender(["refine-views", "--name", name, "--in", os.path.abspath(_opt(a, "--in")), "--pieces", pieces]):
            return 1
        hints = None
        if _opt(a, "--hints"):
            import json as _j
            hints = _j.load(open(_opt(a, "--hints"), encoding="utf-8"))
        path = planner.refine_all(name, _opt(a, "--hint", "") or "", force="--force" in a, hints=hints)
        print("REFINE_READY:", path)
        return 0
    if cmd == "struct":
        sys.path.insert(0, HERE)
        from wc import planner
        a = sys.argv[2:]
        save_prompt(a)
        name = _opt(a, "--name")
        print("[xem ca model] chup ca model, in ma tung manh...")
        sys.stdout.flush()
        if run_blender(["struct-views", "--name", name, "--in", os.path.abspath(_opt(a, "--in"))]):
            return 1
        print("[xem ca model] Claude doi chieu bo phan...")
        sys.stdout.flush()
        path = planner.structure(name, _opt(a, "--it", 1, int), _opt(a, "--history", "") or "")
        print("STRUCT_READY:", path)
        return 0
    if cmd == "decor":
        sys.path.insert(0, HERE)
        from wc import planner
        a = sys.argv[2:]
        save_prompt(a)
        name = _opt(a, "--name")
        print("[decor] chup anh cac manh hien tai...")
        sys.stdout.flush()
        if run_blender(["decor-views", "--name", name, "--in", os.path.abspath(_opt(a, "--in"))]):
            return 1
        print("[decor] Claude chon va dat decor...")
        sys.stdout.flush()
        allowed = [x for x in (_opt(a, "--allow", "") or "").split(",") if x]
        n = planner.decor(name, allowed or None)
        import json as _j
        newd = _j.load(open(os.path.join(HERE, "work", name, "decor_plan.json"), encoding="utf-8")).get("new", [])
        if newd:
            print("[decor] dung %d decor moi..." % len(newd))
            sys.stdout.flush()
            run_blender(["decor-custom"])
            print("DECOR_NEW:", ", ".join("%s (%s)" % (v, i) for i, v in newd))
        print("DECOR_READY:", os.path.join(HERE, "work", name, "decor_plan.json"))
        return 0
    if cmd == "label":
        sys.path.insert(0, HERE)
        from wc import planner
        save_prompt(sys.argv[2:])
        n = planner.label(_opt(sys.argv[2:], "--name"))
        print("LABEL_READY:", n)
        return 0
    if cmd == "facing":
        return facing_cmd(sys.argv[2:])
    if cmd in ("prompt", "gen", "balance"):
        sys.path.insert(0, HERE)
        from wc import stages
        if cmd == "balance":
            from wc import tripo
            print(tripo.balance())
            return 0
        return (stages.prompt_cmd if cmd == "prompt" else stages.gen_cmd)(sys.argv[2:])
    if cmd == "paint":
        sys.path.insert(0, HERE)
        from wc import planner
        a = sys.argv[2:]
        name, src = _opt(a, "--name"), _opt(a, "--in")
        if src:                       # panel: manh DANG CO trong canh -> chup anh, Claude to, panel gan mau tai cho
            print("[to mau] chup anh cac manh hien tai (khong cat lai)...")
            sys.stdout.flush()
            if run_blender(["paint-views", "--name", name, "--in", os.path.abspath(src)]):
                return 1
            print("[to mau] Claude dang chon mau bang cho tung manh...")
            sys.stdout.flush()
            planner.paint(name, src="paint")
            print("PAINT_READY:", os.path.join(HERE, "work", name, "paint.json"))
            return 0
        print("[to mau] Claude dang chon mau bang cho tung manh...")
        sys.stdout.flush()
        planner.paint(name)
        rc = run_blender(["paint-apply", "--name", name])
        if rc == 0:
            print("SPLIT_READY:", os.path.join(HERE, "work", name, "parts.blend"))
        return rc
    if cmd in ("plan", "review"):
        sys.path.insert(0, HERE)
        from wc import planner
        a = sys.argv[2:]
        fn = planner.plan if cmd == "plan" else planner.review
        r = fn(_opt(a, "--name"), _opt(a, "--min", 15, int), _opt(a, "--max", 35, int))
        return 0
    print("lenh la: %s" % cmd)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
