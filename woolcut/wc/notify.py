"""Gui anh qua TELEGRAM khi hang doi tach xong mot muc (2026-10-07, nguoi dung: "khi tach xong 1 anh thi gui anh model
tach 6 mat, anh parts_ids_all qua telegram cho toi").

Bot token + chat id nam o Preferences cua addon (tab Cai dat), truyen cho tien trinh nen qua bien moi truong
WOOLCUT_TG_TOKEN / WOOLCUT_TG_CHAT - khong ghi ra file. Chi dung thu vien chuan. Gui loi thi in ly do, KHONG lam hong
viec tach."""
import os, json, uuid, mimetypes, urllib.request, urllib.error

API = "https://api.telegram.org/bot%s/%s"
MAX_PHOTO = 10 * 2 ** 20          # Telegram: anh <= 10 MB (to hon thi gui dang file)


def config():
    return os.environ.get("WOOLCUT_TG_TOKEN", "").strip(), os.environ.get("WOOLCUT_TG_CHAT", "").strip()


def _call(token, method, fields=None, files=None, timeout=60):
    """POST multipart/form-data -> (ok, ket qua / ly do)."""
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in (fields or {}).items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode("utf-8")
    for k, path in (files or {}).items():
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            data = fh.read()
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                 % (boundary, k, os.path.basename(path), ctype)).encode("utf-8") + data + b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(API % (token, method), data=body, method="POST",
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read().decode("utf-8"))
        except ValueError:
            return False, "HTTP %s" % e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, str(e)
    return bool(res.get("ok")), res.get("result") if res.get("ok") else res.get("description", res)


def send_text(text, token=None, chat=None, timeout=60):
    token, chat = token or config()[0], chat or config()[1]
    if not token or not chat:
        return False, "chua co bot token / chat id"
    return _call(token, "sendMessage", {"chat_id": chat, "text": text[:4000]}, timeout=timeout)


def send_photos(paths, caption="", token=None, chat=None):
    """Mot album (toi da 10 anh), chu thich o anh dau. Anh > 10 MB gui dang file."""
    token, chat = token or config()[0], chat or config()[1]
    if not token or not chat:
        return False, "chua co bot token / chat id"
    paths = [p for p in paths if p and os.path.exists(p)][:10]
    if not paths:
        return send_text(caption, token, chat) if caption else (False, "khong co anh")
    big = [p for p in paths if os.path.getsize(p) > MAX_PHOTO]
    small = [p for p in paths if p not in big]
    ok, msg = True, ""
    if len(small) == 1:
        ok, msg = _call(token, "sendPhoto", {"chat_id": chat, "caption": caption[:1000]}, {"photo": small[0]})
    elif small:
        media = [dict(type="photo", media="attach://p%d" % i, **({"caption": caption[:1000]} if i == 0 else {}))
                 for i in range(len(small))]
        ok, msg = _call(token, "sendMediaGroup", {"chat_id": chat, "media": json.dumps(media, ensure_ascii=False)},
                        {"p%d" % i: p for i, p in enumerate(small)}, timeout=120)
    for p in big:
        ok2, msg2 = _call(token, "sendDocument", {"chat_id": chat, "caption": caption[:1000] if not small else ""},
                          {"document": p}, timeout=120)
        ok, msg = ok and ok2, msg2 if not ok2 else msg
    return ok, msg


def find_chat(token, timeout=15):
    """Chat id cua tin nhan moi nhat gui cho bot (nguoi dung nhan /start cho bot truoc) -> (chat id, ten) hoac None."""
    ok, res = _call(token, "getUpdates", {"limit": "20"}, timeout=timeout)
    if not ok or not isinstance(res, list):
        return None
    for u in reversed(res):
        m = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
        c = m.get("chat") or {}
        if c.get("id"):
            return str(c["id"]), c.get("title") or c.get("first_name") or c.get("username") or ""
    return None
