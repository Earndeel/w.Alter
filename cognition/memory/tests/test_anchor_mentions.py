"""entities.anchors (18/11): a path, a URL, a file name or a code identifier names no project.

Bench « préflight natif »: « Combien de fichiers .md dans /walter/docs ? » and « Utilise l'outil walter_browse … »
were sent to the owner's memory because « walter » matched inside the path and the tool's name.
"""
from walter_memory import entities


def _known(monkeypatch):
    aliases = [("walter", "e1", "project"), ("walter browse", "e2", "project"), ("sagora", "e3", "project"),
               ("walter router", "e4", "project")]
    monkeypatch.setattr(entities, "_aliases", lambda: aliases)
    monkeypatch.setattr(entities, "_ANCHOR_AT", [1e18])        # no cache refresh in the test


def names(text):
    return [a["alias"] for a in entities.anchors(text)]


def test_paths_urls_files_and_identifiers_are_not_mentions(monkeypatch):
    _known(monkeypatch)
    assert names("Combien de fichiers .md dans /walter/docs ?") == []
    assert names("Utilise l'outil walter_browse pour trouver le prix") == []
    assert names("voir https://sagora.walter-ai.cloud/profils") == []
    assert names("lis `walter router` puis réponds") == []
    assert names("ouvre walter.md") == []


def test_real_mentions_still_count(monkeypatch):
    _known(monkeypatch)
    assert names("Que sais-tu de Sagora ?") == ["sagora"]
    assert set(names("Walter Router doit-il prendre le meilleur modèle ?")) == {"walter router", "walter"}
    assert names("Par quelle connexion sort le navigateur de Walter ?") == ["walter"]
