from __future__ import annotations
import html


def render_congrats_html(col) -> str:
    """Simple server-rendered finished screen (the real SvelteKit congrats is a later plan)."""
    info = col.sched.congratulations_info()
    lines = ["<h1>Congratulations!</h1>",
             "<p>You have finished this deck for now.</p>"]
    if info.learn_remaining:
        mins = max(1, info.secs_until_next_learn // 60)
        lines.append(f"<p>The next learning card will be ready in {mins} minute(s).</p>")
    if info.have_user_buried or info.have_sched_buried:
        lines.append("<p><button onclick='pycmd(\"unbury\")'>Unbury</button> "
                     "buried cards.</p>")
    back = "<p><button onclick='pycmd(\"decks\")'>Back to Decks</button></p>"
    return "<center class='congrats'>" + "".join(lines) + back + "</center>"
