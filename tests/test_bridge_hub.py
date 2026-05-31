import asyncio
import pytest
from ankiweb.bridge.hub import BridgeHub


class FakeWS:
    def __init__(self):
        self.sent = []
    async def send_json(self, obj):
        self.sent.append(obj)


async def test_register_and_broadcast_opchanges():
    hub = BridgeHub()
    ws = FakeWS()
    hub.register("deckbrowser", ws)
    await hub.broadcast_opchanges({"study_queues": True}, initiator="x")
    assert ws.sent == [{"type": "opchanges", "flags": {"study_queues": True}, "initiator": "x"}]
    hub.unregister("deckbrowser", ws)
    await hub.broadcast_opchanges({"note": True}, initiator=None)
    assert len(ws.sent) == 1  # no longer receives


async def test_push_call_to_context():
    hub = BridgeHub()
    ws = FakeWS()
    hub.register("reviewer", ws)
    await hub.push_call("reviewer", "_showQuestion", ["q", "a", "card card1"])
    assert ws.sent[0]["type"] == "call"
    assert ws.sent[0]["fn"] == "_showQuestion"
    assert ws.sent[0]["args"] == ["q", "a", "card card1"]
