from __future__ import annotations
import html
from ankiweb.i18n import tr


def render_congrats_html(col) -> str:
    """Simple server-rendered finished screen (the real SvelteKit congrats is a later plan)."""
    info = col.sched.congratulations_info()
    # scheduling_congratulations_finished is one combined sentence ("Congratulations! You have
    # finished this deck for now."); render it whole so it localizes.
    lines = [f"<h1>{html.escape(tr.scheduling_congratulations_finished())}</h1>"]
    if info.learn_remaining:
        # Keyless (documented): scheduling_next_learn_due needs bidi-isolate chars + a localized
        # unit word — disproportionate for this simplified secondary line.
        mins = max(1, info.secs_until_next_learn // 60)
        lines.append(f"<p>The next learning card will be ready in {mins} minute(s).</p>")
    if info.have_user_buried or info.have_sched_buried:
        lines.append(f"<p><button onclick='pycmd(\"unbury\")'>{tr.studying_unbury()}</button> "
                     "buried cards.</p>")
    back = "<p><button onclick='pycmd(\"decks\")'>Back to Decks</button></p>"
    return "<center class='congrats'>" + "".join(lines) + back + "</center>"
