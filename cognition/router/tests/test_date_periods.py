"""Dates in words read by Walter (decision.resolve_date): periods, durations, the nearest year (18/11).

Regression of the bench « préflight natif » (18/11): the model found « cette semaine », « ces derniers jours »,
« le week-end dernier » and « 3 jours », but only single days were read, so the plan dropped them; « le 2 octobre »
said in November was read as next year's.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "llm"))

import decision as d  # noqa: E402

THU = "2026-11-19"            # a Thursday
SUN = "2026-11-22"


def r(text, now=THU):
    return d.resolve_date(text, now)


def test_weeks():
    assert r("cette semaine") == {"date": "2026-11-16", "end": "2026-11-22"}
    assert r("la semaine dernière") == {"date": "2026-11-09", "end": "2026-11-15"}
    assert r("next week") == {"date": "2026-11-23", "end": "2026-11-29"}


def test_weekend_gone_coming_or_both():
    assert r("le week-end dernier") == {"date": "2026-11-14", "end": "2026-11-15"}
    both = r("ce week-end")                    # on a weekday: the coming one, the gone one as the other reading
    assert (both["date"], both["end"], both["past"], both["past_end"], both["ambiguous"]) == \
        ("2026-11-21", "2026-11-22", "2026-11-14", "2026-11-15", True)
    assert r("ce week-end", SUN) == {"date": "2026-11-21", "end": "2026-11-22"}


def test_vague_and_since():
    assert r("ces derniers jours") == {"date": "2026-11-12", "end": "2026-11-19", "approx": True}
    assert r("depuis le début du mois") == {"date": "2026-11-01", "end": "2026-11-19"}
    assert r("ça fait trois semaines") == {"date": "2026-10-29", "end": "2026-11-19"}
    assert r("les 3 derniers jours") == {"date": "2026-11-16", "end": "2026-11-19"}


def test_months_and_years():
    assert r("le mois dernier") == {"date": "2026-10-01", "end": "2026-10-31"}
    assert r("avant la fin du mois") == {"date": "2026-11-30"}
    assert r("en octobre") == {"date": "2026-10-01", "end": "2026-10-31"}
    assert r("début décembre") == {"date": "2026-12-01", "end": "2026-12-10", "approx": True}
    assert r("l'an dernier") == {"date": "2025-01-01", "end": "2025-12-31"}


def test_a_duration_names_no_day_but_is_kept():
    assert r("3 jours") == {"duration": "P3D"}
    assert r("sur 2 semaines") == {"duration": "P2W"}
    assert r("dans 3 jours") == {"date": "2026-11-22"}      # with its preposition it is a day


def test_day_and_month_without_year_is_the_nearest():
    assert r("2 octobre")["date"] == "2026-10-02"            # gone 7 weeks ago, not next year
    assert r("3 décembre à 10 h") == {"time": "10:00", "date": "2026-12-03"}
    assert r("15 janvier")["date"] == "2027-01-15"


def test_weekday_of_a_named_week():
    assert r("lundi de la semaine prochaine") == {"date": "2026-11-23"}
    assert r("mardi de la semaine dernière") == {"date": "2026-11-10"}
    sat = r("samedi soir")                    # no tense in the words: the coming one, the gone one as the other
    assert (sat["date"], sat["past"], sat["ambiguous"]) == ("2026-11-21", "2026-11-14", True)


def test_a_time_alone_names_no_day():
    assert r("14h") is None


def test_a_passage_is_read_with_the_date_words_that_touch_it():
    """Where the model cuts a passage varies: the words just outside it that change the date are read too
    (bench « hold » h12, 18/11: « depuis le début du mois » found as « le début du mois »)."""
    def read(msg, span):
        return d.resolve({"q": {"type": "spans", "resolve": "date"}}, {"q": {"spans": [{"text": span}]}}, THU,
                         msg)["q"]["spans"][0]
    got = read("Combien depuis le début du mois ?", "le début du mois")
    assert (got["text"], got["date"], got["end"]) == ("le début du mois", "2026-11-01", "2026-11-19")
    assert read("je pars dans 3 jours", "3 jours")["date"] == "2026-11-22"
    assert read("on a bossé pendant 3 jours", "3 jours")["duration"] == "P3D"
    assert read("c'était il y a 3 jours", "3 jours")["date"] == "2026-11-16"
    assert read("le week-end dernier on a vu", "le week-end")["end"] == "2026-11-15"
    assert read("rendez-vous après-demain", "demain")["date"] == "2026-11-21"
    assert read("within 3 days please", "3 days")["date"] == "2026-11-22"
    # no message, or a passage said twice: read as written
    assert d.resolve({"q": {"type": "spans", "resolve": "date"}}, {"q": {"spans": [{"text": "3 jours"}]}},
                     THU)["q"]["spans"][0]["duration"] == "P3D"
    assert read("3 jours ou dans 3 jours", "3 jours")["duration"] == "P3D"
