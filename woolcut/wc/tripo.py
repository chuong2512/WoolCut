"""Buoc 2: goi Tripo API v3 bang python he thong, chi dung thu vien chuan. Tai model THO ve
woolcut/inbox/ (chua tach) - buoc 3 (`run.py split`) moi tach thanh bo phan.

API key: bien moi truong TRIPO_API_KEY, hoac file woolcut/data/tripo_key.txt.

HAI VUNG, key va credit KHONG dung chung (kiem 2026-09-30 bang key that):
  quoc te   https://openapi.tripo3d.ai/v3   (key tsk_... tu platform.tripo3d.ai) - mac dinh
  TQ        https://openapi.tripo3d.com/v3  (trang developers.tripo3d.com ghi day la "Primary"
            nhung key quoc te bi bao "Invalid API key" o day)
Doi vung: TRIPO_REGION=cn, hoac TRIPO_API_BASE=<url> de chi dinh han.

Tai lieu (doc 2026-09-30):
  POST /generation/text-to-model | /generation/image-to-model  -> data.task_id
  GET  /tasks/{task_id}  -> data.status queued|running|success|failed|banned|expired|cancelled,
                            data.progress, data.output.model_url, data.output.rendered_image_url
  POST /files (multipart 'file') -> data.file_token
  GET  /account/balance -> data.balance, data.frozen
  generate_parts KHONG di cung texture/pbr/quad/smart_low_poly.
"""
import os, json, time, uuid, mimetypes, urllib.request, urllib.error, urllib.parse

REGIONS = {"global": "https://openapi.tripo3d.ai/v3", "cn": "https://openapi.tripo3d.com/v3"}
API = os.environ.get("TRIPO_API_BASE") or REGIONS.get(os.environ.get("TRIPO_REGION", "global"), REGIONS["global"])
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(HERE, "inbox")

# Khop bo 108 file: trung vi ~17k tam giac/model, mat tu giac la chinh, mau phang.
TURN = -90.0      # goc xoay bu cho model Tripo (mat nhin +X -> -Y)

# Model AI. Mac dinh theo thiet lap web nguoi dung chon (2026-09-30): P1.0 Fast,
# Smart Mesh, Triangle, 8000. Dong P von la low-poly luoi sach -> khong can smart_low_poly.
# Khoang face_limit theo tai lieu Tripo 2026-09.
MODELS = {
    "P1-20260311":   {"label": "P1.0 · Fast", "tri": (50, 20000), "quad": None, "smart": False},
    "P2-20260801":   {"label": "P2.0", "tri": (48, 50000), "quad": (48, 25000), "smart": False},
    "v3.1-20260211": {"label": "H3.1 · Smart Mesh", "tri": (500, 20000), "quad": (500, 10000), "smart": True},
}
DEFAULT_MODEL, DEFAULT_TOPOLOGY, DEFAULT_FACES = "P1-20260311", "tri", 8000

PRESETS = {
    # co mau (texture) -> conform tach manh theo vung mau. Texture v3.5 + delight bo
    # anh sang nuong san trong texture: bong do/AO lam mot vung mau vo thanh nhieu mau.
    "color": {"texture": True, "pbr": False, "texture_quality": "standard",
              "texture_version": "v3.5-20260815", "delight": True},
    # tach manh san, KHONG mau (Tripo cam gop) -> to mau bang --paint. Chi dong H.
    "parts": {"texture": False, "pbr": False, "generate_parts": True},
}
STYLES = {
    # Mac dinh (quy trinh 4 buoc, 2026-10-01): it khoi to, moi khoi mot mau, khoi cham nhau khac mau ->
    # buoc 3 tach theo mau + hinh khoi sach. Giong cau cuoi cua 5 prompt web nguoi dung da duyet.
    "parts": ("Cute stylized toy figure assembled from many separate chunky rounded pieces with visible grooves "
              "between them, small raised decor shapes, each piece one flat solid color, touching pieces in "
              "contrasting colors, smooth surfaces, no text, no fine texture detail"),
    # Do vat don gian (xe bus mini, may anh...) - "toy figure" keo Tripo ve nhan vat, nen dung cau rieng
    "object": ("Cute stylized chunky toy object assembled from many separate rounded pieces with visible grooves "
               "and rims between them, soft edges, small raised decor shapes, each piece one flat solid color, "
               "touching pieces in contrasting colors, smooth surfaces, no text, no fine texture detail"),
    # Cac kieu cu (giu de chay lai task da tao)
    "amigurumi": ("cute stylized amigurumi-like toy figure built from many separate chunky rounded pieces with "
                  "visible seams between pieces, smooth surfaces, simple flat solid colors, no text, "
                  "no fine texture detail"),
    "multi": ("cute stylized 3D toy scene assembled from many separate solid parts, every part a distinct "
              "chunky rounded object in its own flat solid color, small raised decor shapes, touching parts in "
              "contrasting colors, clear seams between parts, smooth surfaces, no text, no fine texture detail"),
}
STYLE = STYLES["parts"]
# Uoc tinh credit theo bang gia H3.1 (text 10/20, image 20/30 khong/co texture;
# smart low poly +10, quad +5, parts +20). Chi de tham khao.
COST = {"text": (10, 20), "image": (20, 30)}


