import re

from funkbot import tools


def test_no_bot_tool_can_change_budgets_policies_pause_or_delete_things():
    """Phase 8: the authority boundary is structural. A Bot's tools are a closed registry with no way to touch caps, policies or the pause switch."""
    forbidden = re.compile(r'budget|cap|limit|polic|pause|delete|purge|secret|key|password|permission', re.I)
    assert not [name for name in tools.REGISTRY if forbidden.search(name)]


def test_every_family_tool_is_always_reviewed_and_a_write_not_a_spend():
    for name in tools.FAMILY_TOOLS:
        assert name in tools.ALWAYS_REVIEWED
        assert tools.REGISTRY[name].risk in ('write', 'send')
