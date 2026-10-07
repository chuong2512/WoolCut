"""TU HOC tu model tot (2026-10-07, nguoi dung: "tool tu hoc tu model tot").

Model XUAT FBX THAT (khong phai ban nhap hang doi) ma bang cham diem dat >= MIN_SCORE, hoac nguoi dung bam
"Mau tot" o buoc 4, duoc ghi vao data/good_models.json kem prompt da tao ra no + so do. Buoc 1 (prompt.brief) dua
toi da 3 prompt tot nhat CUNG DANG + CUNG KIEU (anh / text) cho Claude lam vi du - cang lam nhieu, prompt cang sat
gu nguoi dung. Khong can bpy."""
import os, json, re, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = os.path.join(HERE, "data", "good_models.json")
MIN_SCORE = 85


def _load():
    try:
        with open(GOOD, encoding="utf-8") as fh:
            rows = json.load(fh)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _save(rows):
    os.makedirs(os.path.dirname(GOOD), exist_ok=True)
    tmp = GOOD + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, GOOD)


def mode_of(prompt):
    """Prompt text-to-3D ket bang "Decor:" (prompt.BRIEF); prompt anh ket bang "Details:" (IMAGE_BRIEF)."""
    return "text" if re.search(r"\bDecor:", prompt or "") else "image"


def record(name, res, prompt="", kind="char", mode=None, manual=False):
    """Ghi / cap nhat mot model tot. res = ket qua wc/score.measure (co the None khi nguoi dung tu danh dau)."""
    res = res or {}
    rows = [r for r in _load() if r.get("name") != name]
    rows.append(dict(name=name, kind=kind, mode=mode or mode_of(prompt), prompt=(prompt or "").strip(),
                     score=res.get("score"), grade=res.get("grade"), counts=res.get("counts", {}), manual=bool(manual),
                     when=time.strftime("%Y-%m-%d %H:%M")))
    _save(rows)
    return rows[-1]


def remove(name):
    rows = _load()
    keep = [r for r in rows if r.get("name") != name]
    if len(keep) != len(rows):
        _save(keep)
    return len(rows) - len(keep)


def get(name):
    return next((r for r in _load() if r.get("name") == name), None)


def good_names():
    return {r.get("name") for r in _load()}


def examples(kind, mode, k=3):
    """Prompt cua model tot cung dang + kieu: nguoi dung danh dau truoc, roi diem cao, roi moi nhat."""
    rows = [r for r in _load() if r.get("prompt") and r.get("kind") == kind and r.get("mode") == mode
            and (r.get("manual") or (r.get("score") or 0) >= MIN_SCORE)]
    rows.sort(key=lambda r: (bool(r.get("manual")), r.get("score") or 0, r.get("when", "")), reverse=True)
    return rows[:k]


def count(kind=None):
    return sum(1 for r in _load() if kind is None or r.get("kind") == kind)
