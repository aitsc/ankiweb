"""Pydantic request models for the typed /actions/<name> REST surface (OpenAPI docs).

One module per actions/ file; each defines `<Action>Params` models wired into the matching
`@action(..., params=...)` decorator. Field names match the exact AnkiConnect param names.
"""
