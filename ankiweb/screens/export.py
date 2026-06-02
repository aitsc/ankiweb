from __future__ import annotations
import html
from ankiweb.i18n import tr


def render_export_html(col) -> str:
    decks = col.decks.all_names_and_ids(skip_empty_default=False, include_filtered=False)
    opts = "".join(
        f"<option value='{d.id}'>{html.escape(d.name)}</option>" for d in decks)
    e = lambda s: html.escape(s)
    body = f"""
<div class='export'>
  <h3>{e(tr.actions_export())}</h3>
  <form id='ex' method='post' action='/export'>
    <div><label>Export: <select name='target' id='target'>
      <option value='all'>{e(tr.browsing_whole_collection())}</option>{opts}</select></label></div>
    <fieldset><legend>Format</legend>
      <label><input type='radio' name='fmt' value='apkg' checked onchange='onFmt()'> {e(tr.exporting_anki_deck_package())} (.apkg)</label><br>
      <label><input type='radio' name='fmt' value='colpkg' onchange='onFmt()'> {e(tr.exporting_anki_collection_package())} (.colpkg)</label><br>
      <label><input type='radio' name='fmt' value='notes_csv' onchange='onFmt()'> {e(tr.exporting_notes_in_plain_text())} (.csv)</label><br>
      <label><input type='radio' name='fmt' value='cards_csv' onchange='onFmt()'> {e(tr.exporting_cards_in_plain_text())} (.csv)</label>
    </fieldset>
    <fieldset id='pkgopts'><legend>Package options</legend>
      <label><input type='checkbox' name='with_scheduling'> {e(tr.exporting_include_scheduling_information())}</label><br>
      <label><input type='checkbox' name='with_media' checked> {e(tr.exporting_include_media())}</label><br>
      <label><input type='checkbox' name='with_deck_configs'> {e(tr.exporting_include_deck_configs())}</label><br>
      <label><input type='checkbox' name='legacy' checked> {e(tr.exporting_support_older_anki_versions())}</label>
    </fieldset>
    <fieldset id='csvopts' style='display:none;'><legend>CSV options</legend>
      <label><input type='checkbox' name='with_html'> {e(tr.exporting_include_html_and_media_references())}</label><br>
      <label><input type='checkbox' name='with_tags' checked> {e(tr.exporting_include_tags())}</label><br>
      <label><input type='checkbox' name='with_deck' checked> {e(tr.exporting_include_deck())}</label><br>
      <label><input type='checkbox' name='with_notetype' checked> {e(tr.exporting_include_notetype())}</label><br>
      <label><input type='checkbox' name='with_guid'> {e(tr.exporting_include_guid())}</label>
    </fieldset>
    <div style='margin-top:10px;'>
      <button type='submit' id='go'>{e(tr.actions_export())}</button>
      <a href='/deckbrowser'>{e(tr.actions_cancel())}</a>
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
