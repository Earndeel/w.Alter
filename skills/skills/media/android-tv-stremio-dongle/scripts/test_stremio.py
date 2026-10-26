"""Tests locaux de stremio.py (aucun appareil requis) : python3 -I test_stremio.py [dossier de stremio.py]"""
import os, sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))
import stremio as S

def st(title, url=True, size="0.5 GB"):
    s = {"name": "[TB+] Torrentio\n1080p", "title": f"{title}\n💾 {size}"}
    if url: s["url"] = "https://x.example/secret-key/file.mkv"
    return s

ok = 0
def check(cond, msg):
    global ok
    assert cond, msg; ok += 1

# VOSTFR rejeté pour une VF, même avec le drapeau de l'addon
_, i = S.score(st("Show.S01E01.DSR.XviD-0TV.vostfr.avi 🇫🇷"), lang="fr", runtime_minutes=22)
check("VOSTFR : audio original" in i["rejected"], i["rejected"])
# MULTi.VFi accepté
p_multi, i = S.score(st("Show.S01E01.MULTi.VFi.1080p.HDLight.AC3.2.0.H265-GRP"), lang="fr", runtime_minutes=22)
check(not i["rejected"], i["rejected"])
# VF seule devant MULTi à qualité égale
p_fr, i = S.score(st("Show.S01E01.TRUEFRENCH.1080p.WEB.H265-GRP"), lang="fr", runtime_minutes=22)
check(p_fr > p_multi, (p_fr, p_multi))
# VO inchangée : un doublage seul reste rejeté
_, i = S.score(st("Film.2020.TRUEFRENCH.1080p.H265"), lang="vo", runtime_minutes=100)
check("doublage français seul" in i["rejected"], i)
# MULTI VOSTFR avec VFF reste admis
_, i = S.score(st("Film.2020.MULTi.VFF.VOSTFR.1080p.H265"), lang="fr", runtime_minutes=100)
check(not i["rejected"], i["rejected"])

A = lambda idx, lang, title="": {"index": idx, "codec_type": "audio", "tags": {"language": lang, "title": title}}
V = {"index": 0, "codec_type": "video"}
v = S.audio_verdict([V, A(1, "fre", "FR VFi"), A(2, "eng", "ENG VO")], "fr", "eng", "MULTi.VFi")
check(v.startswith("VF présente (piste #1), mais"), v)
v = S.audio_verdict([V, {"index": 1, "codec_type": "audio"}], "fr", "eng", "Show S01E01 FRENCH DVDRiP")
check(v.startswith("VF OK"), v)
v = S.audio_verdict([V, {"index": 1, "codec_type": "audio"}], "fr", "eng", "Show S01E01 VOSTFR")
check(v.startswith("VF NON PROUVÉE"), v)
v = S.audio_verdict([V, A(1, "eng"), A(2, "spa")], "fr", "eng", "MULTi")
check(v.startswith("VF ABSENTE"), v)
v = S.audio_verdict([V, A(1, "fra"), A(2, "jpn")], "fr", "eng", "MULTi")
check("INCERTAIN" in v, v)
fr_def = dict(A(1, "fra"), disposition={"default": 1})
v = S.audio_verdict([V, fr_def, A(2, "jpn")], "fr", "eng", "MULTi")
check("NON GARANTI" in v, v)
v = S.audio_verdict([V, A(1, "fre"), A(2, "eng")], "fr", "fre", "MULTi")
check("conforme à la langue du profil" in v, v)
check(S.mask("Error https://torbox.app/dl?token=abc: 403") == "Error <url> 403", S.mask("Error https://torbox.app/dl?token=abc: 403"))
check(S.is_french("fre") and S.is_french("FR VFi : AC3") and not S.is_french("ENG VO"), "is_french")
v = S.audio_verdict([V, A(1, "fre"), A(2, "eng")], "fr", "eng", "MULTi", {"id": "0:2", "language": "fr"})
check("déjà retenu le français" in v, v)
core = {"streams": '{"uid":"u","items":[[{"metaId":"tt1","videoId":"tt1:1:2"},{"state":{"audioTrack":{"id":"0:2","language":"fr"}}}]]}'}
check(S.saved_track(core, "tt1", "tt1:1:2")["language"] == "fr", "saved ep")
check(S.saved_track(core, "tt1", "tt1:1:3")["language"] == "fr", "saved series fallback")
check(S.saved_track(core, "tt9", "tt9") is None, "none")
print(f"{ok} tests OK")
