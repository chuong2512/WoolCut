"""Buoc 1: huong dan gui Claude CLI viet prompt Tripo (TIENG ANH - bam quy tac chat hon; chi hai dong
VI / WHY tra ve tieng Viet co dau de nguoi dung duyet). Khong can bpy - addon va run.py cung dung.

Kieu prompt = kieu 5 prompt web nguoi dung da duyet (2026-10-01): con vat chibi lam MOT viec, it khoi to,
moi khoi MOT mau phang, khoi cham nhau khac mau -> buoc 3 tach theo mau + hinh khoi sach se."""
import re

STYLE_TAIL = ("Cute stylized toy figure, chunky rounded shapes, smooth surfaces, few large parts, each part one "
              "flat solid color, touching parts in contrasting colors, no text, no fine texture detail")

COLOR_WORDS = ("pink, sky blue, blue, yellow, lemon yellow, green, dark green, cream, beige, brown, red, crimson, "
               "orange, purple, violet, white, black, gray, turquoise mint")

IDEA_GIVEN = ('Write ONE English prompt for Tripo AI (text-to-3D) based on the user\'s idea (may be in Vietnamese): '
              '"%s"')
IDEA_SELF = ("The user gave NO idea: INVENT one new model yourself - fun and cute, fitting the asset set (a chibi "
             "animal/character doing one specific activity, a food item, an object with personality...), then write "
             "an English prompt for Tripo AI (text-to-3D). The idea must be CLEARLY DIFFERENT from every existing and "
             "already-made model listed below; prefer themes not covered yet (jobs, sports, seasons/holidays, "
             "musical instruments, vehicles...).")

IDEA_SELF_OBJECT = ("The user gave NO idea: INVENT one new simple OBJECT yourself (a vehicle, a small building, an "
                    "appliance, furniture, a food item, a toy...) - no character, just one chunky cute object, then write "
                    "an English prompt for Tripo AI (text-to-3D). It must be CLEARLY DIFFERENT from every existing and "
                    "already-made model listed below.")

KIND_CHAR = {
    "examples": """- "A chubby golden hamster barista standing behind a small round wooden coffee counter, holding a big white
  coffee cup with both paws. Small black bead eyes, pink cheeks,
  tiny round ears, small green apron. A red coffee grinder on the counter. Everything on a thick round
  cream-colored base."
- "A round baby penguin fisherman sitting on a small white ice floe, holding a short brown fishing rod with a
  red float. Wears a yellow knit beanie with a pom-pom. A small blue bucket with one orange fish next to him.
  Black and white body, orange beak and feet." """,
    "rule": """- A chibi animal/character doing ONE thing, with 1-3 simple chunky props, usually on
  a thick round base.""",
}
# Kieu DO VAT don gian (nguoi dung 2026-10-02 gui anh xe bus mini bo tron: "tao promt don gian nhu xe bus nay")
KIND_OBJECT = {
    "examples": """- "A chunky retro minibus toy with a rounded boxy body and soft edges. Lower body orange, upper body and
  roof cream, a thick white rim around the roof. Big sky blue windows: one wide windshield and three side
  windows. Four big black tires with gray round hubcaps. Two round yellow headlights in white rings, a gray oval
  grille and thick gray bumpers front and back. Two chunky round red side mirrors on the front corners."
- "A chunky cute retro camera toy with a rounded box body. Black body with a cream top plate, a big gray round
  lens with a sky blue glass center, a red round shutter button and a small yellow flash box on top, two chunky
  brown strap loops on the sides." """,
    "rule": """- ONE simple chunky object (vehicle, small building, appliance, furniture, food, toy) - no character, no
  scene. 6-12 big parts, rounded boxy shapes with soft edges. Wheels, windows, lights, buttons, doors are
  separate raised chunky parts in contrasting colors. Vehicles need no base; small objects may sit on a thick
  round base. Avoid thin rods, antennas, wires, handles that are thinner than a finger of the model.""",
}

