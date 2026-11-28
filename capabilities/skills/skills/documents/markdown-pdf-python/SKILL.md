---
name: markdown-pdf-python
description: Use when converting Markdown notes to PDF on Ubuntu with already installed Python tools, or evaluating PDF dependencies without installing anything.
---

# Markdown → PDF avec Python sans installation

## Vérifier l'environnement réel

Respecter toute interdiction d'installation : ne lancer ni apt install, ni pip install, ni npm install, ni npx, ni téléchargement de binaire. Les consultations de métadonnées et simulations restent possibles si autorisées.

Vérifier les versions et les imports dans le Python qui exécutera le convertisseur :

```sh
python3 - <<'PY'
import importlib
for name in ('fitz', 'reportlab', 'markdown', 'mistune', 'weasyprint', 'fpdf', 'xhtml2pdf', 'markdown_pdf'):
    try:
        m = importlib.import_module(name)
        print(name, 'présent', getattr(m, '__version__', getattr(m, 'Version', '')))
    except ImportError:
        print(name, 'absent')
import fitz
print(fitz.version)
print('Story disponible:', hasattr(fitz, 'Story'))
PY
fc-match -f '%{file}\n' 'DejaVu Sans'
fc-match -f '%{file}\n' 'DejaVu Sans Mono'
```

Lors de l'essai du 11 novembre 2026, PyMuPDF 1.27.2.3 et ReportLab 4.5.1 étaient présents. Les autres modules ci-dessus étaient absents. Revérifier ces faits avant réutilisation.

## Construire et contrôler la chaîne

1. Travailler dans un sous-dossier de session. L'essai de référence a produit `md2html.py`, `html2pdf_story.py`, `verify_pdf.py` et `run.sh` dans `/user/Lucas/workspace/e2e/scratch/python/`. Vérifier leur présence avant de les réutiliser.
2. Sans parseur Markdown installé, limiter explicitement le convertisseur maison aux constructions testées : titres ATX, paragraphes, listes, tableaux GFM, citations, blocs de code clôturés et éléments inline. Échapper le texte avec `html.escape`. Ne pas annoncer une compatibilité Markdown générale.
3. Produire un HTML intermédiaire inspectable, puis utiliser `fitz.Story` avec une archive de polices locales. Vérifier les signatures de la version installée avant d'appeler les méthodes d'écriture :

```sh
python3 - <<'PY'
import fitz, inspect
for name in ('__init__', 'write_with_links', 'write_stabilized_with_links'):
    print(name, inspect.signature(getattr(fitz.Story, name)))
PY
```

4. Pour une page A4 avec marges de 52 points, la fonction de placement testée était :

```python
def rectfn(num, filled):
    page = fitz.paper_rect('a4')
    return page, page + (52, 52, -52, -52), None
```

5. Utiliser l'écriture avec liens lorsque le document contient des liens. Sous-ensembler les polices et compresser le PDF avec `subset_fonts()` puis `save(..., deflate=True, garbage=4)` lorsque ces opérations conviennent au document retourné.
6. Relire le PDF avec `fitz.open`. Contrôler nombre de pages, texte extrait, accents, liens et positions des cellules. Pour un alignement à droite, comparer les coordonnées `x1` des mots. Ajouter un document de plusieurs pages et des lignes de code longues aux essais.

## Éviter la perte silencieuse du code

Avec la configuration A4 testée, un bloc `<pre>` en police monospace de 9 points perdait du texte au-delà d'environ 88 caractères par ligne. Ce seuil dépend de la police et de la largeur disponible : le mesurer, ne pas le traiter comme une constante universelle.

Replier les longues lignes en Python avant l'échappement HTML, avec `textwrap`, en conservant l'indentation. Tester aussi un long chemin sans espaces. Ne pas se fier à `white-space: pre-wrap` sans preuve sur le PDF obtenu.

Comparer le code source au texte extrait après normalisation des espaces pour détecter les caractères perdus. Cette comparaison ne vérifie pas la conservation de l'indentation : la contrôler séparément. Un vérificateur contenant les chaînes attendues d'une fixture doit recevoir cette fixture ; ses échecs sur un autre document ne prouvent pas un défaut du rendu.

Les essais ont également constaté que `float` et `display:flex` ne produisaient pas la disposition demandée. Vérifier les coordonnées ou le rendu visuel ; l'absence d'exception ne prouve pas le support CSS.

## Évaluer des dépendances sans installation

Consulter les versions :

```sh
pip index versions markdown
pip index versions weasyprint
pip index versions markdown-pdf
apt-cache policy libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
apt-get install --simulate libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

Lire `https://pypi.org/pypi/<paquet>/json` avec `urllib.request` pour consulter `requires_python`, `requires_dist` et les tailles des distributions. Tenir compte de l'architecture et distinguer taille des wheels, dépendances manquantes et espace installé ; une somme de wheels ne mesure pas l'espace disque final. Vérifier les exigences système de la version étudiée dans sa documentation officielle.

Lors de l'essai, Pango et Cairo étaient déjà présents. Les métadonnées de `markdown-pdf` révélaient une dépendance à PyMuPDF : ne pas présenter cet emballage comme un moteur de rendu indépendant.

## Vérifier la reproductibilité

Générer plusieurs PDF et comparer leurs octets. Lors de l'essai, certaines sorties différaient uniquement par le champ `/ID` du trailer. Pour diagnostiquer ce cas, comparer aussi les octets après neutralisation de `/ID` dans des copies en mémoire. Ne pas conclure à une reproductibilité octet pour octet sur deux sorties identiques seulement.
