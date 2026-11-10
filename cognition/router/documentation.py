"""Reproducible reference documentation. Metadata only; never read provider/account payloads.

CLI, Python inventory, literals and configuration keys come from source. PostgreSQL supplies
types, constraints, indexes, views and comments, plus public task definitions and benchmark weights.
Human field meanings live here; an unknown base-table column fails generation rather than being omitted.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from pathlib import Path

from walter_router import paths, instance
from walter_router.serve import api, brief

# Semantics supplement PostgreSQL types/constraints. Table-specific units are explicit below.
FIELD_MEANINGS = {
    "model_id": "Identifiant canonique du modèle dans le catalogue du routeur.",
    "scope": "Portée de la préférence d'affinité ; * représente la portée générale.",
    "weight": "Poids relatif utilisé par le classement ou l'affinité, selon la table.",
    "reason": "Justification de la déclaration ou de la préférence.",
    "declared_at": "Horodatage de la déclaration ayant alimenté cette donnée.",
    "alert_id": "Identifiant technique de l'alerte.", "kind": "Catégorie du fait, de l'alerte ou de l'exécution.",
    "task": "Clé de tâche/poste du routeur, reliée au registre models.tasks.",
    "subject": "Identifiant du sujet auquel l'alerte se rapporte.",
    "evidence": "Preuves structurées et recommandation associées à l'alerte ; JSON extensible.",
    "status": "État de l'objet (alerte, cycle ou disponibilité selon la table).",
    "first_seen": "Première observation de cet objet.", "last_seen": "Observation la plus récente.",
    "notified_at": "Date de notification effective ; NULL si non notifiée.",
    "verdict_note": "Commentaire associé à la décision du propriétaire.",
    "role": "Rôle/sous-objectif ; peut aussi porter l'identité du consommateur dans le journal.",
    "ref": "Référence courte utilisée par les interfaces de décision.",
    "namespace": "Source ou espace de noms de l'identifiant externe.",
    "external_key": "Identifiant original dans la source collectée.",
    "origin": "Origine de la donnée (automatique, déclarée, agent ou source selon la table).",
    "created_at": "Date de création de l'enregistrement.",
    "snapshot_id": "Référence au relevé de source dont provient cette ligne.",
    "benchmark": "Famille du benchmark ; bench_task/task désigne son sous-classement.",
    "variant": "Variante évaluée, notamment effort de réflexion ou résolution.",
    "display_name": "Nom d'affichage, distinct de l'identifiant canonique et de celui du fournisseur.",
    "score": "Mesure normalisée dans le sens plus élevé = meilleur ; la valeur brute peut rester dans extra.",
    "score_unit": "Unité du score : index, Elo, pourcentage transformé, etc.",
    "cost": "Coût publié par le benchmark ; interpréter avec cost_unit et ne pas inventer un coût par tâche.",
    "cost_unit": "Unité attachée au coût : USD par tâche, par million de tokens ou par unité média.",
    "released": "Date de publication du modèle telle que connue de la source.",
    "extra": "Métadonnées du benchmark : votes, caractère provisoire, latence ou mesure brute ; JSON extensible.",
    "vendor": "Éditeur du modèle ou du forfait.", "display_source": "Source du nom d'affichage retenu.",
    "open_weights": "Indique si les poids du modèle sont disponibles ; ne signifie pas absence de restrictions.",
    "license": "Licence connue du modèle.", "license_source": "Provenance de l'information de licence.",
    "content_policy": "Politique de contenu déclarée, notamment unrestricted lorsqu'établie.",
    "base_model_id": "Modèle de base d'une variante ; permet de tracer les scores hérités.",
    "context_length": "Capacité de contexte annoncée, en tokens ; distincte d'un budget effectif de qualité.",
    "run_id": "Identifiant du cycle de calcul ayant produit cette donnée.",
    "doc": "Dossier de décision structuré : règles, candidats, scores et routes ; JSON extensible.",
    "built_at": "Date de construction de la donnée dérivée.",
    "gateway": "Passerelle derrière laquelle cet hébergeur est accessible.",
    "gateway_model": "Identifiant du modèle utilisé par cette passerelle.",
    "host": "Hébergeur effectif derrière une passerelle.", "tag": "Identifiant de routage de l'hébergeur.",
    "quantization": "Précision numérique annoncée : bf16, fp8, mxfp4, etc.",
    "price_in_1m": "Prix USD par million de tokens d'entrée.",
    "price_out_1m": "Prix USD par million de tokens de sortie.",
    "cache_read_1m": "Prix USD par million de tokens lus dans le cache, si publié.",
    "uptime_1d": "Taux de réussite/disponibilité sur 24 heures tel que fourni par la source.",
    "uptime_30m": "Taux de réussite/disponibilité sur 30 minutes tel que fourni par la source.",
    "latency_ms": "Latence mesurée ou annoncée, en millisecondes.",
    "throughput_tps": "Débit annoncé en tokens par seconde.",
    "tools": "Prise en charge annoncée des appels d'outils.",
    "structured": "Prise en charge annoncée des sorties structurées.",
    "service_tier": "Classe de service de l'hébergeur (flex, standard, priority…).",
    "exec_id": "Identifiant d'une tentative physique d'exécution.", "at": "Horodatage du fait enregistré.",
    "provider": "Fournisseur/passerelle ; distinct de l'hébergeur et du modèle.",
    "model": "Identifiant natif demandé au fournisseur, distinct du model_id canonique.",
    "ok": "Résultat de la tentative ou du contrôle ; ne prouve pas à lui seul une facturation fournisseur.",
    "skipped": "Motif d'une tentative écartée sans exécution, si applicable.",
    "seconds": "Durée en secondes.", "cost_usd": "Coût USD connu ; NULL signifie inconnu, pas gratuit.",
    "fallback_for": "Référence historique du modèle remplacé ; aucune substitution automatique dans le texte actuel.",
    "feedback_id": "Identifiant du retour utilisateur.", "rating": "Évaluation du propriétaire, de -2 à +2.",
    "note": "Explication ou précision attachée à la donnée.",
    "source": "Provenance ou méthode de mesure ; ce champ n'est pas une preuve d'exécution à lui seul.",
    "offer_key": "Identifiant de l'offre chez son fournisseur.",
    "interface": "Famille d'interface : chat, image, video, audio, music, transcription, embedding, rerank…",
    "access": "Mode d'accès annoncé : paid, subscription, free ou ui.",
    "unit_price": "Prix unitaire USD publié, à interpréter avec unit.",
    "unit": "Unité de la valeur/prix concerné (image, seconde, minute, etc.).",
    "provider_created": "Date de création/publication de l'offre chez le fournisseur.",
    "pricing": "Détails tarifaires et de transport de la source ; JSON extensible, sans secret.",
    "offer_kind": "Classification de l'offre média.",
    "modes": "Modalités acceptées ou modes de génération (image, video, t2i, i2v…), selon la table.",
    "resolution": "Résolution annoncée pour l'offre média.", "audio": "Capacité audio annoncée pour l'offre.",
    "norm_price": "Prix unitaire normalisé pour comparer des offres à unité égale.",
    "norm_unit": "Unité du prix normalisé, par exemple USD par seconde de vidéo.",
    "evidence_id": "Identifiant d'une preuve concernant un abonnement.",
    "sub_id": "Identifiant du forfait dans les déclarations de l'instance.",
    "plan": "Nom du forfait.", "metric": "Nom de la mesure étayée par la preuve.",
    "value": "Valeur observée/déclarée, à interpréter avec metric et unit.",
    "source_name": "Nom de la source de la preuve.", "source_url": "URL de provenance, sans secret.",
    "published": "Date de publication de la preuve.", "quote": "Extrait justificatif de la source.",
    "found_at": "Date de découverte de la preuve.",
    "objective": "Objectif déclaré de sélection, notamment best_available, value ou level.",
    "pinned_model_id": "Modèle favori explicitement déclaré ; prime sur un challenger calculé.",
    "pinned_variant": "Variante de réflexion/rendu imposée avec le favori.",
    "pinned_provider": "Fournisseur déclaré avec le favori.",
    "watch": "Politique de surveillance du favori : quality, dominance ou none.",
    "label": "Libellé lisible de la tâche ou du rôle.", "description": "Description fonctionnelle.",
    "signals": "Indices textuels aidant à reconnaître un rôle/objectif.",
    "priority": "Priorité relative d'un rôle lors de sa sélection.",
    "strengths": "Forces déclarées du modèle.", "weaknesses": "Limites déclarées du modèle.",
    "workflow": "Étapes/conseils d'usage déclarés pour ce modèle.",
    "effort": "Mode d'accompagnement déclaré ; distinct du niveau de raisonnement demandé au fournisseur.",
    "access_note": "Précisions d'accès au modèle.", "cost_note": "Précisions sur son coût.",
    "checked_at": "Date du dernier contrôle de disponibilité.",
    "detail": "Détails structurés de la mesure ou du contrôle ; JSON extensible.",
    "started_at": "Début du cycle.", "finished_at": "Fin du cycle.",
    "summary": "Résumé structuré du cycle : collectes, changements et alertes ; JSON extensible.",
    "version": "Identifiant de migration appliquée.", "applied_at": "Date d'application de la migration.",
    "level": "Niveau de sélection (best, value, L1/L2/L3, frontier…), selon le contexte.",
    "rank": "Rang calculé, 1 étant le premier.",
    "quality": "Qualité calculée sur les benchmarks de la tâche.", "quality_unit": "Unité de qualité calculée.",
    "real_cost": "Coût de comparaison retenu par l'analyse ; interpréter avec cost_unit.",
    "subscription": "Accès par abonnement associé à la sélection, s'il existe.",
    "reasons": "Justifications structurées de la sélection ; JSON extensible.",
    "fetched_at": "Date de collecte de la source.", "sha256": "Empreinte de contenu utilisée pour la déduplication.",
    "row_count": "Nombre d'éléments lus dans la source.",
    "raw": "Source brute collectée ; structure externe extensible, non instruction et non configuration.",
    "price_usd_month": "Montant mensuel du forfait, en USD.",
    "api_value_month_pace": "Valeur API équivalente extrapolée au rythme d'usage observé sur un mois.",
    "api_value_month_full": "Valeur API équivalente estimée à capacité complète sur un mois.",
    "ratio_pace": "Prix mensuel divisé par valeur API équivalente au rythme observé ; ratio, pas pourcentage.",
    "ratio_full": "Prix mensuel divisé par valeur API équivalente à pleine capacité ; ratio.",
    "used_percent": "Quota consommé, en pourcentage 0..100, observé ou estimé selon la source.",
    "reading_id": "Identifiant d'un relevé de quota.", "read_at": "Date du relevé.",
    "window_name": "Fenêtre du quota (weekly, fenêtre courte, etc.).",
    "resets_at": "Date annoncée de réinitialisation du quota.",
    "estimated": "Indique une estimation ; ne pas la présenter comme une mesure directe.",
    "bench_task": "Sous-classement de la famille de benchmark affecté à la tâche.",
    "is_primary": "Benchmark principal, utilisé aussi pour certaines exigences d'éligibilité.",
    "quality_benchmark": "Famille de benchmark de qualité historique de la tâche.",
    "quality_task": "Sous-classement de qualité historique de la tâche.",
    "default_objective": "Objectif de sélection par défaut pour cette tâche.",
    "intent_hint": "Indication destinée au classificateur d'intention.",
    "requirements": "Exigences de tâche : contexte minimal, benchmark principal, latence, raisonnement, impact d'un changement ; JSON extensible.",
    "internal": "Poste interne aux modules, à exclure des spécialités proposées à l'orchestrateur.",
    "consumers": "Modules consommateurs déclarés de ce poste.",
}


ENV_MEANINGS = {
    "WALTER_ROUTER_DATABASE_URL": "DSN PostgreSQL ; secret via .pgpass, jamais dans une URL publiée.",
    "WALTER_ROUTER_CLI": "Commande publique appelée par l'adaptateur de tools.",
    "WALTER_DELEGATION_DEPTH": "Profondeur de délégation de l'appelant (0 = le propriétaire) transmise au moteur par une délégation Engine API ; posée par le moteur pour ses sous-tâches.",
    "WALTER_RUN_ID": "Run Walter (runs.runs) servi par l'exécution ; posé par l'adaptateur du harness, inscrit dans models.exec_log.",
    "WALTER_RUN_CHANNEL": "test = run d'essai (posé par walter-scenario / walter-lab) : dépense payante plafonnée par walter-llm (test_budget), au-delà validation du propriétaire.",
    "WALTER_RUN_CONTEXT": "caller = le sous-agent walter_run reçoit seulement le contexte de l'appelant ; sinon le paquet walter-context (context.build scope=child).",
    "WALTER_SESSION_ID": "Session walter_logs de l'appelant ; parent de la session du sous-agent walter_run.",
    "WALTER_TASK_ID": "Tâche de sous-agent (runs.tasks) servie par l'exécution walter_run ; inscrite dans models.exec_log.",
    "WALTER_ROUTER_CHILD": "Marqueur des enfants historiques ; empêche une récursion de routage.",
    "WALTER_LLM_PORT": "Port HTTP loopback de la passerelle (défaut logiciel 8894).",
    "WALTER_LLM_URL": "URL loopback de la passerelle walter-llm pour les commandes Telegram des services web conversationnels (défaut http://127.0.0.1:8894).",
    "WALTER_LLM_TOKEN": "Jeton local d'agent de Hermes pour la passerelle walter-llm (~/.hermes/.env, jamais affiché).",
    "WALTER_FLARESOLVERR": "Adresse du service de lecture des sources qui le nécessitent.",
    "HERMES_HOME": "Emplacement du runtime historique pour les opérations/adaptateurs qui en dépendent encore.",
    "CLAUDE_PROJECTS": "Source locale de métriques des sessions Claude pour estimer un abonnement.",
    "CODEX_SESSIONS": "Source locale de métriques des sessions Codex pour estimer un abonnement.",
    "TELEGRAM_HOME_CHANNEL": "Destination d'instance des avis/propositions ; ne pas exporter sa valeur.",
    "CLOUDFLARE_ACCOUNT_ID": "Identifiant du compte pour la voie de décision configurée ; valeur privée hors documentation.",
    "CLOUDFLARE_AI_TOKEN": "Nom d'un accès secret pour la voie de décision ; ne pas afficher sa valeur.",
    "CLOUDFLARE_API_KEY": "Nom d'un accès secret utilisé par un adaptateur ; ne pas afficher sa valeur.",
    "CLOUDFLARE_EMAIL": "Identité de compte pour l'adaptateur Cloudflare ; donnée d'instance.",
    "KIE_API_KEY": "Nom d'accès fournisseur ; la passerelle utilise Walter Secrets, pas une clé transmise au modèle.",
    "OPENROUTER_API_KEY": "Nom d'accès fournisseur ; la passerelle utilise Walter Secrets.",
    "CHATGPT_TOKEN_DIR": "Réglage du transport de l'abonnement ; l'authentification reste fournie par son grant.",
    "CHATGPT_DEFAULT_INSTRUCTIONS": "Instructions de base du transport d'abonnement, indépendantes du goal de la sous-tâche.",
}


def database(conn):
    objects = []
    for row in conn.execute("""select c.oid, c.relname as name, c.relkind as kind,
        obj_description(c.oid, 'pg_class') as description from pg_class c
        join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='models' and c.relkind in ('r','v','m') order by c.relname"""):
        cols = []
        for col in conn.execute("""select a.attname as name, format_type(a.atttypid,a.atttypmod) as type,
            not a.attnotnull as nullable, pg_get_expr(d.adbin,d.adrelid) as default,
            col_description(a.attrelid,a.attnum) as comment from pg_attribute a
            left join pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum
            where a.attrelid=%s and a.attnum>0 and not a.attisdropped order by a.attnum""", (row['oid'],)):
            meaning = col.pop('comment') or FIELD_MEANINGS.get(col['name'])
            if not meaning and row['kind'] == 'r':
                raise ValueError(f"Undocumented database field: {row['name']}.{col['name']}")
            cols.append({**col, 'description': meaning or 'Champ dérivé ; expression complète dans la définition SQL de cette vue.'})
        obj = {k: row[k] for k in ('name','kind','description')}
        obj['columns'] = cols
        obj['constraints'] = [r['definition'] for r in conn.execute(
            'select pg_get_constraintdef(oid) as definition from pg_constraint where conrelid=%s order by conname', (row['oid'],))]
        obj['indexes'] = [r['indexdef'] for r in conn.execute(
            "select indexdef from pg_indexes where schemaname='models' and tablename=%s order by indexname", (row['name'],))]
        if row['kind'] in ('v','m'):
            obj['definition'] = conn.execute('select pg_get_viewdef(%s,true) as sql', (row['oid'],)).fetchone()['sql']
        objects.append(obj)
    return {'schema': 'models', 'objects': objects}


def source_files():
    roots = ('analysis','serve','research','plan','interface','store','llm','config','hermes-plugins','contracts','guardian')
    files = [paths.ROOT / n for n in ('cli.py','instance.py','paths.py','health.py','documentation.py')]
    for root in roots:
        files += [p for p in (paths.ROOT/root).rglob('*') if p.is_file() and p.suffix in ('.py','.json','.sql','.js','.mjs','.html')
                  and not any(part in ('venv','__pycache__','.pytest_cache','node_modules','tests') for part in p.parts)
                  and not p.name.startswith('test_')]
    files += [p for p in (paths.ROOT/'bin').iterdir() if p.is_file()]
    return sorted(set(files))


def normal(value):
    if isinstance(value, dict): return {str(k): normal(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)): return [normal(v) for v in value]
    if isinstance(value, (set, frozenset)): return [normal(v) for v in sorted(value, key=str)]
    return value


def inventory():
    constants, environments, code, config, env_details = [], set(), [], [], []
    for file in source_files():
        rel = str(file.relative_to(paths.ROOT))
        if file.suffix == '.py':
            tree = ast.parse(file.read_text())
            code.append({'file': rel, 'description': (ast.get_docstring(tree) or '').split('\n')[0],
                         'functions': [{'name': n.name, 'signature': ast.unparse(n.args),
                                        'description': (ast.get_docstring(n) or '').split('\n')[0]}
                                       for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]})
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('get','getenv','env_value','setdefault'):
                    src = ast.unparse(node.func)
                    if 'environ' in src or 'getenv' in src or 'env_value' in src:
                        if node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                            name = node.args[0].value
                            environments.add(name)
                            if name not in ENV_MEANINGS:
                                raise ValueError('Undocumented environment variable: '+name)
                            env_details.append({'name':name,'file':rel,'operation':node.func.attr,
                                                'default_expression':ast.unparse(node.args[1]) if len(node.args)>1 else 'aucun',
                                                'description':ENV_MEANINGS[name]})
            if rel in ('documentation.py','serve/api.py'):
                continue
            lines = file.read_text().splitlines()
            for n in tree.body:
                if not isinstance(n, ast.Assign): continue
                try: value = ast.literal_eval(n.value)
                except (ValueError,TypeError): continue
                for target in n.targets:
                    pairs = zip(target.elts,value) if isinstance(target,(ast.Tuple,ast.List)) and isinstance(value,(tuple,list)) else [(target,value)]
                    for name, item in pairs:
                        if isinstance(name,ast.Name) and name.id.isupper():
                            constants.append({'file':rel, 'name':name.id, 'value':normal(item),
                                              'comment':lines[n.lineno-1].split('#',1)[-1].strip() if '#' in lines[n.lineno-1] else ''})
        elif file.suffix == '.json' and rel.startswith('config/'):
            def visit(value, key=''):
                if isinstance(value,dict):
                    for k,v in sorted(value.items()): visit(v, key+'.'+k if key else k)
                elif isinstance(value,list) and value:
                    for v in value: visit(v,key+'[]')
                else:
                    config.append({'file':rel,'key':key,'type':type(value).__name__,'default':value})
            visit(json.loads(file.read_text()))
    # Arrays of model offers can repeat keys. Keep all declared defaults, deterministically.
    return {'constants':constants,'environment_names':sorted(environments),'environment':env_details,'code':code,'configuration':config}


def cli_reference():
    from walter_router.cli import build_parser
    def describe(parser):
        args = []
        for action in parser._actions:
            if isinstance(action,argparse._SubParsersAction):
                args.append({'subcommands':{name:describe(p) for name,p in sorted(action.choices.items())}})
            else:
                args.append({'flags':action.option_strings or [action.dest],'dest':action.dest,'required':action.required,
                             'default':action.default,'choices':list(action.choices) if action.choices is not None else None,
                             'nargs':action.nargs,'help':action.help or ''})
        return args
    return describe(build_parser())


class _BriefConn:
    def __init__(self,tasks,roles): self.tasks,self.roles=tasks,roles
    def execute(self,sql):
        return self.roles if 'preferences' in sql else [r for r in self.tasks if not r['internal'] and r['interface']!='tool']


def _neutral_metadata(value, owner):
    """Remove the active owner's address form from public descriptive catalog metadata."""
    if isinstance(value, str):
        return re.sub(re.escape(owner), 'l’utilisateur', value, flags=re.IGNORECASE) if owner else value
    if isinstance(value, dict):
        return {k: _neutral_metadata(v, owner) for k, v in value.items()}
    if isinstance(value, list):
        return [_neutral_metadata(v, owner) for v in value]
    return value