BRIEF = """%s

The model is for a 3D puzzle game ("Wooler") in a cute knitted-toy style. After generation a tool SPLITS the
model into parts with ONE COLOR PER PART (head, muzzle, ears, eyes, hat, clothing, arms, legs, each prop...);
the player unwinds colored wool from each part. So the model must read as a few large, clearly separated,
chunky rounded parts, each in one flat color, and parts that touch must have contrasting colors.
The tool can ONLY separate a part where it bulges out with a groove/neck around it OR has a different flat color
than its neighbour. A detail that is just sculpted relief in the same color (a face sunk inside a hood, belly
folds, fingers) can never be split, so it can never be painted - describe every part as its own raised volume
WITH its own color.
ASSEMBLED FROM MANY PIECES (user 2026-10-05: Tripo models came out too simple, body + seat + fenders fused into one
blob that cannot be split): describe the model like a toy ASSEMBLED from 12-20 separate chunky pieces, name each
piece and say how it sits on the others ("a separate cushion seat sitting ON TOP of the body with a visible groove",
"a front fender shell wrapping over the wheel", "a raised ring around the headlight", "the tire, rim and hub cap as
three stacked parts"). Use layering words: separate, sitting on, wrapped by, raised ring / rim / band / trim, stacked,
plugged into, with a groove between. Every part one flat color, neighbours contrasting. Small details are separate
raised knobs, never engraved or painted lines.
Tripo FUSES anything flush or recessed into the main body (boombox 2026-10-06: "separate speaker pods" came out as
two shallow dents in the body, the cassette door as a relief). So every sub-part must STICK OUT: "a thick round
speaker pod bulging out from the front", "a cassette door panel mounted on top of the front face", "a control strip
sitting on the top edge" - never inset, recessed, sunken, built-in, flush, engraved or "set into" the body.

Good examples (copy this style and length):
%s

Rules for the prompt:
- English, one paragraph, HARD LIMIT 720 characters - count them; name pieces tersely (Tripo cuts at 1024 incl. the ~260-char style sentence). Do NOT add the style sentence (cute stylized toy figure, chunky
  rounded shapes, flat colors...) - the tool appends it automatically.
%s
- Name a flat color for EVERY part, using only these words: %s.
  Touching parts get different colors (white arms on a red sweater - never white on white).
- DECOR (the original models carry small decoration pieces, split off as "D" pieces - a model without them looks
  bare): besides the main parts add %s, each group in one bold color that contrasts with the surface it sits on.
  Good decor for this type: %s.
  Every decor piece is a simple chunky raised shape (domed dot, button, star, heart, small flower, oval, stud),
  about 1/15-1/25 of the model height, spaced apart from its neighbours - never flat paint, never thin lines.
  Write ALL decor as the LAST sentence of the prompt, starting with "Decor:" (180-280 characters), naming each
  group with count + shape + color + where: "Decor: black bead eyes and pink blush ovals, a ring of eight white
  studs around the hat band, five raised yellow stars on the blue scarf, six small pink flowers scattered on the
  base top." A character's decor always includes its eyes and blush; the main-part sentences before it stay
  short so the decor sentence fits.
- Avoid: flat painted prints, thin stripes or lines, plaid, tiny patterns (they turn into noise when split -
  use raised decor shapes instead), thin fragile details, text or letters, logos, several characters, fur
  strands, realism.
- Existing models (108 original files) - do not repeat: %s.
- Already made with PrimForge - do not repeat either: %s.

Also choose the Tripo SETUP (credits are charged per generation):
- User's default: MODEL P1-20260311 (P1.0 Fast, clean low-poly "Smart Mesh"), TOPOLOGY tri, POLYCOUNT 8000.
  Models ASSEMBLED from 12+ pieces need more faces so grooves and small parts survive: POLYCOUNT 15000-20000
  (P1 max 20000); busy scenes 20000.
- P1-20260311: tri only, 50-20000. P2-20260801: tri 48-50000, quad 48-25000.
  v3.1-20260211 (H3.1, more detail): tri 500-20000, quad 500-10000 - only for complex organic shapes.

Use no tools. Reply with EXACTLY these 7 lines and nothing else:
NAME: <English PascalCase name, max 3 words>
PROMPT: <the English prompt>
VI: <1-2 câu tiếng Việt CÓ DẤU đầy đủ, mô tả prompt để người dùng duyệt>
MODEL: <P1-20260311 | P2-20260801 | v3.1-20260211>
TOPOLOGY: <tri | quad>
POLYCOUNT: <integer>
WHY: <1 câu tiếng Việt CÓ DẤU: vì sao chọn thiết lập này>"""

# ------------------------------------------------------------------ PROMPT ANH (Tripo web image-to-3D, 2026-10-07)
# Nguoi dung tao model tren web Tripo bang Image to 3D (Smart Mesh, P2.0, Quad, ~11k mat). Image-to-3D chep dung
# nhung gi anh ve: mang mot mau lon -> mot khoi khong tach duoc. So lieu tu 108 FBX goc (wc/sep.py TARGET).
# Cau khung anh noi vao khi copy (Claude khong tu viet khung / nen / anh sang -> prompt ngan, tap trung bo phan).
IMAGE_TAIL = ("Single subject, full body, centered, front three-quarter view from slightly above, plain light gray "
              "background, soft even studio lighting, no cast shadows, 3D clay toy render, smooth matte surfaces, "
              "chunky rounded shapes, every part a separate raised piece in one flat color with a visible seam, "
              "touching parts in contrasting colors, no text, no printed patterns, no fur texture")
