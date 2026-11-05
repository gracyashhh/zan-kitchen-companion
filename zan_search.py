"""Zān's live recipe search with typeahead suggestions (Streamlit v2 component).

Only locally saved recipe titles and ingredients are searched; no API/model calls.
"""
import streamlit as st

_HTML = """
<div class="zan-search" id="zan-search-root">
  <label for="zan-search-input" class="sr-only">Search saved recipes</label>
  <div class="zan-search-bar">
    <input id="zan-search-input" type="search" autocomplete="off"
           aria-label="Search saved recipes" aria-autocomplete="list"
           aria-controls="zan-search-options" aria-expanded="false" />
    <button id="zan-clear" class="zan-clear" type="button" aria-label="Clear search">×</button>
    <svg class="zan-search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none"
      aria-hidden="true" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <circle cx="10.8" cy="10.8" r="6.6"/><path d="m16 16 5 5"/>
    </svg>
  </div>
  <div id="zan-search-options" class="zan-search-options" role="listbox" hidden></div>
</div>
"""

_CSS = """
* { box-sizing: border-box; }
.zan-search { position:relative; width:100%; z-index:20; color:#513747;
  font-family: 'DM Sans', ui-sans-serif, system-ui, sans-serif; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px;
  overflow:hidden; clip:rect(0,0,0,0); border:0; }
.zan-search-bar { height:52px; width:100%; display:flex; align-items:center;
  background:#FFFFFF; border:1px solid #E7D8E0; border-radius:27px;
  box-shadow:0 4px 16px rgba(81,55,71,.06); padding:0 16px 0 19px;
  transition: border-color .15s, box-shadow .15s; }
.zan-search-bar:focus-within { border-color:#C77998;
  box-shadow:0 3px 14px rgba(141,38,85,.12); }
#zan-search-input { outline:none; flex:1; min-width:0; border:0; background:transparent;
  box-shadow:none; font:500 15px 'DM Sans',ui-sans-serif,system-ui,sans-serif;
  color:#513747; padding:0; height:100%; -webkit-appearance:none; }
#zan-search-input::placeholder { color:#9E8D97; opacity:1; }
#zan-search-input::-webkit-search-cancel-button { display:none; }
.zan-search-icon { flex:none; color:#8C6E7C; margin-left:9px; }
.zan-clear { flex:none; display:none; border:0; border-radius:50%; background:#FBE8EF;
  color:#8D2655; font-size:21px; line-height:1; width:30px; height:30px;
  align-items:center; justify-content:center; cursor:pointer; }
.zan-clear:hover { background:#F5C5D8; }
.zan-search-options { position:absolute; top:calc(100% + 5px); left:0; right:0;
  z-index:60; padding:7px; background:#fff; border:1px solid #E7D8E0;
  border-radius:19px; box-shadow:0 14px 36px rgba(81,55,71,.12);
  max-height:320px; overflow-y:auto; }
.zan-search-options[hidden] { display:none; }
.zan-option { display:flex; flex-direction:column; align-items:flex-start; width:100%;
  text-align:left; background:transparent; border:0; padding:10px 13px;
  border-radius:12px; cursor:pointer; color:#513747; }
.zan-option:hover,.zan-option.active { background:#FFF1F6; }
.zan-option-name { font:700 14px 'DM Sans',ui-sans-serif,sans-serif; }
.zan-option-hint { font:500 12px 'DM Sans',ui-sans-serif,sans-serif;
  color:#907D87; margin-top:3px; }
@media (max-width:760px) { .zan-search-bar { height:48px; }
  #zan-search-input { font-size:16px; }
  .zan-search-options { max-height:240px; }
}
"""

