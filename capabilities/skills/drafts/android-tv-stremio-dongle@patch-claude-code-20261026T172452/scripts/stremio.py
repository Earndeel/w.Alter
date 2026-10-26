#!/usr/bin/env python3
"""Cherche un film ou une série, interroge tes addons Stremio, choisit la meilleure source pour le
dongle D6 et la lance directement dans le lecteur de Stremio. Aucune navigation dans l'interface.

  python3 stremio.py "dune deuxieme partie"            film, lance la meilleure source
  python3 stremio.py "the office" --s 2 --e 3          épisode d'une série
  python3 stremio.py "alien" --year 1979 --list        montre le classement sans rien lancer
  python3 stremio.py "alien" --pick 3                  lance la 3e source du classement
  python3 stremio.py "south park" --s 12 --e 6 --open  ouvre la fiche, l'utilisateur choisit la source
  python3 stremio.py --on / --off                     allume ou éteint la télé
  python3 stremio.py "alien" --pick 2 --probe          pistes audio réelles de la 2e source, sans lancer
  python3 stremio.py "alien" --match "GRP" --probe     même chose en désignant la release par son nom
  python3 stremio.py "alien" --state                   lecture en cours + piste audio retenue par Stremio
  options : --lang fr (VF explicite), --lang vo (défaut), --original-lang CODE, --host IP
  Qualité automatique : meilleure résolution admissible; --4k est conservé par compatibilité.

Le dongle ne se met jamais en veille profonde (verrou noyau) : quand la télé est éteinte, il reste
joignable écran éteint. Le lancer d'un film réveille son écran, ce qui allume la télé par HDMI-CEC,
puis s'assure que le serveur de Stremio tourne (sinon pas de sous-titres) avant d'ouvrir le lecteur.

Les adresses des addons (avec ta clé TorBox) sont lues sur le dongle à chaque lancement et ne sont
jamais affichées ni écrites sur le disque.
"""
import argparse, base64, json, os, re, shutil, subprocess, sys, time, unicodedata, zlib
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

CINEMETA = "https://v3-cinemeta.strem.io"
STREMIO_PKG = "com.stremio.one"
# Comme URI_COMPONENT_ENCODE_SET dans stremio-core : tout sauf A-Z a-z 0-9 - _ . ! ~ * ' ( )
SAFE = "-_.!~*'()"
# Par ssh non interactif, le PATH du Mac n'inclut pas Homebrew : adb et ffprobe y sont pourtant.
os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), "/usr/local/bin", "/opt/homebrew/bin"])
FRENCH_CODES = {"fr", "fre", "fra", "french", "francais"}