IMAGE_LIMIT = 650

IMAGE_BRIEF = """%s

WORKFLOW: the user makes the model on the Tripo WEB site with IMAGE-to-3D. First a text-to-image tool draws ONE
concept image from your prompt, then Tripo turns that image into a 3D model. Then a tool SPLITS the model into
parts with ONE COLOR PER PART for a wool-unwinding puzzle game ("Wooler"). The tool can only split where the COLOR
changes or where a piece bulges out with a groove around it. Image-to-3D copies the image faithfully: a big area of
one color becomes one blob that cannot be split; every color change becomes a separate part.

WHAT THE 108 ORIGINAL GAME MODELS LOOK LIKE (measured, this type): about %d separate color parts (%d-%d), %d
colors, and the biggest single-color area covers only ~%d%% of the surface, plus %s small raised details.
- Characters are always DRESSED: a top with a contrasting collar and cuffs, a bottom, shoes, often gloves - the bare
  animal color is left only on the head, hands and feet. A lighter raised muzzle, belly patch and inner ears; a
  colored nose; a hat with a contrasting band; 1-2 accessories; a prop held AWAY from the body.
- Objects are layered: panels with contrasting trims and rims; wheels = tire + rim + hub cap; lights = ring + lens;
  straps, bows, buttons, knobs as separate raised pieces. Food sits in a bowl with a contrasting rim and base ring,
  toppings as separate chunks. Scenes sit on a thick base with a contrasting rim.
- Small RAISED details everywhere: buttons, pockets, patches, stitched flowers, stars, hearts, studs along rims.
%s
Write ONE English text-to-image prompt, one paragraph, HARD LIMIT %d characters (count them). The tool appends a
framing / style sentence itself - do NOT write the view, background, lighting or render style.
%s
- Name a flat color for EVERY part using only: %s. No two touching parts share a color. No single color covers
  more than about a quarter of the model.
- End with %s.
- Avoid: hoods or masks around the face, fur or knit texture, printed patterns, plaid, stripes, text, logos, thin
  rods, wires, fingers, several characters, a background scene, props hugged against the body.
- Existing models (108 original files) - do not repeat: %s.
- Already made - do not repeat either: %s.

Good examples (copy this style and length):
%s

Use no tools. Reply with EXACTLY these 4 lines and nothing else:
NAME: <English PascalCase name, max 3 words>
PROMPT: <the English image prompt>
VI: <1-2 câu tiếng Việt CÓ DẤU đầy đủ, mô tả prompt để người dùng duyệt>
CHECK: <3-5 điều tiếng Việt CÓ DẤU, ngăn bằng " · ", để người dùng soát trên ẢNH trước khi đưa lên 3D, riêng cho
model này (vd: "áo xanh tách khỏi thân nâu · khay bánh cầm xa thân · mũ có băng đỏ")>"""

# so luong decor / chi tiet theo DANG (categories.FORMATS "decor_amount", "image_details"): mac dinh = nhan vat
# (15-60 decor / model goc); cay don le chi 3-12 (2026-10-08)
DECOR_AMOUNT = "3-5 GROUPS of small RAISED decor shapes, 15-40 pieces in total"
IMAGE_DETAILS = 'a "Details:" clause naming 3-4 groups of small RAISED details with count, shape, color and where'

KEYS = ("NAME", "PROMPT", "VI", "MODEL", "TOPOLOGY", "POLYCOUNT", "WHY", "CHECK")