def collect(offline=False):
    snapshot = paths.ROOT/'docs'/'reference'/'catalog.json'
    if offline:
        old = json.loads(snapshot.read_text())
        db, tasks, roles, weights = (old[k] for k in ('database','tasks','roles','benchmark_weights'))
    else:
        from walter_router.store import db as store
        with store.connect() as conn:
            db = database(conn)
            tasks = list(conn.execute('select * from models.tasks order by task'))
            # Only public role keys, never pins, accounts, owner notes or prices.
            roles = [{'role':r['role']} for r in conn.execute("select distinct role from models.preferences where task in ('text_to_video','image_to_video') order by role")]
            weights = list(conn.execute('select task,benchmark,bench_task,is_primary,weight,note from models.task_benchmarks order by task,benchmark,bench_task'))
            conn.rollback()
    tasks, weights = _neutral_metadata([tasks, weights], instance.owner())
    result = {'schema_version':1,'api':api.schema(),'cli':cli_reference(),'database':db,'tasks':tasks,'roles':roles,
            'benchmark_weights':weights,'note':brief.document(_BriefConn(tasks,roles), owner='l’utilisateur'),
            'inventory':inventory(),
            'sources':{str(p.relative_to(paths.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}}
    return json.loads(json.dumps(result,ensure_ascii=False,default=str))


def cell(value):
    if value is None: return '—'
    if not isinstance(value,str): value=json.dumps(value,ensure_ascii=False,sort_keys=True)
    return value.replace('|','\\|').replace('\n','<br>')


def render(c):
    banner = '> Généré par `walter-router docs --write`. Modifier les sources, puis régénérer ; ne pas éditer ce fichier.\n\n'
    api_md = ['# Référence des outils et paramètres\n',banner]
    for tool in c['api']['tools']:
        api_md += [f"## {tool['name']}\n",tool['description']+'\n',
                   '| Paramètre | Type | Défaut transport | Obligatoire | Sens et valeurs |\n|---|---|---|---|---|']
        for key,p in tool['inputSchema']['properties'].items():
            details = p['description']+' '+ '; '.join(f'{k}: {cell(v)}' for k,v in p.items() if k not in ('type','description','default'))
            api_md.append(f"| `{key}` | {cell(p['type'])} | {cell(p.get('default'))} | {key in tool['inputSchema']['required']} | {details} |")
        api_md.append('')
    api_md += ['## CLI complète\n','```text']
    for entry in c['cli']:
        for name,arguments in entry.get('subcommands',{}).items():
            api_md.append('walter-router '+name)
            for a in arguments:
                api_md.append('  '+', '.join(a['flags'])+' : '+a['help']+' ; défaut='+cell(a['default'])+
                              (' ; valeurs='+cell(a['choices']) if a['choices'] is not None else ''))
    api_md.append('```')
    data_md = ['# Dictionnaire PostgreSQL complet : models\n',banner,
               'Types, valeurs par défaut, nullabilité, contraintes et index proviennent du catalogue PostgreSQL. '
               'Les JSON de sources et métadonnées sont extensibles : ils ne constituent pas des paramètres typés supplémentaires.\n']
    for obj in c['database']['objects']:
        data_md += [f"## models.{obj['name']} ({'table' if obj['kind']=='r' else 'vue'})\n",(obj['description'] or 'Objet dérivé du routeur.')+'\n',
                    '| Colonne | Type SQL | Nullable | Défaut SQL | Signification |\n|---|---|---|---|---|']
        for p in obj['columns']:
            data_md.append(f"| `{p['name']}` | {cell(p['type'])} | {p['nullable']} | {cell(p['default'])} | {cell(p['description'])} |")
        for key in ('constraints','indexes'):
            if obj[key]: data_md += ['\n'+key+' :\n','```sql',*obj[key],'```']
        if obj.get('definition'): data_md += ['\nDéfinition de la vue :\n','```sql',obj['definition'].strip(),'```']
        data_md.append('')
    config_md = ['# Constantes, environnement et configuration livrée\n',banner,
                 'Inventaire exhaustif des affectations littérales MAJUSCULES au niveau module et des noms de variables '
                 'd’environnement lus explicitement. Les constantes ne sont pas toutes des réglages utilisateur. '
                 'Les expressions calculées, paramètres locaux et métadonnées externes sont décrits par le code et les contrats d’usage.\n',
                 '| Source | Constante | Valeur | Commentaire source |\n|---|---|---|---|']
    for r in c['inventory']['constants']:
        config_md.append(f"| {r['file']} | `{r['name']}` | {cell(r['value'])} | {cell(r['comment'])} |")
    config_md += ['\n## Variables d’environnement lues ou initialisées\n',
                  '| Variable | Source | Accès | Défaut (expression de code) | Effet |\n|---|---|---|---|---|']
    for r in c['inventory']['environment']:
        config_md.append(f"| `{r['name']}` | {r['file']} | {r['operation']} | {cell(r['default_expression'])} | {cell(r['description'])} |")
    config_md += [
                  '\n## Clés des fichiers de configuration livrés\n',
                  'Ces valeurs sont les défauts logiciels, jamais un export des réglages privés de l’instance. '
                  'Les tableaux sont parcourus avec `[]` ; des clés répétées représentent plusieurs entrées.\n',
                  '| Fichier | Clé | Type | Défaut livré |\n|---|---|---|---|']
    for r in c['inventory']['configuration']:
        config_md.append(f"| {r['file']} | `{r['key']}` | {r['type']} | {cell(r['default'])} |")
    tasks_md = ['# Registre des tâches et poids des benchmarks\n',banner,
                'Les postes `internal=true` servent aux modules. Une capacité annoncée ou une offre existante '
                'ne prouve pas que le chemin d’exécution accepte toutes ses entrées. Voir EXECUTION.md. '
                'Les descriptions et exigences reflètent le registre SQL : certaines mentions de consommateurs '
                'historiques ne prouvent pas que ces services sont encore actifs. Les formes d’adresse au '
                'propriétaire sont neutralisées dans cet export public.\n',
                '| Clé | Interface | Interne | Objectif | Description / exigences |\n|---|---|---|---|---|']
    for t in c['tasks']:
        tasks_md.append(f"| `{t['task']}` | {t['interface']} | {t['internal']} | {t['default_objective']} | {cell(t.get('description'))} ; {cell(t.get('requirements'))} |")
    tasks_md += ['\n## Affectation des benchmarks\n','| Tâche | Famille | Sous-classement | Principal | Poids | Note |\n|---|---|---|---|---|---|']
    for w in c['benchmark_weights']:
        tasks_md.append('| '+' | '.join(cell(w.get(k)) for k in ('task','benchmark','bench_task','is_primary','weight','note'))+' |')
    code_md = ['# Inventaire du code\n',banner]
    for mod in c['inventory']['code']:
        code_md += ['## '+mod['file']+'\n',mod['description']+'\n']
        for f in mod['functions']:
            code_md += ['- `'+f['name']+'('+f['signature']+')` — '+f['description']]
        code_md.append('')
    return {'API.md':'\n'.join(api_md)+'\n','DATABASE.md':'\n'.join(data_md)+'\n',
            'CONFIGURATION.md':'\n'.join(config_md)+'\n','TASKS.md':'\n'.join(tasks_md)+'\n',
            'CODE.md':'\n'.join(code_md)+'\n','ORCHESTRATOR.md':c['note']['content']+'\n',
            'catalog.json':json.dumps(c,ensure_ascii=False,sort_keys=True,indent=2,default=str)+'\n'}


def maintain(write=False, offline=False):
    catalog = collect(offline)
    generated = render(catalog)
    folder = paths.ROOT/'docs'/'reference'
    stale = []
    for name,content in generated.items():
        p = folder/name
        if not p.exists() or p.read_text()!=content:
            stale.append('docs/reference/'+name)
            if write:
                folder.mkdir(parents=True,exist_ok=True)
                p.write_text(content)
    tables = [o for o in catalog['database']['objects'] if o['kind']=='r']
    return {'ok':write or not stale,'changed' if write else 'stale':stale,'offline':offline,
            'tables':len(tables),'columns':sum(len(t['columns']) for t in tables),'note_chars':catalog['note']['chars']}