_JS = r"""
export default function({parentElement, data, setStateValue}) {
  const root = parentElement.querySelector('#zan-search-root');
  const input = root.querySelector('#zan-search-input');
  const popup = root.querySelector('#zan-search-options');
  const clearBtn = root.querySelector('#zan-clear');
  const searchRows = Array.isArray(data.recipes) ? data.recipes : [];

  parentElement._setValue = setStateValue;
  parentElement._searchRows = searchRows;
  parentElement._activeIdx = -1;

  function matchesFor(term) {
    const needle = term.toLocaleLowerCase().trim();
    if (!needle) return [];
    return parentElement._searchRows.filter(row => {
      const name = (row.name || '').toLocaleLowerCase();
      const details = (row.ingredients || '').toLocaleLowerCase();
      return name.includes(needle) || details.includes(needle);
    }).sort((a,b) => {
      const an = (a.name || '').toLocaleLowerCase();
      const bn = (b.name || '').toLocaleLowerCase();
      const score = n => n.startsWith(needle) ? 0 : n.includes(needle) ? 1 : 2;
      return score(an) - score(bn) || an.localeCompare(bn);
    }).slice(0,5);
  }

  parentElement._show = (forceOpen=false) => {
    const term = input.value.trim();
    clearBtn.style.display = term ? 'flex' : 'none';
    const found = matchesFor(term);
    popup.replaceChildren();
    parentElement._activeIdx = -1;
    const open = !!term && found.length > 0 && (forceOpen || parentElement._focused);
    popup.hidden = !open;
    input.setAttribute('aria-expanded', String(open));
    if (!open) return;
    found.forEach((recipe, idx) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('role','option');
      button.className = 'zan-option';
      const title = document.createElement('span');
      title.className = 'zan-option-name';
      title.textContent = recipe.name;
      const hint = document.createElement('span');
      hint.className = 'zan-option-hint';
      hint.textContent = 'Saved recipe';
      button.append(title, hint);
      button.addEventListener('mousedown', e => e.preventDefault());
      button.addEventListener('click', () => {
        clearTimeout(parentElement._pending);
        input.value = recipe.name;
        parentElement._typing = true;
        parentElement._setValue('query', input.value);
        parentElement._focused = false;
        popup.hidden = true;
        input.setAttribute('aria-expanded','false');
        clearBtn.style.display = 'flex';
        input.blur();
      });
      popup.appendChild(button);
    });
  };

  const pythonValue = data.query || '';
  if (input.value === pythonValue) {
    parentElement._typing = false;
  } else if (!parentElement._typing) {
    input.value = pythonValue;
  }
  parentElement._show();

  if (!parentElement._attached) {
    parentElement._attached = true;
    parentElement._focused = false;
    input.addEventListener('focus', () => {
      parentElement._focused = true;
      parentElement._show(true);
    });
    input.addEventListener('input', () => {
      parentElement._typing = true;
      parentElement._show(true);
      clearTimeout(parentElement._pending);
      parentElement._pending = setTimeout(() => {
        parentElement._setValue('query', input.value);
      }, 150);
    });
    input.addEventListener('blur', () => {
      parentElement._focused = false;
      setTimeout(() => { popup.hidden = true;
        input.setAttribute('aria-expanded', 'false'); }, 120);
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        popup.hidden = true; input.setAttribute('aria-expanded','false'); return;
      }
      if (e.key === 'Enter' && !popup.hidden) {
        const opts = [...popup.querySelectorAll('.zan-option')];
        const at = parentElement._activeIdx >= 0 ? parentElement._activeIdx : 0;
        if (opts[at]) { e.preventDefault(); opts[at].click(); }
      }
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !popup.hidden) {
        e.preventDefault();
        const opts = [...popup.querySelectorAll('.zan-option')];
        if (!opts.length) return;
        const prev = parentElement._activeIdx;
        const next = e.key === 'ArrowDown' ? Math.min(prev + 1, opts.length-1)
          : Math.max(prev - 1, 0);
        parentElement._activeIdx = next;
        opts.forEach((b,i)=>b.classList.toggle('active',i===next));
      }
    });
    clearBtn.addEventListener('click', () => {
      clearTimeout(parentElement._pending);
      input.value = '';
      parentElement._typing = true;
      parentElement._setValue('query','');
      parentElement._show();
      input.focus();
    });
  }
}
"""

_component = st.components.v2.component(
    "zan_recipe_search_v1", html=_HTML, css=_CSS, js=_JS, isolate_styles=True
)


def recipe_search(recipes, *, key="zan_live_recipe_search"):
    """Filter on typing, and show up to 5 clickable suggestions without Enter."""
    rows = []
    seen = set()
    for item in recipes:
        name = str(item.get("name") or "").strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        ingredients = ", ".join(str(x) for x in (item.get("ingredients") or []))
        rows.append({"name": name, "ingredients": ingredients})
    state = st.session_state.get(key, {})
    current = state.get("query", "") if isinstance(state, dict) else ""
    result = _component(
        data={"query": current, "recipes": rows},
        default={"query": ""},
        key=key,
        on_query_change=lambda: None,
    )
    return result.query or ""
