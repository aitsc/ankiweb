from __future__ import annotations
# Message shapes (JSON over WebSocket):
#   client->server: {"type":"cmd", "id":int|None, "ctx":str, "arg":str}
#                   {"type":"result", "id":int, "value":<json>}
#                   {"type":"ready", "ctx":str}     # after domDone
#   server->client: {"type":"call", "id":int|None, "fn":str, "args":[...]}
#                   {"type":"eval", "id":int|None, "js":str}
#                   {"type":"result", "id":int, "value":<json>}   # reply to a cmd cb
#                   {"type":"opchanges", "flags":{...}, "initiator":str|None}