def api_key():
    k = os.environ.get("TRIPO_API_KEY")
    if not k:
        p = os.path.join(HERE, "data", "tripo_key.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                k = fh.read().strip()
    if not k:
        raise SystemExit("Chua co API key Tripo. Dat bien moi truong TRIPO_API_KEY "
                         "hoac ghi key vao woolcut/data/tripo_key.txt")
    return k


def _call(method, path, body=None, data=None, headers=None):
    h = {"Authorization": "Bearer " + api_key()}
    h.update(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read().decode("utf-8"))
        except Exception:
            raise SystemExit("Tripo HTTP %d: %s" % (e.code, e.reason))
    if res.get("code", 0) != 0:
        hint = ""
        if res.get("code") == 2010 or "credit" in str(res.get("message", "")).lower():
            hint = (" - credit tren trang web Tripo KHONG dung duoc cho API; "
                    "can credit API cua dung tai khoan lay key")
        raise SystemExit("Tripo loi %s: %s %s%s" % (res.get("code"), res.get("message", ""),
                                                    res.get("suggestion", ""), hint))
    return res.get("data", {})


def upload(path):
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        payload = fh.read()
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
             "Content-Type: %s\r\n\r\n" % (boundary, os.path.basename(path), ctype)).encode()
            + payload + ("\r\n--%s--\r\n" % boundary).encode())
    d = _call("POST", "/files", data=body,
              headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    return d["file_token"]


def request_body(prompt=None, image=None, preset="color", model=DEFAULT_MODEL, style=True, extra=None,
                 topology=DEFAULT_TOPOLOGY, faces=DEFAULT_FACES):
    if preset == "parts" and model.startswith("P"):
        model = "v3.1-20260211"                # generate_parts chi co o dong H (model >= v3.0)
    info = MODELS.get(model, MODELS["v3.1-20260211"])
    if topology == "quad" and not info["quad"]:
        raise SystemExit("Tripo loi: %s khong ho tro tu giac (quad) - chon Triangle hoac P2.0/H3.1"
                         % info["label"])
    body = {"model": model}
    body.update(PRESETS[preset])
    body["face_limit"] = faces
    if preset == "color":
        if info["smart"]:
            body["smart_low_poly"] = True
        if topology == "quad":
            body["quad"] = True
    if image:
        body["input"] = image                  # file_token, URL, hoac task_id
    elif prompt:                               # image-to-model khong co truong prompt
        tail = STYLES.get(style if isinstance(style, str) else "parts", STYLE) if style else None
        body["prompt"] = (prompt.rstrip(" .,") + ", " + tail) if tail else prompt
        body["prompt"] = body["prompt"][:1024]
    body.update(extra or {})
    if body.get("generate_parts"):
        for k in ("texture", "pbr"):
            body[k] = False
        for k in ("quad", "smart_low_poly"):
            body.pop(k, None)
    return body


def face_range(body):
    info = MODELS.get(body.get("model"))
    if body.get("generate_parts") or info is None:
        return (48, 150000) if body.get("quad") else (48, 1500000)
    return info["quad"] if body.get("quad") else info["tri"]


# Tu mau trong prompt -> mau bang duoc phep. Bang goc co nhieu mau na na (Beige thuc
# ra la hong dao, Brown rat toi); gioi han theo y nguoi viet prompt thi chon dung hon.
HINTS = [
    ("sky blue", ["Sky"]), ("light blue", ["Sky"]), ("navy", ["DeepOcean", "Blue"]), ("blue", ["Blue", "Sky"]),
    ("turquoise", ["TurquoiseMint", "Cyan"]), ("mint", ["TurquoiseMint"]), ("teal", ["Cyan", "DeepOcean"]),
    ("lemon", ["yellow02"]), ("golden", ["Yellow", "yellow02"]), ("gold", ["Yellow"]),
    ("yellow", ["Yellow", "yellow02"]), ("dark green", ["DarkGreen"]), ("forest", ["Forest"]),
    ("green", ["Green", "DarkGreen"]), ("cream", ["Cream", "White"]), ("ivory", ["Cream", "White"]),
    ("beige", ["Beige"]), ("peach", ["Beige"]), ("tan", ["Beige", "Brown"]),
    ("wood", ["Brown", "Orange"]), ("brown", ["Brown", "Orange"]), ("chocolate", ["Brown"]),
    ("bread", ["Orange", "Brown"]), ("loaf", ["Orange", "Brown"]), ("crimson", ["Crimson"]),
    ("red", ["Red", "Crimson"]), ("orange", ["Orange"]), ("pink", ["Pink"]), ("purple", ["Purple"]),
    ("violet", ["Violet"]), ("lavender", ["LightLavender"]), ("white", ["White"]), ("black", ["Black"]),
    ("gray", ["25", "Gray"]), ("grey", ["25", "Gray"]), ("silver", ["25"]),
    ("stone", ["25", "Charcoal"]), ("charcoal", ["Charcoal"]),
]


def palette_hint(prompt):
    """Ten mau bang goi y tu prompt; None neu prompt noi qua it mau (dung ca bang)."""
    import re
    t = " " + (prompt or "").lower() + " "
    got = []
    for word, cols in HINTS:
        if re.search(r"[^a-z]" + word + r"[^a-z]", t) or (word in ("wood", "gold") and word in t):
            got += [c for c in cols if c not in got]
    if len(got) < 3:
        return None
    for c in ("White", "Black"):              # mat, vien, muc trang luon can
        if c not in got:
            got.append(c)
    return got


def estimate(body, kind):
    if str(body.get("model", "")).startswith("P"):
        return 35 if kind == "text" else 45     # web hien 35 cho P1 Fast co mau; anh: uoc chung
    base = COST[kind][1 if body.get("texture") else 0]
    add = 10 * bool(body.get("smart_low_poly")) + 5 * bool(body.get("quad")) + 20 * bool(body.get("generate_parts"))
    return base + add


def create(body, kind):
    path = "/generation/text-to-model" if kind == "text" else "/generation/image-to-model"
    return _call("POST", path, body=body)["task_id"]


def wait(task_id, timeout=900, interval=3):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        d = _call("GET", "/tasks/" + task_id)
        st, pr = d.get("status"), d.get("progress", 0)
        if (st, pr) != last:
            print("[tripo] %s %s%%" % (st, pr), flush=True)
            last = (st, pr)
        if st == "success":
            return d
        if st in ("failed", "banned", "expired", "cancelled"):
            raise SystemExit("[tripo] task %s ket thuc: %s" % (task_id, st))
        time.sleep(interval)
    raise SystemExit("[tripo] qua %ds chua xong - chay lai: run.py tripo --task %s" % (timeout, task_id))


def download(url, stem):
    os.makedirs(INBOX, exist_ok=True)
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".glb"
    dest = os.path.join(INBOX, stem + ext)
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as fh:
        fh.write(r.read())
    return dest


def balance():
    return _call("GET", "/account/balance")
