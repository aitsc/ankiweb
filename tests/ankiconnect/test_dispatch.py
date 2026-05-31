import pytest
from ankiweb.ankiconnect.registry import ACTIONS, action
from ankiweb.ankiconnect.dispatch import dispatch_one
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.runtime import Runtime


@pytest.fixture
def rt():
    return Runtime(service=None, config=AnkiConnectConfig())


@pytest.fixture(autouse=True)
def _register():
    @action("echo")
    async def echo(rt, value=None):
        return value
    @action("boom")
    async def boom(rt):
        raise ValueError("kaboom")
    yield
    ACTIONS.pop("echo", None)
    ACTIONS.pop("boom", None)


async def test_v6_success_enveloped(rt):
    reply = await dispatch_one(rt, {"action": "echo", "version": 6, "params": {"value": 7}})
    assert reply == {"result": 7, "error": None}


async def test_v4_success_is_bare(rt):
    reply = await dispatch_one(rt, {"action": "echo", "version": 4, "params": {"value": 7}})
    assert reply == 7


async def test_default_version_is_4_bare(rt):
    reply = await dispatch_one(rt, {"action": "echo", "params": {"value": "x"}})
    assert reply == "x"


async def test_error_always_enveloped_even_v4(rt):
    reply = await dispatch_one(rt, {"action": "boom", "version": 4})
    assert reply == {"result": None, "error": "kaboom"}


async def test_unknown_action_errors(rt):
    reply = await dispatch_one(rt, {"action": "nope", "version": 6})
    assert reply["result"] is None and "nope" in reply["error"]


async def test_multi_returns_list_of_replies(rt):
    reply = await dispatch_one(rt, {"action": "multi", "version": 6, "params": {"actions": [
        {"action": "echo", "version": 6, "params": {"value": 1}},
        {"action": "boom", "version": 6},
    ]}})
    assert reply["result"][0] == {"result": 1, "error": None}
    assert reply["result"][1] == {"result": None, "error": "kaboom"}


async def test_apikey_gate(rt):
    rt.config.api_key = "s3cret"
    bad = await dispatch_one(rt, {"action": "echo", "version": 6, "key": "wrong", "params": {"value": 1}})
    assert bad["result"] is None and "key" in bad["error"].lower()
    ok = await dispatch_one(rt, {"action": "echo", "version": 6, "key": "s3cret", "params": {"value": 1}})
    assert ok == {"result": 1, "error": None}
