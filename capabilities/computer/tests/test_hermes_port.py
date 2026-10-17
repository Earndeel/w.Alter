"""Contract checks against the installed host without starting a desktop session."""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

HERMES = Path('/root/.hermes/hermes-agent')
if not HERMES.exists():
    pytest.skip('optional installed Hermes contract', allow_module_level=True)
sys.path.insert(0, str(HERMES))
from tools.computer_use.backend import ActionResult as HostActionResult, CaptureResult as HostCaptureResult
from walter_computer.ports import hermes
from test_modularity import FakeTransport


def test_native_host_and_port_have_identical_results_for_same_transport():
    with patch.object(hermes, '_load_hermes_config', return_value={}):
        backend = hermes.WalterCuaBackend(observer_enabled=False)
    backend._session = FakeTransport()
    capture = backend.capture(mode='ax', app='Demo', pid=42, window_id=7)
    assert isinstance(capture, HostCaptureResult)
    assert capture.capture_error is None
    assert capture.elements[0].element_token == 'snapshot-A'
    backend.arm_native_refs(capture)
    # Stale refs refuse before a presence check or transport mutation.
    backend._walter_ref_guard_state = 'superseded'
    result = backend.click(element=1)
    assert isinstance(result, HostActionResult)
    assert not result.ok
    assert result.code == 'stale_element_token'
    backend._bridge.stop()


def test_registration_retains_host_extension_seams():
    class Context:
        def __init__(self): self.backends={}; self.actions={}; self.prompts={}
        def register_computer_use_backend(self,name,factory): self.backends[name]=factory
        def register_computer_use_action(self,name,handler,**kwargs): self.actions[name]=(handler,kwargs)
        def register_system_prompt_section(self,name,prompt,**kwargs): self.prompts[name]=prompt
    ctx=Context()
    with patch.object(hermes, '_load_hermes_config', return_value={}):
        hermes.register(ctx)
    assert set(ctx.backends) == {'walter'}
    assert set(ctx.actions) == {'launch_app','open_url','device_context','vision_target','click_visual_ref','targeted_verify'}
    assert len(ctx.prompts)==1


def test_missing_host_seam_fails_closed():
    with pytest.raises(RuntimeError, match='extension seams'):
        hermes.register(object())


def _registered_override():
    class Context:
        def register_tool(self, **kwargs): self.tool=kwargs
        def register_system_prompt_section(self,*args,**kwargs): pass
        def register_hook(self,*args): pass
    ctx=Context()
    with patch.object(hermes, '_load_hermes_config', return_value={}):
        hermes.register(ctx)
    return ctx.tool


def test_public_override_retains_schema_and_explicit_consent_flag():
    tool=_registered_override()
    assert tool['name']=='computer_use'
    assert tool['override'] is True
    assert 'click' in tool['schema']['parameters']['properties']['action']['enum']
    assert 'launch_app' in tool['schema']['parameters']['properties']['action']['enum']


def test_override_approval_denial_never_starts_backend():
    tool=_registered_override()
    host=hermes._native_contract()
    from tools.bot_desktop import lease
    with patch.object(lease,'assert_agent_may_act',return_value=type('Lease',(),{'epoch':1})()), \
         patch.object(host,'_reject_unsafe',return_value=None), \
         patch.object(host,'_request_approval',return_value='DENIED') as approve, \
         patch.object(hermes._NATIVE_SESSIONS,'backend',side_effect=AssertionError('must not start')):
        assert tool['handler']({'action':'click','element':1},session_id='test')=='DENIED'
        approve.assert_called_once()


def test_override_human_lease_denial_never_starts_backend():
    tool=_registered_override()
    from tools.bot_desktop import lease
    with patch.object(lease,'assert_agent_may_act',side_effect=lease.HumanHasControl('human')), \
         patch.object(hermes._NATIVE_SESSIONS,'backend',side_effect=AssertionError('must not start')):
        assert 'human_has_control' in tool['handler']({'action':'capture'},session_id='test')


def test_new_mutation_and_foreground_scope_use_central_gate():
    tool=_registered_override()
    host=hermes._native_contract()
    from tools.bot_desktop import lease
    state=type('Lease',(),{'epoch':1})()
    with patch.object(lease,'assert_agent_may_act',return_value=state), \
         patch.object(host,'_reject_unsafe',return_value=None), \
         patch.object(host,'_request_approval',side_effect=[None,'FOREGROUND DENIED']) as approve, \
         patch.object(hermes._NATIVE_SESSIONS,'backend',side_effect=AssertionError('must not start')):
        assert tool['handler']({'action':'launch_app','app':'Demo','bring_to_front':True},session_id='test')=='FOREGROUND DENIED'
        assert [call.args[0] for call in approve.call_args_list]==['launch_app','bring_to_front']


def test_override_uses_same_device_lock_as_independent_port():
    from walter_computer.device_lock import DeviceCallLock
    from tools.bot_desktop import lease
    tool=_registered_override()
    host=hermes._native_contract()
    with DeviceCallLock().hold() as acquired:
        assert acquired
        with patch.object(lease,'assert_agent_may_act',return_value=type('Lease',(),{'epoch':1})()), \
             patch.object(host,'_reject_unsafe',return_value=None), \
             patch.object(hermes._NATIVE_SESSIONS,'backend',side_effect=AssertionError('must not start')):
            assert 'device_busy' in tool['handler']({'action':'list_apps'},session_id='test')


def test_human_takeover_discards_result_before_return():
    tool=_registered_override()
    host=hermes._native_contract()
    from tools.bot_desktop import lease
    initial=type('Lease',(),{'epoch':1})()
    changed=type('Lease',(),{'epoch':2})()
    with patch.object(lease,'assert_agent_may_act',return_value=initial), \
         patch.object(lease,'get',side_effect=[initial,changed]), \
         patch.object(host,'_reject_unsafe',return_value=None), \
         patch.object(hermes._NATIVE_SESSIONS,'backend',return_value=type('Backend',(),{})()), \
         patch.object(host,'_dispatch',return_value='SYNTHETIC_PRIVATE_RESULT'):
        result=tool['handler']({'action':'list_apps'},session_id='test')
        assert 'human_has_control' in result
        assert 'SYNTHETIC_PRIVATE_RESULT' not in result
