"""Self-check for telegram_inbox with a faked Telegram API. Run: python3 test_telegram_inbox.py"""
import os
import tempfile
from pathlib import Path

import telegram_inbox as t

msg = lambda uid, chat, text, **kw: {"update_id": uid, "message": {"message_id": uid * 10, "chat": {"id": chat}, "text": text, **kw}}
pending = [
    msg(1, 42, "apply here https://jobs.lever.co/x/1, and https://a.com/b."),
    msg(2, 99, "https://evil.com"),  # someone else's chat: ignored
    msg(3, 42, "https://old.com/job"),  # already in links.txt
    msg(4, 42, "Senior role", entities=[{"type": "text_link", "url": "https://hidden.com/j"}]),
    msg(5, 42, "no link here"),  # kept in the group
]
calls, deleted = [], []


def fake_api(token, method, timeout=0, offset=0, chat_id=None, message_id=None):
    if method == "deleteMessage":
        if message_id == 30:
            raise t.urllib.error.HTTPError("", 400, "message can't be deleted", {}, None)
        return deleted.append(message_id)
    calls.append(offset)
    return [u for u in pending if u["update_id"] >= offset][:2]  # 2 per page to exercise paging


with tempfile.TemporaryDirectory() as d:
    t.HERE, t.LINKS = Path(d), Path(d) / "links.txt"  # HERE: never read the real .env
    t.LINKS.write_text("https://old.com/job")  # no trailing newline
    t._api = fake_api
    os.environ.update(TELEGRAM_BOT_TOKEN="x", TELEGRAM_CHAT_ID="42")
    assert t.sync() == ["https://jobs.lever.co/x/1", "https://a.com/b", "https://hidden.com/j"]
    assert t.LINKS.read_text().splitlines() == ["https://old.com/job", "https://jobs.lever.co/x/1", "https://a.com/b", "https://hidden.com/j"]
    assert calls == [0, 3, 5, 6], calls  # last call confirms everything up to update 5
    assert deleted == [10, 40], deleted  # 30 failed to delete and was skipped; 20 is not our chat, 50 had no link
    os.environ["TELEGRAM_BOT_TOKEN"] = ""
    assert t.sync() == []  # not set up: no-op
print("ok")