def adb(host, *args, check=True):
    r = subprocess.run(["adb", "-s", f"{host}:5555", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"adb a échoué : {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def get_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def read_core(host):
    """L'état de Stremio sur le dongle (root nécessaire) : profil (addons, réglages) et `streams`."""
    xml = adb(host, "shell", "su", "-c", f"'cat /data/data/{STREMIO_PKG}/shared_prefs/core.xml'")
    return {e.get("name"): e.text for e in ET.fromstring(xml)}


def read_profile(host):
    return json.loads(read_core(host)["profile"])


def read_addons(host):
    """Les addons installés, lus dans le profil de Stremio sur le dongle."""
    return read_profile(host)["addons"]


def stream_addons(addons, kind, imdb_id):
    out = []
    for a in addons:
        m = a.get("manifest", {})
        res = m.get("resources", [])
        has_stream = any(r == "stream" or (isinstance(r, dict) and r.get("name") == "stream") for r in res)
        prefixes = m.get("idPrefixes") or next(
            (r.get("idPrefixes") for r in res if isinstance(r, dict) and r.get("name") == "stream"), None)
        local = a["transportUrl"].startswith(("http://127.0.0.1", "http://localhost"))  # injoignable depuis le Mac
        if has_stream and not local and kind in m.get("types", []) and (
                not prefixes or any(imdb_id.startswith(p) for p in prefixes)):
            out.append((m.get("name", "?"), a["transportUrl"]))
    return out


def search(query, kind, year):
    q = urllib.parse.quote(query)
    metas = get_json(f"{CINEMETA}/catalog/{kind}/top/search={q}.json").get("metas", [])
    if year:
        metas = [m for m in metas if str(year) in str(m.get("releaseInfo", ""))] or metas
    if not metas:
        sys.exit(f"Rien trouvé pour « {query} ».")
    # Titre exact d'abord, sinon l'ordre de Cinemeta (popularité).
    exact = [m for m in metas if norm(m["name"]) == norm(query)]
    return (exact or metas)[0], metas[:5]


def fetch_streams(addons, kind, video_id):
    def one(addon):
        name, transport = addon
        base = transport.rsplit("/manifest.json", 1)[0]
        try:
            streams = get_json(f"{base}/stream/{kind}/{urllib.parse.quote(video_id)}.json", timeout=12).get("streams", [])
        except Exception as e:
            return name, transport, [], type(e).__name__
        return name, transport, streams, None

    with ThreadPoolExecutor(len(addons) or 1) as ex:
        return list(ex.map(one, addons))


def legacy_score(s, want_4k, lang, year=None):
    text = f"{s.get('name', '')}\n{s.get('title', '')}\n{s.get('description', '')}"
    t = text.lower()
    info = {"cached": False, "res": "?", "size_gb": None, "seeds": None, "flags": []}
    pts = 0
    years = set(re.findall(r"\b(19[2-9]\d|20[0-4]\d)\b", t))
    if year and years and year not in years:
        info["flags"].append("ANNÉE?")
        pts -= 40                                   # fichier d'un autre film (pack, suite...)
    if s.get("url") and re.search(r"\[(tb|rd|ad|pm|dl)\+\]|⚡|\[tb⚡\]|cached", t):
        info["cached"], pts = True, pts + 100
    elif s.get("url"):
        pts += 60                                   # lien direct HTTP non marqué en cache
    elif s.get("infoHash"):
        m = re.search(r"👤\s*(\d+)", text)
        info["seeds"] = int(m.group(1)) if m else 0
        pts += min(info["seeds"], 60) / 2          # pair-à-pair : dépend des sources
    res = re.search(r"\b(2160p|4k|1080p|720p|480p)\b", t)
    info["res"] = {"4k": "2160p"}.get(res.group(1), res.group(1)) if res else "?"
    pts += {"2160p": 50 if want_4k else 25, "1080p": 45, "720p": 25, "480p": 5}.get(info["res"], 10)
    m = re.search(r"💾\s*([\d.]+)\s*(gb|mb)", t) or re.search(r"\b([\d.]+)\s*(gb|mb)\b", t)
    if m:
        info["size_gb"] = float(m.group(1)) / (1024 if m.group(2) == "mb" else 1)
        if info["size_gb"] > 25:
            pts -= 40                               # débit trop fort pour la puce et le Wi-Fi
    for flag, rx, malus in (("HDR", r"\bhdr|hdr10", 40), ("DV", r"\bdv\b|dolby ?vision", 60),
                            ("REMUX", r"remux", 30), ("AV1", r"\bav1\b", 200), ("3D", r"\b3d\b", 50)):
        if re.search(rx, t):
            info["flags"].append(flag)
            pts -= malus                            # pas de HDR ni d'AV1 sur cette puce
    if re.search(r"x265|hevc|h\.?265", t):
        info["flags"].append("HEVC")
        pts += 5
    if lang == "fr" and re.search(r"\bvff\b|\bvf2?\b|truefrench|\bfrench\b|\bmulti\b|🇫🇷", t):
        info["flags"].append("FR")
        pts += 30
    return pts, info


def score(s, want_4k=False, lang="vo", year=None, runtime_minutes=None, original_lang=None):
    """Filtrer avant de classer. Les limites de débit sont prudentes, pas un benchmark du Wi-Fi."""
    text = "\n".join(str(s.get(k, "")) for k in ("name", "title", "description"))
    t = text.lower()
    _, info = legacy_score(s, want_4k, lang, None)
    rejected = []
    info["rejected"] = rejected
    original_lang = (original_lang or "").lower()
    years = set(re.findall(r"\b(?:19[2-9]\d|20[0-4]\d)\b", t))
    if year and years and str(year) not in years:
        rejected.append("mauvaise année")
    if not (s.get("url") or s.get("infoHash")):
        rejected.append("pas de flux lisible")
    for flag in ("HDR", "DV", "AV1", "3D", "REMUX"):
        if flag in info["flags"]:
            rejected.append(flag)
    if re.search(r"\b(?:cam|hdcam|hdts|telesync|telecine|screener|8k|4320p)\b", t):
        rejected.append("qualité ou format inadapté")

    # MULTI ne garantit aucune langue : c'est une piste à vérifier dans le lecteur.
    french_tag = bool(re.search(r"\b(?:vff|vfi|vf2?|truefrench|french|francais|vfq)\b", t))
    french = french_tag or "🇫🇷" in t
    multi = bool(re.search(r"\bmulti\b|dual[ ._-]*audio", t))
    vo = bool(re.search(r"\b(?:vo|vost|vostfr|vosten|original)\b", t))
    vostfr = bool(re.search(r"\b(?:vostfr|subfrench|stfr)\b", t))
    if lang == "fr":
        if not (french or multi or original_lang == "fr"):
            rejected.append("VF non indiquée")
        # VOSTFR = audio original + sous-titres français ; le drapeau 🇫🇷 de l'addon ne fait pas une VF.
        if vostfr and not multi and not re.search(r"\b(?:vff|vfi|vf2?|truefrench|vfq)\b", t):
            rejected.append("VOSTFR : audio original")
        info["audio"] = "VF indiquée" if french else "VF à vérifier"
    else:
        if french and not (multi or vo or original_lang == "fr"):
            rejected.append("doublage français seul")
        info["audio"] = "VO à vérifier"
        # Une VO n'est pas forcément anglaise. --lang en reste une demande explicite.
        if lang == "en" and not (re.search(r"\b(?:english|eng)\b|🇬🇧|🇺🇸", t) or multi or original_lang == "en"):
            rejected.append("audio anglais non indiqué")

    size = (s.get("behaviorHints") or {}).get("videoSize")
    if isinstance(size, (int, float)) and size > 0:
        info["size_gb"] = size / 1_000_000_000
    else:
        m = re.search(r"([\d]+(?:[.,]\d+)?)\s*(gib|gb|go|mib|mb|mo)\b", t)
        if m:
            amount = float(m.group(1).replace(",", "."))
            unit = m.group(2)
            info["size_gb"] = amount * {"gib": 1.073741824, "gb": 1, "go": 1,
                                           "mib": .001048576, "mb": .001, "mo": .001}[unit]
    bitrate = None
    if runtime_minutes and info["size_gb"]:
        bitrate = info["size_gb"] * 8000 / (runtime_minutes * 60)
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mbps|mb/s|kbps)\b", t)
        if m:
            bitrate = float(m.group(1).replace(",", ".")) / (1000 if m.group(2) == "kbps" else 1)
    info["bitrate_mbps"] = bitrate
    # 12 Mb/s moyens : marge pour pointes, Wi-Fi et seulement 1 Go de RAM.
    # À relever seulement après un essai de lecture stable sur le dongle.
    if bitrate is not None and bitrate > 12:
        rejected.append("débit moyen > 12 Mb/s")
    if bitrate is None and info["size_gb"] and info["size_gb"] > 8:
        rejected.append("fichier > 8 Go sans débit connu")
    if info["res"] == "2160p":
        if "HEVC" not in info["flags"] or bitrate is None or not s.get("url"):
            rejected.append("4K sans HEVC, débit connu ou lien direct")
    if s.get("infoHash") and not s.get("url") and (info["seeds"] or 0) < 10:
        rejected.append("P2P insuffisamment disponible")

    # La meilleure résolution admissible prime; à qualité égale, cache et HEVC.
    pts = {"2160p": 400, "1080p": 300, "720p": 200, "480p": 100}.get(info["res"], 50)
    pts += 30 if info["cached"] else (15 if s.get("url") else 0)
    pts += 5 if "HEVC" in info["flags"] else 0
    pts += 3 if (lang == "fr" and french) or (lang == "vo" and vo) else 0
    # VF seule : joue en français sans bascule (le profil Stremio préfère l'anglais sur une MULTi).
    pts += 4 if lang == "fr" and french_tag and not multi else 0
    if bitrate is None:
        pts -= 10
        info["flags"].append("DÉBIT?")
    return pts, info


def get_runtime(meta, kind, season=None, episode=None):
    """Ne pas appliquer la durée d'un film ou d'un pack à un épisode."""
    value = meta.get("runtime")
    if kind == "series":
        videos = meta.get("videos") or []
        video = next((v for v in videos if v.get("season") == season and v.get("episode") == episode), {})
        value = video.get("runtime") or value
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:min(?:utes?)?)?\s*", str(value or ""), re.I)
    return float(m.group(1)) if m and float(m.group(1)) > 0 else None