def brief(idea, have, made, previous="", kind="char", theme="free", mode="text"):
    """kind = DANG model (categories.FORMATS: char, object, food, scene, plant); theme = CHU DE (categories.THEMES).
    Vi du + luat theo dang; chu de kem danh sach model goc cung chu de (theo phong cach, khong lap y).
    mode="image": prompt TAO ANH cho Image to 3D tren web Tripo (IMAGE_BRIEF, so lieu bo goc wc/sep.py)."""
    from . import categories as cat
    f = cat.FORMATS.get(kind, cat.FORMATS["char"])
    th = cat.THEMES.get(theme, cat.THEMES["free"])
    what = ("an English text-to-image prompt (the image then goes to Tripo image-to-3D)" if mode == "image"
            else "an English prompt for Tripo AI (text-to-3D)")
    if idea.strip():
        head = ('Write %s based on the user\'s idea (may be in Vietnamese): "%s"' % (what, idea) if mode == "image"
                else IDEA_GIVEN % idea)
    else:
        head = ("The user gave NO idea: INVENT one new model yourself of the TYPE below, then write %s. It must be "
                "CLEARLY DIFFERENT from every existing and already-made model listed below." % what)
    if th["en"]:
        head += ("\nTHEME: %s. Original models of this theme (match their cute style, do NOT copy them): %s."
                 % (th["en"], ", ".join(th["models"])))
    if mode == "image":                  # luat dang nam trong IMAGE_BRIEF (image_rule) - khong lap luat text-to-3D
        head += "\nModel TYPE: %s. Original models of this type: %s." % (
            {"char": "chibi character", "scene": "small diorama"}.get(kind, kind), ", ".join(f["models"][:16]))
    else:
        head += "\nModel TYPE:\n%s\nOriginal models of this type: %s." % (f["rule"], ", ".join(f["models"][:16]))
    if previous and not idea.strip():
        head += " Previously suggested: '%s' - this time come up with a DIFFERENT idea." % previous[:160]
    if mode == "image":
        from . import sep
        g = sep.TARGET.get(kind, sep.TARGET["char"])
        ex = "\n".join('- "%s"' % e for e in f.get("image_examples") or f["examples"]) + own_examples(kind, mode)
        b = IMAGE_BRIEF % (head, g["parts"], g["parts_lo"], g["parts_hi"], g["colors"],
                           round(100 * g["largest"]), f.get("image_details_n", "20-60"),
                           f.get("image_look", ""), IMAGE_LIMIT, f.get("image_rule") or f["rule"],
                           COLOR_WORDS, f.get("image_details", IMAGE_DETAILS),
                           ", ".join(have) or "-", ", ".join(made) or "-", ex)
        if f.get("image_look"):                  # dang co phong cach rieng (cay: chi tiet THUA) -> bo dong "khap noi"
            b = b.replace("- Small RAISED details everywhere: buttons, pockets, patches, stitched flowers, stars, "
                          "hearts, studs along rims.\n", "")
        return b
    ex = "\n".join('- "%s"' % e for e in f["examples"]) + own_examples(kind, mode)
    return BRIEF % (head, ex, f["rule"], COLOR_WORDS, f.get("decor_amount", DECOR_AMOUNT),
                    f.get("decor", cat.DECOR_DEFAULT), ", ".join(have) or "-", ", ".join(made) or "-")


def own_examples(kind, mode):
    """Tu hoc (wc/learn.py): prompt cua model nguoi dung DA XUAT va dat bang cham diem -> them vao vi du."""
    try:
        from . import learn
        rows = learn.examples(kind, mode, 3)
    except Exception:
        return ""
    if not rows:
        return ""
    return ("\nThe user's OWN finished models that passed the game check (match their level of detail and color "
            "layering; do NOT copy their subject):\n" + "\n".join('- "%s"' % r["prompt"] for r in rows))


def find_prompt(model_path="", name="", work=""):
    """Prompt da tao model: <work>/prompt.txt (o "Prompt cua model" o panel - co file la theo file, ke ca rong)
    > <Ten>.tripo.json canh file model (buoc 2 cua tool ghi)."""
    import os, json
    if work:
        p = os.path.join(work, "prompt.txt")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    return fh.read().strip()
            except OSError:
                pass
    if not model_path:
        return ""
    d0 = os.path.dirname(model_path)
    base = re.sub(r"_[0-9a-f]{8}$", "", os.path.splitext(os.path.basename(model_path))[0])
    for c in (os.path.join(d0, "%s.tripo.json" % name), os.path.join(d0, "%s.tripo.json" % base)):
        if os.path.exists(c):
            try:
                with open(c, encoding="utf-8") as fh:
                    d = json.load(fh)
            except (OSError, ValueError):
                continue
            text = (d.get("request") or {}).get("prompt") or d.get("prompt") or d.get("PROMPT") or d.get("text")
            if text:
                return str(text).strip()
    return ""


def parse(lines):
    out = {}
    for ln in lines:
        t = ln.strip().strip("*").strip()
        for key in KEYS:
            if t.upper().startswith(key + ":"):
                out[key] = t.split(":", 1)[1].strip().strip('"').strip("`").strip()
    return out


def slug(text, fallback="Model"):
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    s = "".join(w[:1].upper() + w[1:] for w in words[:4])
    return s[:40] or fallback
