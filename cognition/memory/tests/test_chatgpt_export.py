"""ChatGPT export connector: pure parsing (no database)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "chatgpt_export", Path(__file__).resolve().parent.parent / "connectors" / "chatgpt_export.py")
cx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cx)


def node(nid, parent, role=None, ctype="text", parts=None, t=None, **extra):
    msg = None if role is None else {"id": nid, "author": {"role": role}, "create_time": t,
                                     "content": {"content_type": ctype, "parts": parts or []},
                                     "metadata": extra.pop("metadata", {}), **extra}
    return nid, {"id": nid, "parent": parent, "message": msg, "children": []}


def conv(nodes, current, **kw):
    return {"conversation_id": "c1", "title": "Titre", "create_time": 1_780_000_000, "current_node": current,
            "mapping": dict(nodes), "default_model_slug": "gpt-6-thinking", **kw}


def test_branch_visible_only():
    c = conv([node("root", None),
              node("sys", "root", "system", parts=["context"], metadata={"is_visually_hidden_from_conversation": True}),
              node("u1", "sys", "user", parts=["Bonjour"], t=1_780_000_001),
              node("th", "u1", "assistant", "thoughts", t=1_780_000_002),
              node("rr", "th", "assistant", "reasoning_recap", t=1_780_000_003),
              node("tc", "rr", "assistant", "code", parts=["search('x')"], recipient="web"),
              node("tl", "tc", "tool", parts=["résultat"]),
              node("a_old", "tl", "assistant", parts=["ancienne réponse"], t=1_780_000_004),
              node("a1", "tl", "assistant", parts=["Salut"], t=1_780_000_005, metadata={"model_slug": "gpt-6"})],
             current="a1")
    evs = cx.parse_conversation(c)
    assert [e["event_type"] for e in evs] == ["conversation.started", "message.sent", "message.received"]
    assert evs[1]["content"] == "Bonjour" and evs[1]["source_id"] == "msg:u1"
    assert evs[2]["content"] == "Salut" and evs[2]["reply_to"] == "msg:u1"
    assert evs[2]["payload"]["model"] == "gpt-6"
    assert all(e["thread_id"] == "c1" and e["source"] == "chatgpt" for e in evs)


def test_voice_and_attachments():
    c = conv([node("root", None),
              node("u1", "root", "user", "multimodal_text", t=1_780_000_001,
                   parts=[{"content_type": "audio_transcription", "text": "dicté"},
                          {"content_type": "audio_asset_pointer", "asset_pointer": "sediment://file_abc"}]),
              node("u2", "u1", "user", "multimodal_text", t=1_780_000_002,
                   parts=[{"content_type": "image_asset_pointer", "asset_pointer": "file-service://file_img"}],
                   metadata={"attachments": [{"id": "file_img", "name": "photo.jpg", "mime_type": "image/jpeg"}]})],
             current="u2")
    evs = cx.parse_conversation(c, {"file_abc": "file_abc.dat"})
    voice, image = evs[1], evs[2]
    assert voice["content"] == "dicté" and voice["payload"]["message_type"] == "voice"
    assert voice["payload"]["attachments"][0]["in_export"] is True
    assert image["content"] == "[photo.jpg]" and len(image["payload"]["attachments"]) == 1
    assert all(a["in_export"] is False for a in image["payload"]["attachments"])


def test_do_not_remember_and_empty_skipped():
    assert cx.parse_conversation(conv([node("root", None), node("u1", "root", "user", parts=["x"], t=1)],
                                      current="u1", is_do_not_remember=True)) == []
    assert cx.parse_conversation(conv([node("root", None)], current="root")) == []
