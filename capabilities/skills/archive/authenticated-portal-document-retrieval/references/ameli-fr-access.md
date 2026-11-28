# Ameli.fr Access Notes (French health insurance portal)

Session 2026-08-08 : tentative d'accès depuis l'infra basée en Thaïlande. Pipeline cookies complet monté, puis blocage réseau identifié.

## Statut : GEO-BLOQUÉ depuis les IP hors France (confirmé)

- `assure.ameli.fr` (espace assuré) : refus de connexion **TCP** sur :443 depuis tous les egress testés. DNS résout bien (93.174.145.36) ; `curl -sv` montre "Connection refused". C'est un géoblocage réseau dur, pas un challenge anti-bot.
- `www.ameli.fr` : 301 → `www.ameli.fr` → **403** pour les clients de type curl (pas de fingerprint navigateur complet). Un vrai navigateur passerait peut-être, non vérifié de bout en bout.
- Egress testés : Mac IP résidentielle thaïlandaise (58.11.189.182, exit node Tailscale), VPS Oracle Singapour (129.150.52.60 → ipinfo: SG), conteneur webtop (route via l'exit node du Mac).
- Aucun egress français dans l'infra au moment du test : nœuds Tailscale = w-alter (VPS) + lucass-macbook-pro-15 (Mac). Aucune clé VPN dans le vault.

## Pré-flight : vérifier la reachabilité AVANT tout travail cookies

Pour tout portail administratif français, dérouler ce diagnostic depuis chaque egress candidat (hôte + conteneur) avant extraction/injection de cookies :

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://assure.ameli.fr/
curl -sv --max-time 12 https://assure.ameli.fr/ -o /dev/null 2>&1 | tail -25
# DNS résolu + "Connection refused" ⇒ géoblocage ; abandonner le pipeline cookies.
curl -s --max-time 8 ifconfig.me   # confirmer l'IP de sortie
```

Test internet de contrôle : `curl -s -o /dev/null -w "%{http_code}" https://www.google.com` doit donner 200 — sinon le souci est local, pas le portail.

## Structure observée (cookies Brave, Mac)

- Domaines : `www.ameli.fr`, `assure.ameli.fr`, `ameliconnect.ameli.fr`
- Cookies d'auth (assure.ameli.fr) : `ASpersist`, `JSESSIONID`, `_WL_AUTHCOOKIE_JSESSIONID`, `mod_auth_openidc_session` (session OIDC)
- `www.ameli.fr` : `ameli_espace`
- Stack anti-bot Akamai : cookies `TS0*`/`TS1*`/`TS4*`/`TSa*`, `BIGipServer*`, `cookie_trust*` **fingerprint-bound — ne jamais les injecter cross-browser** (même règle que cf_clearance). Filtrer par préfixe au décryptage.

## Pipeline qui a fonctionné (jusqu'au réseau)

- Extraction/décryptage : pipeline Brave Mac standard (vault `macos/brave_keychain_key`, PBKDF2-HMAC-SHA1 saltysalt, skip 16 premiers octets) — 22 cookies décryptés, 5 candidats d'auth.
- Cible d'injection vivante ce jour-là : **Brave-in-webtop CDP 9224** (port conteneur ; lancer playwright dans le conteneur, pas depuis l'hôte). Camoufox 9378 était down.
- Injection : `context.add_cookies()` puis `page.goto` — les 7 cookies injectés passaient, le réseau a bloqué.
- Filtre d'injection utilisé : exclure les préfixes `TS0/TS1/TS4/TSa`, `BIGip`, `cookie_trust`, `ktlv`, `iav_`, `pmg4`, `hbc` + les analytics standard.

## Ce qui débloquerait

1. Monsieur active un VPN français existant sur le Mac → les cookies de session peuvent rester valides une fenêtre courte ; relancer extract → inject → navigate.
2. Provisionner un VPS français (OVH/Scaleway/Hetzner FR) comme egress → chantier infra, approbation requise (sensibilité coûts).
3. FranceConnect ne contourne PAS le géoblocage (même chemin réseau).