def reachable(host):
    subprocess.run(["adb", "connect", f"{host}:5555"], capture_output=True, timeout=10)
    r = subprocess.run(["adb", "-s", f"{host}:5555", "shell", "echo", "ok"], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() == "ok"


def keep_awake(host):
    # Verrou noyau : l'écran du dongle peut s'éteindre, mais pas son Wi-Fi (perdu au redémarrage,
    # d'où sa repose à chaque lancement).
    adb(host, "shell", "su", "-c", "'echo stremio_remote > /sys/power/wake_lock'", check=False)


def screen_on(host):
    return "mWakefulness=Awake" in adb(host, "shell", "dumpsys", "power", check=False)


def tv_on(host):
    """Le dongle réveillé envoie <Image View On> et <Active Source> en HDMI-CEC : la télé s'allume
    et passe sur son entrée. Écran du dongle éteint = télé éteinte (elle lui envoie <Standby>)."""
    if not reachable(host):
        sys.exit("Dongle injoignable : il a dû redémarrer puis se mettre en veille profonde. "
                 "Allume-le une fois avec sa télécommande, le script repose ensuite le verrou.")
    keep_awake(host)
    if not screen_on(host):
        print("   allumage de la télé…")
        adb(host, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(4)


CECSEND = "/data/local/tmp/cecsend"


def cec(host, *octets):
    """Message CEC brut vers la télé (adresse 0) avec cecsend, compilé depuis cecsend.c."""
    if "cecsend" not in adb(host, "shell", "ls", CECSEND, check=False):
        local = __file__.rsplit("/", 1)[0] + "/cecsend"
        adb(host, "push", local, CECSEND)
        adb(host, "shell", "chmod", "755", CECSEND)
    return adb(host, "shell", "su", "-c", f"'{CECSEND} 0 {' '.join(octets)}'", check=False)


def tv_off(host):
    if reachable(host):
        keep_awake(host)
        # <Standby> adressé à la télé : obéi même sur l'accueil VIDAA, contrairement à la diffusion
        # qu'envoie le dongle en se mettant en veille.
        cec(host, "36")
        adb(host, "shell", "input", "keyevent", "KEYCODE_SLEEP")


def server_up(host):
    # Le serveur local de Stremio (port 11470 du dongle), joint par une redirection adb vers 11471.
    adb(host, "forward", "tcp:11471", "tcp:11470", check=False)
    try:
        urllib.request.urlopen("http://127.0.0.1:11471/settings", timeout=2).close()
        return True
    except Exception:
        return False


def ensure_server(host, timeout=45):
    """Les sous-titres passent par le serveur local de Stremio, qui ne démarre pas quand l'appli
    s'ouvre directement sur le lecteur. Ouvrir l'accueil de Stremio le démarre (~15 s à froid)."""
    if server_up(host):
        return True
    print("   serveur Stremio arrêté : ouverture de Stremio pour le démarrer…")
    adb(host, "shell", "monkey", "-p", STREMIO_PKG, "-c", "android.intent.category.LEANBACK_LAUNCHER", "1", check=False)
    for _ in range(timeout):
        time.sleep(1)
        if server_up(host):
            return True
    print("   le serveur de sous-titres n'a pas démarré")
    return False


def mask(text):
    """Les liens debrid et les adresses d'addons contiennent les clés : jamais affichés."""
    return re.sub(r"\b[a-z][a-z0-9+.-]*://\S+", "<url>", str(text), flags=re.I)


def is_french(code_or_title):
    words = set(norm(code_or_title or "").split())
    return bool(words & (FRENCH_CODES | {"vf", "vff", "vfi", "vfq", "vf2", "truefrench"}))


def probe_tracks(url, timeout=90):
    """Pistes réelles du fichier par ffprobe (sur l'hôte qui exécute le script, pas le dongle)."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None, "ffprobe introuvable sur cet hôte (Mac : /usr/local/bin/ffprobe)"
    try:
        r = subprocess.run([exe, "-v", "error", "-show_entries",
                            "stream=index,codec_type,codec_name,channels,width,height:stream_tags=language,title"
                            ":stream_disposition=default", "-of", "json", url],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"ffprobe sans réponse après {timeout} s (source lente ou non mise en cache)"
    if r.returncode != 0:
        return None, "ffprobe a échoué : " + mask(r.stderr.strip())[:300]
    return json.loads(r.stdout or "{}").get("streams", []), None


def saved_state(core, meta_id, video_id):
    """État de lecture que Stremio a retenu pour ce titre (épisode, sinon série) : pistes, décalages."""
    items = json.loads(core.get("streams") or "{}").get("items", [])
    hit = next((v for k, v in items if k.get("videoId") == video_id), None) or \
        next((v for k, v in items if k.get("metaId") == meta_id), None)
    return (hit or {}).get("state") or {}


def saved_track(core, meta_id, video_id):
    """Piste audio que Stremio a retenue pour ce titre, ou None."""
    return saved_state(core, meta_id, video_id).get("audioTrack")


def audio_verdict(tracks, lang, preferred, release_text, saved=None):
    """Ce que le lecteur jouera, d'après les pistes, la piste retenue pour ce titre et le profil."""
    audio = [t for t in tracks if t.get("codec_type") == "audio"]
    if not audio:
        return "aucune piste audio détectée"
    tag = lambda t: (t.get("tags") or {})
    fr = [t for t in audio if is_french(tag(t).get("language")) or is_french(tag(t).get("title"))]
    pref = [t for t in audio if (tag(t).get("language") or "").lower() == (preferred or "").lower()]
    if lang != "fr":
        return (f"{len(audio)} piste(s) audio ; le lecteur prendra « {preferred} » si elle existe"
                + ("" if pref else ", sinon la piste par défaut du fichier") + ". Vérifier la VO.")
    if len(audio) == 1:
        if fr or re.search(r"\b(?:vff|vfi|vf2?|truefrench|french|vfq)\b", release_text.lower()):
            return "VF OK : une seule piste audio, release française. Rien à basculer."
        return "VF NON PROUVÉE : une seule piste, sans étiquette française. Choisir une autre source."
    if not fr:
        return "VF ABSENTE : aucune piste étiquetée français. Choisir une autre source."
    if saved and is_french(saved.get("language")):
        return (f"VF présente (piste #{fr[0]['index']}) ; Stremio a déjà retenu le français pour ce titre "
                "et devrait le reprendre. Contrôler avec --state après le lancement.")
    if pref:
        if pref[0] in fr:
            return (f"VF présente (piste #{pref[0]['index']}) et conforme à la langue du profil : "
                    "le lecteur devrait la prendre. Contrôler avec --state.")
        return (f"VF présente (piste #{fr[0]['index']}), mais le profil Stremio préfère « {preferred} » : "
                "le lecteur devrait démarrer sur cette langue. Basculer l'audio en français dans le lecteur "
                "(skill, « Getting French audio »), puis contrôler avec --state.")
    default = [t for t in audio if (t.get("disposition") or {}).get("default")]
    if len(default) == 1 and default[0] in fr:
        return (f"VF présente (piste #{fr[0]['index']}, piste par défaut du fichier) ; aucune piste dans la "
                f"langue du profil (« {preferred} ») : le lecteur devrait prendre la VF, NON GARANTI. "
                "Contrôler après lancement (menu audio ou --state).")
    return (f"VF présente (piste #{fr[0]['index']}), mais rien n'établit la piste que le lecteur prendra "
            "(pas de piste dans la langue du profil, défaut du fichier absent ou non français) : INCERTAIN. "
            "Basculer en français dans le lecteur si besoin, puis contrôler.")


def print_probe(stream, lang, preferred, saved=None):
    text = "\n".join(str(stream.get(k, "")) for k in ("name", "title", "description"))
    if not stream.get("url"):
        print("   source pair-à-pair (sans lien direct) : pistes non sondables avant lancement")
        return
    tracks, err = probe_tracks(stream["url"])
    if err:
        print("   " + err)
        return
    for t in tracks:
        tags, kind = t.get("tags") or {}, t.get("codec_type")
        if kind == "video":
            print(f"   vidéo #{t['index']}  {t.get('codec_name')}  {t.get('width')}x{t.get('height')}")
        elif kind == "audio":
            default = " défaut" if (t.get("disposition") or {}).get("default") else ""
            print(f"   audio #{t['index']}  {t.get('codec_name')}  {t.get('channels')}ch  "
                  f"langue={tags.get('language', '?')}  titre={mask(tags.get('title', '-'))}{default}")
    print("   → " + audio_verdict(tracks, lang, preferred, text, saved))


def print_state(host, meta_id, video_id):
    """Lecture en cours (media session) et piste audio retenue par Stremio pour ce titre."""
    out = adb(host, "shell", "dumpsys", "media_session", check=False)
    block = out.split(f"package={STREMIO_PKG}", 1)[1][:1500] if f"package={STREMIO_PKG}" in out else ""
    m = re.search(r"state=PlaybackState \{state=(\d+), position=(\d+)", block)
    d = re.search(r"description=([^\n]*)", block)
    names = {"0": "aucun", "1": "arrêté", "2": "en pause", "3": "en lecture", "6": "chargement", "7": "erreur"}
    if m:
        print(f"   lecteur : {names.get(m.group(1), m.group(1))}, position {int(m.group(2)) // 1000} s"
              + (f", « {d.group(1).strip()} »" if d else ""))
    else:
        print("   lecteur : aucune session Stremio active")
    print("   (relancer --state après quelques secondes : la position doit avancer)")
    core = read_core(host)
    state = saved_state(core, meta_id, video_id)
    track, sub = state.get("audioTrack"), state.get("subtitleTrack")
    settings = json.loads(core["profile"]).get("settings", {})
    if track:
        print(f"   piste audio retenue pour ce titre : {track.get('language')} (id {track.get('id')})")
    else:
        print(f"   aucune piste audio retenue pour ce titre : le lecteur suit le profil "
              f"(« {settings.get('audioLanguage')} »)")
    if sub:
        print(f"   sous-titres retenus pour ce titre : {sub.get('language') or '?'} (id {mask(sub.get('id'))})")
    else:
        print(f"   aucun sous-titre retenu pour ce titre : profil « {settings.get('subtitlesLanguage')} », "
              f"sélection auto {'oui' if settings.get('subtitlesAutoSelect') else 'non'}")
    print("   sous-titres anglais : à confirmer à l'écran (capture), --state ne le prouve pas")


def release_label(stream, addon=""):
    lines = (stream.get("title") or stream.get("description") or "").splitlines()
    return mask(lines[0] if lines else addon)


def choose(ranked, pick, match):
    """La source à sonder ou lancer : par son nom (--match, stable d'un appel à l'autre) sinon par rang."""
    if match:
        want = norm(match)
        hits = [i for i, r in enumerate(ranked) if want in norm(
            "\n".join(str(r[4].get(k, "")) for k in ("name", "title", "description")))]
        if not hits:
            sys.exit(f"Aucune source admissible ne contient « {match} ». Aucun lancement.")
        return hits[0] + 1
    if not 1 <= pick <= len(ranked):
        sys.exit("Numéro de source hors classement.")
    return pick


def player_link(stream, stream_transport, meta_transport, kind, meta_id, video_id):
    # stremio-core Stream::encode : JSON -> zlib -> base64 standard, puis encodage URI composant.
    enc = base64.b64encode(zlib.compress(json.dumps(stream, separators=(",", ":")).encode())).decode()
    parts = [enc, stream_transport, meta_transport, kind, meta_id, video_id]
    return "stremio:///player/" + "/".join(urllib.parse.quote(p, safe=SAFE) for p in parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--on", action="store_true", help="allumer la télé (sans lancer de film)")
    ap.add_argument("--off", action="store_true", help="éteindre la télé")
    ap.add_argument("--year", type=int)
    ap.add_argument("--s", type=int, help="saison (série)")
    ap.add_argument("--e", type=int, help="épisode (série)")
    ap.add_argument("--4k", dest="want_4k", action="store_true")
    ap.add_argument("--lang", choices=("vo", "fr", "en"), default="vo",
                    help="VO par défaut; fr pour une demande VF explicite")
    ap.add_argument("--original-lang", help="langue originale ISO connue (VO ne signifie pas anglais)")
    ap.add_argument("--list", action="store_true", help="classer sans lancer")
    ap.add_argument("--open", action="store_true", help="ouvrir la fiche dans Stremio sans lancer de source")
    ap.add_argument("--pick", type=int, default=1)
    ap.add_argument("--match", help="choisir la première source admissible dont le libellé contient ce texte "
                                    "(nom de release), au lieu d'un rang qui peut changer entre deux appels")
    ap.add_argument("--probe", action="store_true",
                    help="sonder les pistes audio réelles de la source --pick, sans rien lancer")
    ap.add_argument("--state", action="store_true",
                    help="lecture en cours et piste audio retenue par Stremio pour ce titre")
    ap.add_argument("--host", default="192.168.1.37")
    a = ap.parse_args()

    if a.off:
        return tv_off(a.host)
    if a.on or not a.query:
        return tv_on(a.host)
    kind = "series" if a.s else "movie"
    inspect = a.list or a.probe or a.state
    if not inspect:
        tv_on(a.host)
    elif not reachable(a.host):
        sys.exit("Dongle injoignable.")
    meta, others = search(a.query, kind, a.year)
    video_id = f"{meta['id']}:{a.s}:{a.e or 1}" if kind == "series" else meta["id"]
    print(f"→ {meta['name']} ({meta.get('releaseInfo', '?')})  [{meta['id']}]")
    if len(others) > 1:
        print("   autres : " + " · ".join(f"{m['name']} ({m.get('releaseInfo', '?')})" for m in others[1:4]))
    if a.state:
        return print_state(a.host, meta["id"], video_id)
    if a.open:
        q = lambda s: urllib.parse.quote(s, safe=SAFE)
        link = f"stremio:///detail/{kind}/{q(meta['id'])}/{q(video_id)}"
        adb(a.host, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"'{link}'", STREMIO_PKG)
        print("▶ fiche ouverte dans Stremio")
        return

    try:
        details = get_json(f"{CINEMETA}/meta/{kind}/{meta['id']}.json").get("meta", {})
    except Exception:
        details = {}
    runtime = get_runtime(details, kind, a.s, a.e or 1)
    core = read_core(a.host)
    profile = json.loads(core["profile"])
    addons = stream_addons(profile["addons"], kind, meta["id"])
    results = fetch_streams(addons, kind, video_id)
    year = re.match(r"\d{4}", str(meta.get("releaseInfo", ""))) if kind == "movie" else None
    ranked = []
    for name, transport, streams, err in results:
        print(f"   {name:28} {'erreur ' + err if err else str(len(streams)) + ' sources'}")
        for s in streams:
            pts, info = score(s, a.want_4k, a.lang, year.group(0) if year else None,
                              runtime, a.original_lang)
            if not info["rejected"]:
                ranked.append((pts, info, name, transport, s))
    ranked.sort(key=lambda r: -r[0])
    if not ranked:
        sys.exit("Aucune source adaptée au matériel et à la langue demandée. Aucun lancement.")

    for i, (pts, info, name, _, s) in enumerate(ranked[:10], 1):
        size = f"{info['size_gb']:.1f} Go" if info["size_gb"] else "? Go"
        how = "cache" if info["cached"] else (f"P2P {info['seeds']}👤" if info["seeds"] is not None else "direct")
        lines = (s.get("title") or s.get("description") or "").splitlines()
        first = lines[0][:60] if lines else ""
        print(f"{i:>3}. {pts:>5.0f}  {info['res']:>6} {size:>8}  {how:10} {','.join(info['flags']):14} {name[:16]:16} {first}")
    if a.list:
        return

    a.pick = choose(ranked, a.pick, a.match)
    pts, info, name, transport, stream = ranked[a.pick - 1]
    if a.probe:
        print(f"? sonde n°{a.pick} : {release_label(stream, name)[:90]}")
        return print_probe(stream, a.lang, profile.get("settings", {}).get("audioLanguage"),
                           saved_track(core, meta["id"], video_id))
    link = player_link(stream, transport, f"{CINEMETA}/manifest.json", kind, meta["id"], video_id)
    if not ensure_server(a.host):
        sys.exit("Serveur de sous-titres indisponible : lecture interrompue, à réparer.")
    out = adb(a.host, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"'{link}'", STREMIO_PKG)
    print(f"▶ lancement demandé : n°{a.pick} {release_label(stream, name)[:90]} "
          f"({name}, {info['res']}, {info['audio']}). "
          "Contrôler la lecture et la piste audio avec --state (mêmes arguments), "
          "puis vérifier les sous-titres anglais à l'écran."
          if "Error" not in out else "Stremio a refusé le lancement.")


if __name__ == "__main__":
    main()

