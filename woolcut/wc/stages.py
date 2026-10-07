"""Buoc 1 (Claude viet prompt) va buoc 2 (Tripo tao model) - chep tu PrimForge run.py (2026-10-01),
chay bang python he thong qua woolcut/run.py. Lenh ton credit chi chay khi co --yes."""
import os, sys, glob, json, subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def prompt_cmd(argv):
    import argparse, shutil
    sys.path.insert(0, HERE)
    from wc import prompt
    ap = argparse.ArgumentParser(prog="run.py prompt")
    ap.add_argument("--idea", default="")
    from wc import categories as cat
    ap.add_argument("--kind", choices=sorted(cat.FORMATS), default="char")
    ap.add_argument("--theme", choices=sorted(cat.THEMES), default="free")
    a = ap.parse_args(argv)
    exe = shutil.which("claude") or os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
    if not os.path.exists(exe):
        raise SystemExit("Khong tim thay claude CLI")
    have = sorted(os.path.splitext(os.path.basename(f))[0]
                  for f in glob.glob(os.path.join(os.path.dirname(HERE), "*.fbx")))
    made = sorted({os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(HERE, "out", "*.fbx"))})
    from wc import planner
    model, effort = planner.SPEED.get(os.environ.get("WOOLCUT_SPEED", "normal"), planner.SPEED["normal"])["paint"]
    extra = (["--model", model] if model else []) + (["--effort", effort] if effort else [])
    def ask(text):
        return subprocess.run([exe, "-p", text, "--output-format", "text"] + extra + [
                              "--disallowedTools", "Bash", "Edit", "Write", "Read", "Glob", "Grep", "WebFetch",
                              "WebSearch", "NotebookEdit"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    brief = prompt.brief(a.idea, have, made, kind=a.kind, theme=a.theme)
    p = ask(brief)
    out = p.stdout
    # prompt qua dai (Tripo cat o 1024 tinh ca cau phong cach ~260) -> nho Claude rut gon, giu du cac bo phan
    for _ in range(2):
        got = prompt.parse(out.splitlines())
        if len(got.get("PROMPT", "")) <= 740:
            break
        p = ask(brief + "\n\nYour previous answer:\n" + out + "\n\nThe PROMPT line is %d characters - TOO LONG. "
                "Rewrite it under 700 characters: keep every named piece and the Decor sentence, use shorter wording. "
                "Reply with the same 7 lines." % len(got.get("PROMPT", "")))
        out = p.stdout
    print(out)
    return p.returncode


# ------------------------------------------------------------------ buoc 2
def gen_cmd(argv):
    import argparse
    sys.path.insert(0, HERE)
    from wc import tripo
    ap = argparse.ArgumentParser(prog="run.py gen")
    ap.add_argument("--name")
    ap.add_argument("--prompt")
    ap.add_argument("--image", help="duong dan anh PNG/JPG hoac URL")
    ap.add_argument("--preset", choices=sorted(tripo.PRESETS), default="color")
    ap.add_argument("--style", choices=sorted(tripo.STYLES), default="parts")
    ap.add_argument("--model", default=None, help="P1-20260311 (mac dinh) | P2-20260801 | v3.1-20260211")
    ap.add_argument("--topology", choices=("tri", "quad"), default=None)
    ap.add_argument("--faces", type=int, help="polycount (face_limit)")
    ap.add_argument("--no-texture", action="store_true", help="khong mau (re hon) - buoc 3 tach theo hinh khoi")
    ap.add_argument("--raw", action="store_true", help="khong noi cau phong cach vao prompt")
    ap.add_argument("--task", help="lay lai ket qua mot task da tao (khong ton credit)")
    ap.add_argument("--yes", action="store_true", help="THAT SU gui (ton credit)")
    a = ap.parse_args(argv)
    if not a.name:
        raise SystemExit("can --name")
    if a.task:
        task_id = a.task
    else:
        if not a.prompt and not a.image:
            raise SystemExit("can --prompt hoac --image")
        kind = "image" if a.image else "text"
        img = a.image if (a.image and a.image.startswith("http")) else ("<file_token>" if a.image else None)
        body = tripo.request_body(a.prompt, img, a.preset, a.model or tripo.DEFAULT_MODEL,
                                  style=False if a.raw else a.style,
                                  topology=a.topology or tripo.DEFAULT_TOPOLOGY, faces=a.faces or tripo.DEFAULT_FACES,
                                  extra={"texture": False} if a.no_texture else None)
        lo, hi = tripo.face_range(body)
        if not lo <= body["face_limit"] <= hi:
            raise SystemExit("Tripo loi: polycount %d ngoai khoang %d-%d cua %s" % (
                body["face_limit"], lo, hi, tripo.MODELS.get(body["model"], {}).get("label", body["model"])))
        print("[tripo] %s-to-model, uoc tinh ~%d credit" % (kind, tripo.estimate(body, kind)))
        print(json.dumps(body, indent=1, ensure_ascii=False))
        if not a.yes:
            print("\n[tripo] CHUA GUI. Them --yes de gui that (ton credit).")
            return 0
        if os.environ.get("WOOLCUT_NO_TRIPO") or os.environ.get("PRIMFORGE_NO_TRIPO"):
            # Dat boi addon khi chay Claude CLI: agent khong duoc tu tieu credit cua nguoi dung
            raise SystemExit("[tripo] bi chan: tien trinh nay khong duoc phep ton credit Tripo")
        need = tripo.estimate(body, kind)
        try:
            have = float(tripo.balance().get("balance", 0))
            print("[tripo] vung %s, API bao con %g credit (can ~%d)" % (tripo.API, have, need))
        except SystemExit as e:
            print("[tripo] khong hoi duoc so du: %s" % e)
        if a.image and not a.image.startswith("http"):
            body["input"] = tripo.upload(a.image)
        try:
            task_id = tripo.create(body, kind)
        except SystemExit as e:
            # texture v3.5 + delight moi, chua chac moi model nhan: bi tu choi tham so thi gui lai mot lan
            # khong co hai muc do (loi tham so khong tru credit)
            if "1004" in str(e) and "texture_version" in body:
                print("[tripo] Tripo khong nhan texture v3.5/delight (%s) - gui lai khong co" % e)
                body.pop("texture_version", None)
                body.pop("delight", None)
                task_id = tripo.create(body, kind)
            else:
                raise
        print("[tripo] task", task_id)
        os.makedirs(tripo.INBOX, exist_ok=True)
        with open(os.path.join(tripo.INBOX, a.name + ".tripo.json"), "w", encoding="utf-8") as fh:
            json.dump({"task_id": task_id, "kind": kind, "style": a.style, "request": body}, fh, indent=1,
                      ensure_ascii=False)
    have = [f for f in glob.glob(os.path.join(tripo.INBOX, "%s_%s.*" % (a.name, task_id[-8:])))
            if f.lower().endswith((".fbx", ".glb", ".gltf", ".obj"))]
    if have:
        model = have[0]
        print("[tripo] dung lai file da tai:", model)
    else:
        d = tripo.wait(task_id)
        out = d.get("output", {})
        if not out.get("model_url"):
            raise SystemExit("[tripo] task xong nhung khong co model_url: %s" % out)
        model = tripo.download(out["model_url"], "%s_%s" % (a.name, task_id[-8:]))
        print("[tripo] model ->", model)
        if out.get("rendered_image_url"):
            print("[tripo] anh Tripo ->", tripo.download(out["rendered_image_url"], a.name + "_tripo_preview"))
    # Dong in nay la GIAO KEO voi addon. Tripo xuat model mat nhin +X; bo goc nhin -Y -> xoay TURN (-90)
    print("MODEL_READY: %s" % model)
    print("TURN: %g" % tripo.TURN)
    return 0


