---
name: annas-archive-download
description: Use when downloading an ebook from Anna's Archive.
---

# Anna's Archive — téléchargement d'ebook

## Domaines (vérifié 2026-09-18)
- Officiels : `annas-archive.gl` (principal), `.pk`, `.gd`. Le `.org` a été saisi (janv. 2026), le `.pm` est un parking pub, `.gs/.li/.se` morts.
- Vérifier le domaine courant sur la page Wikipedia EN d'Anna's Archive (liens externes) si le .gl échoue.

## Pipeline éprouvé
1. **Search** : `GET /search?index=&q=<query>&display=table` — résultats dans des `<tr>` avec `href="/md5/<md5>"`.
2. **DDoS-Guard** : le domaine est derrière DDoS-Guard (403 + challenge JS). curl et Camoufox headless échouent. Passer par **scrapling `stealthy_fetch`** (MCP) avec `network_idle=true`, `wait>=25000`, `timeout=180000` — le challenge passe et rend du HTML complet.
3. **Page md5** : `/md5/<md5>` → liste des serveurs. Pour le gratuit, utiliser les **Slow Partner Servers** (`/slow_download/<md5>/0/<n>`).
4. **Lien direct** : la page slow_download affiche un compte à rebours (~30 s) puis une URL `http://<ip>:6060/...` en clair dans la page (aussi dans le handler `navigator.clipboard.writeText`). Refetch après `wait=45000`.
5. **Download** : `curl --globoff -o out.epub "<url>"` — le path contient un `~` ; sans `--globoff`, curl développe le glob et échoue. Vérifier avec `file` (attendu : "EPUB document") et `unzip -l` (mimetype présent).

## Pièges
- `~` dans l'URL du lien direct = glob shell → toujours `--globoff`.
- Fast Partner Servers = membres payants uniquement.
- Miroirs non officiels en secours : open-slum.org, shadowlibraries.github.io.
