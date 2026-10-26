#!/usr/bin/env python3
"""Cherche un film ou une série, interroge tes addons Stremio, choisit la meilleure source pour le
dongle D6 et la lance directement dans le lecteur de Stremio. Aucune navigation dans l'interface.
Adresse du dongle : --host, sinon DONGLE_HOST, sinon le fichier ~/.config/stremio-remote/host.

  python3 stremio.py "dune deuxieme partie"            film, lance la meilleure source
  python3 stremio.py "the office" --s 2 --e 3          épisode d'une série
  python3 stremio.py "alien" --year 1979 --list        montre le classement sans rien lancer
  python3 stremio.py "alien" --pick 3                  lance la 3e source du classement
  python3 stremio.py "south park" --s 12 --e 6 --open  ouvre la fiche, l'utilisateur choisit la source
  python3 stremio.py --on / --off                     allume ou éteint la télé
  options : --4k (préférer la 4K SDR), --lang en (au lieu du français), --host IP

Le dongle ne se met jamais en veille profonde (verrou noyau) : quand la télé est éteinte, il reste
joignable écran éteint. Le lancer d'un film réveille son écran, ce qui allume la télé par HDMI-CEC,
puis s'assure que le serveur de Stremio tourne (sinon pas de sous-titres) avant d'ouvrir le lecteur.

Les adresses des addons (avec ta clé TorBox) sont lues sur le dongle à chaque lancement et ne sont
jamais affichées ni écrites sur le disque.
"""
import argparse, base64, json, os, re, subprocess, sys, time, unicodedata, zlib
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

CINEMETA = "https://v3-cinemeta.strem.io"
STREMIO_PKG = "com.stremio.one"
# Comme URI_COMPONENT_ENCODE_SET dans stremio-core : tout sauf A-Z a-z 0-9 - _ . ! ~ * ' ( )
SAFE = "-_.!~*'()"


def default_host():
    if os.environ.get("DONGLE_HOST"):
        return os.environ["DONGLE_HOST"]
    try:
        return open(os.path.expanduser("~/.config/stremio-remote/host")).read().strip() or None
    except OSError:
        return None


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


def read_addons(host):
    """Les addons installés, lus dans le profil de Stremio sur le dongle (root nécessaire)."""
    xml = adb(host, "shell", "su", "-c", f"'cat /data/data/{STREMIO_PKG}/shared_prefs/core.xml'")
    root = ET.fromstring(xml)
    profile = json.loads(next(e.text for e in root if e.get("name") == "profile"))
    return profile["addons"]


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


def score(s, want_4k, lang, year=None):
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
    print("   le serveur n'a pas démarré : lecture sans sous-titres")
    return False


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
    ap.add_argument("--lang", default="fr")
    ap.add_argument("--list", action="store_true", help="classer sans lancer")
    ap.add_argument("--open", action="store_true", help="ouvrir la fiche dans Stremio sans lancer de source")
    ap.add_argument("--pick", type=int, default=1)
    ap.add_argument("--host", default=default_host(), help="IP du dongle (DONGLE_HOST ou ~/.config/stremio-remote/host)")
    a = ap.parse_args()
    if not a.host:
        sys.exit("Adresse du dongle inconnue : --host IP, DONGLE_HOST=IP ou ~/.config/stremio-remote/host.\n"
                 "Pour la trouver : dns-sd -B _adb._tcp (macOS) puis résoudre le nom, ou la liste DHCP de la box.")

    if a.off:
        return tv_off(a.host)
    if a.on or not a.query:
        return tv_on(a.host)
    kind = "series" if a.s else "movie"
    if not a.list:
        tv_on(a.host)
    elif not reachable(a.host):
        sys.exit("Dongle injoignable.")
    meta, others = search(a.query, kind, a.year)
    video_id = f"{meta['id']}:{a.s}:{a.e or 1}" if kind == "series" else meta["id"]
    print(f"→ {meta['name']} ({meta.get('releaseInfo', '?')})  [{meta['id']}]")
    if len(others) > 1:
        print("   autres : " + " · ".join(f"{m['name']} ({m.get('releaseInfo', '?')})" for m in others[1:4]))
    if a.open:
        q = lambda s: urllib.parse.quote(s, safe=SAFE)
        link = f"stremio:///detail/{kind}/{q(meta['id'])}/{q(video_id)}"
        adb(a.host, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"'{link}'", STREMIO_PKG)
        print("▶ fiche ouverte dans Stremio")
        return

    addons = stream_addons(read_addons(a.host), kind, meta["id"])
    results = fetch_streams(addons, kind, video_id)
    year = re.match(r"\d{4}", str(meta.get("releaseInfo", ""))) if kind == "movie" else None
    ranked = []
    for name, transport, streams, err in results:
        print(f"   {name:28} {'erreur ' + err if err else str(len(streams)) + ' sources'}")
        for s in streams:
            pts, info = score(s, a.want_4k, a.lang, year.group(0) if year else None)
            ranked.append((pts, info, name, transport, s))
    ranked.sort(key=lambda r: -r[0])
    if not ranked:
        sys.exit("Aucune source trouvée.")

    for i, (pts, info, name, _, s) in enumerate(ranked[:10], 1):
        size = f"{info['size_gb']:.1f} Go" if info["size_gb"] else "? Go"
        how = "cache" if info["cached"] else (f"P2P {info['seeds']}👤" if info["seeds"] is not None else "direct")
        first = (s.get("title") or s.get("description") or "").splitlines()[0][:60]
        print(f"{i:>3}. {pts:>5.0f}  {info['res']:>6} {size:>8}  {how:10} {','.join(info['flags']):14} {name[:16]:16} {first}")
    if a.list:
        return

    pts, info, name, transport, stream = ranked[a.pick - 1]
    link = player_link(stream, transport, f"{CINEMETA}/manifest.json", kind, meta["id"], video_id)
    ensure_server(a.host)
    out = adb(a.host, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"'{link}'", STREMIO_PKG)
    print(f"▶ lancé : n°{a.pick} ({name}, {info['res']})" if "Error" not in out else out)


if __name__ == "__main__":
    main()
