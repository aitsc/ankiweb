from __future__ import annotations
import html


def render_export_html(col) -> str:
    decks = col.decks.all_names_and_ids(skip_empty_default=False, include_filtered=False)
    opts = "".join(
        f"<option value='{d.id}'>{html.escape(d.name)}</option>" for d in decks)
    body = f"""
<div class='export'>
  <h3>Export</h3>
  <form id='ex' method='post' action='/export'>
    <div><label>Export: <select name='target' id='target'>
      <option value='all'>Whole Collection</option>{opts}</select></label></div>
    <fieldset><legend>Format</legend>
      <label><input type='radio' name='fmt' value='apkg' checked onchange='onFmt()'> Anki Deck Package (.apkg)</label><br>
      <label><input type='radio' name='fmt' value='colpkg' onchange='onFmt()'> Anki Collection Package (.colpkg)</label><br>
      <label><input type='radio' name='fmt' value='notes_csv' onchange='onFmt()'> Notes in Plain Text (.csv)</label><br>
      <label><input type='radio' name='fmt' value='cards_csv' onchange='onFmt()'> Cards in Plain Text (.csv)</label>
    </fieldset>
    <fieldset id='pkgopts'><legend>Package options</legend>
      <label><input type='checkbox' name='with_scheduling'> Include scheduling information</label><br>
      <label><input type='checkbox' name='with_media' checked> Include media</label><br>
      <label><input type='checkbox' name='with_deck_configs'> Include deck presets</label><br>
      <label><input type='checkbox' name='legacy' checked> Support older Anki versions</label>
    </fieldset>
    <fieldset id='csvopts' style='display:none;'><legend>CSV options</legend>
      <label><input type='checkbox' name='with_html'> Include HTML and media references</label><br>
      <label><input type='checkbox' name='with_tags' checked> Include tags</label><br>
      <label><input type='checkbox' name='with_deck' checked> Include deck</label><br>
      <label><input type='checkbox' name='with_notetype' checked> Include notetype</label><br>
      <label><input type='checkbox' name='with_guid'> Include unique identifier</label>
    </fieldset>
    <div style='margin-top:10px;'>
      <button type='submit' id='go'>Export</button>
      <a href='/deckbrowser'>Cancel</a>
    </div>
  </form>
</div>
<script>
function onFmt() {{
  var f = document.querySelector("input[name='fmt']:checked").value;
  var pkg = (f === 'apkg' || f === 'colpkg');
  document.getElementById('pkgopts').style.display = pkg ? '' : 'none';
  document.getElementById('csvopts').style.display = pkg ? 'none' : '';
  document.getElementById('target').disabled = (f === 'colpkg');
}}
onFmt();
</script>
"""
    return body
