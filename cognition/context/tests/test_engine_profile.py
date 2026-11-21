from walter_context import config


def test_engine_router_alias_gets_engine_profile_not_default():
    c = config.load()
    p = c.profile("walter/auto")
    assert p.match == "walter/*" and p.effective_budget >= 96000
    assert c.profile("auto").match == "*"            # the port qualifies the alias; a bare name stays unknown
