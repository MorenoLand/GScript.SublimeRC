import sublime
import sublime_plugin
import json
import os
import threading
import re
import time

try:
  from . import _lsp_players
  _has_player_completions = True
except ImportError:
  _has_player_completions = False

try:
  from . import _main
  _has_server_objects = True
except ImportError:
  _has_server_objects = False

_popup_dimensions_cache = (600, 400, 600, 400)
_popup_dimensions_last_load = 0
POPUP_STYLE_VERSION = 2
SUBLIMERC_POPUP_SURFACE = "#242936"
SUBLIMERC_EDITOR_SCHEMES = {
  "sublimerc-gscript-editor.sublime-color-scheme",
  "sublimerc-goption-editor.sublime-color-scheme",
}

def _is_sublimerc_editor_scheme(color_scheme):
  scheme_name = str(color_scheme or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
  return scheme_name in SUBLIMERC_EDITOR_SCHEMES

def _get_popup_dimensions():
  global _popup_dimensions_cache, _popup_dimensions_last_load
  now = time.time()
  if now - _popup_dimensions_last_load > 5.0:
    try:
      settings = sublime.load_settings("SublimeRC.sublime-settings")
      main_w = int(settings.get("popup_max_width", 600))
      compact_w = int(settings.get("popup_max_width_compact", 400))
      main_h = int(settings.get("popup_max_height", 600))
      compact_h = int(settings.get("popup_max_height_compact", 400))
      main_w = max(300, min(1200, main_w))
      compact_w = max(250, min(800, compact_w))
      main_h = max(200, min(1200, main_h))
      compact_h = max(150, min(800, compact_h))
      _popup_dimensions_cache = (main_w, compact_w, main_h, compact_h)
      _popup_dimensions_last_load = now
    except:
      pass
  return _popup_dimensions_cache

def get_package_name():
  try:
    file_path = __file__
    packages_path = sublime.packages_path()
    installed_packages_path = os.path.join(os.path.dirname(packages_path), "Installed Packages")
    if packages_path in file_path:
      rel_path = os.path.relpath(file_path, packages_path)
      package_name = rel_path.split(os.sep)[0]
      return package_name
    elif installed_packages_path in file_path:
      rel_path = os.path.relpath(file_path, installed_packages_path)
      package_name = rel_path.split(os.sep)[0]
      if package_name.endswith('.sublime-package'):
        package_name = package_name[:-16]
      return package_name
  except:
    pass
  return "SublimeRC"

def get_user_data_dir():
  path = os.path.join(sublime.packages_path(), "User", get_package_name())
  os.makedirs(path, exist_ok=True)
  return path

def get_user_api_definitions_path():
  return os.path.join(get_user_data_dir(), "api_definitions.json")

class PopupStyler(object):
  _cache = {}
  _last_gc = 0
  __slots__ = ('view', 'color_scheme', 'font_size', 'ui_scale', 'font_scale', 'styles')

  def __init__(self, view):
    self.view = view
    self.color_scheme = view.settings().get("color_scheme", "")
    self.font_size = view.settings().get("font_size", 12)
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    self.ui_scale = settings.get("popup_ui_scale", 1.0) if settings else 1.0
    self.font_scale = settings.get("popup_font_scale", 0.92) if settings else 0.92
    if len(self._cache) > 10 and time.time() - self._last_gc > 60:
      self._cache.clear()
      PopupStyler._last_gc = time.time()
    cache_key = (self.color_scheme, self.ui_scale, self.font_scale, POPUP_STYLE_VERSION)
    if cache_key in self._cache:
      self.styles = self._cache[cache_key]
      return
    styles = view.style()
    base_fg = styles.get("foreground", "#d4d4d4")
    base_bg = styles.get("background", "#1e1e1e")
    if _is_sublimerc_editor_scheme(self.color_scheme):
      base_fg = "#f5f5f5"
      base_bg = SUBLIMERC_POPUP_SURFACE
    def scope_color(scope, default=base_fg):
      style = view.style_for_scope(scope)
      return style.get("foreground", default) if style else default
    self.styles = {
      'text': base_fg,
      'background': base_bg,
      'border': self._blend(base_bg, base_fg, 0.12),
      'muted': self._blend(base_bg, base_fg, 0.45),
      'comment': scope_color("comment", "#6a9955"),
      'string': scope_color("string", "#ce9178"),
      'number': scope_color("constant.numeric", "#b5cea8"),
      'constant': scope_color("constant", "#569cd6"),
      'variable': scope_color("variable", "#9cdcfe"),
      'parameter': scope_color("variable.parameter", "#4fc3f7"),
      'keyword': scope_color("keyword", "#c586c0"),
      'storage': scope_color("storage.type", "#c586c0"),
      'function': scope_color("entity.name.function", "#dcdcaa"),
      'operator': scope_color("keyword.operator", "#d4d4d4"),
      'punctuation': scope_color("punctuation", "#d4d4d4"),
      'user_badge': self._blend(base_bg, "#b97a00", 0.7),
      'global_badge': self._blend(base_bg, "#4a5f6b", 0.7),
      'client_badge': self._blend(base_bg, "#3a8fa3", 0.7),
      'server_badge': self._blend(base_bg, "#5a8f5d", 0.7),
      'var_badge': self._blend(base_bg, "#a33527", 0.7),
      'func_badge': self._blend(base_bg, "#7a1f8a", 0.7),
    }
    if _is_sublimerc_editor_scheme(self.color_scheme):
      self.styles.update({
        'comment': "#6c7480",
        'string': "#aad94c",
        'number': "#ffcc66",
        'constant': "#d2a6ff",
        'variable': "#73d0ff",
        'parameter': "#73d0ff",
        'keyword': "#ffad66",
        'storage': "#ffad66",
        'function': "#ffd173",
        'operator': "#f29e74",
        'punctuation': "#f29e74",
      })
    self._cache[cache_key] = self.styles

  def _blend(self, bg, fg, alpha):
    try:
      bg = bg.lstrip('#')
      fg = fg.lstrip('#')
      if len(bg) == 3:
        bg = bg[0]*2 + bg[1]*2 + bg[2]*2
      if len(fg) == 3:
        fg = fg[0]*2 + fg[1]*2 + fg[2]*2
      bg_r, bg_g, bg_b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
      fg_r, fg_g, fg_b = int(fg[0:2], 16), int(fg[2:4], 16), int(fg[4:6], 16)
      r = int(bg_r * (1 - alpha) + fg_r * alpha)
      g = int(bg_g * (1 - alpha) + fg_g * alpha)
      b = int(bg_b * (1 - alpha) + fg_b * alpha)
      return '#{:02x}{:02x}{:02x}'.format(r, g, b)
    except:
      return bg

  def fs(self, base):
    return int(base * self.font_scale * self.ui_scale)

  def px(self, base):
    return int(base * self.ui_scale)

  def c(self, key):
    return self.styles.get(key, "#d4d4d4")

_highlight_cache = {}

def _escape_html(text):
  return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def _regex_highlight_gscript(code, view):
  styler = PopupStyler(view)
  c = styler.c
  token_re = re.compile(
    r'(?P<comment>//[^\n]*|/\*.*?\*/)'
    r'|(?P<string>"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')'
    r'|(?P<number>\b\d+(?:\.\d+)?\b)'
    r'|(?P<keyword>\b(?:function|public|private|if|else|for|while|do|switch|case|default|break|continue|return|new|delete|true|false|null)\b)'
    r'|(?P<func>\b[A-Za-z_][A-Za-z0-9_]*(?=\s*\())'
    r'|(?P<variable>\b(?:this|temp|player|server|serverr|client|clientr)\.[A-Za-z_][A-Za-z0-9_]*|\btemp\.[A-Za-z_][A-Za-z0-9_]*|\$[A-Za-z_][A-Za-z0-9_]*)'
    r'|(?P<operator>[{}()[\].,;:+\-*/%=!<>@&|]+)',
    re.S
  )
  color_map = {
    'comment': c('comment'),
    'string': c('string'),
    'number': c('number'),
    'keyword': c('keyword'),
    'func': c('function'),
    'variable': c('variable'),
    'operator': c('operator'),
  }
  result = []
  pos = 0
  for match in token_re.finditer(code):
    if match.start() > pos:
      result.append(_escape_html(code[pos:match.start()]))
    kind = match.lastgroup
    text = _escape_html(match.group(0))
    result.append('<span style="color:{0}">{1}</span>'.format(color_map.get(kind, c('text')), text))
    pos = match.end()
  if pos < len(code):
    result.append(_escape_html(code[pos:]))
  return ''.join(result)

def syntax_highlight_gscript(code, view=None):
  if not code or not view:
    return _escape_html(code)
  cache_key = (code[:128], view.settings().get("color_scheme", ""))
  cached = _highlight_cache.get(cache_key)
  if cached is not None:
    return cached
  if _is_sublimerc_editor_scheme(view.settings().get("color_scheme", "")):
    html = _regex_highlight_gscript(code, view)
    _highlight_cache[cache_key] = html
    return html
  window = sublime.active_window()
  if not window:
    return _regex_highlight_gscript(code, view)
  temp_view = None
  try:
    temp_view = window.new_file(flags=sublime.TRANSIENT)
    temp_view.set_scratch(True)
    temp_view.set_read_only(False)
    package_name = get_package_name()
    syntax_path = 'Packages/{}/gscript.sublime-syntax'.format(package_name)
    temp_view.set_syntax_file(syntax_path)
    temp_view.run_command('append', {'characters': 'x', 'scroll_to_end': False})
    temp_view.sel().clear()
    temp_view.sel().add(sublime.Region(0, 1))
    start_time = time.time()
    while time.time() - start_time < 0.1:
      if 'source.gscript' in temp_view.scope_name(0):
        break
      time.sleep(0.005)
    temp_view.run_command('select_all')
    temp_view.run_command('right_delete')
    temp_view.run_command('append', {'characters': code, 'scroll_to_end': False})
    result = []
    i = 0
    n = len(code)
    append = result.append
    escape_table = str.maketrans({'&': '&amp;', '<': '&lt;', '>': '&gt;'})
    while i < n:
      scope = temp_view.scope_name(i)
      j = i + 1
      while j < n and j - i < 50:
        if temp_view.scope_name(j) != scope:
          break
        j += 1
      styler = PopupStyler(view)
      styles = styler.styles
      color = None
      if "comment" in scope:
        color = styles['comment']
      elif "string" in scope:
        color = styles['string']
      elif "constant.numeric" in scope:
        color = styles['number']
      elif "constant" in scope:
        color = styles['constant']
      elif "variable.parameter" in scope:
        color = styles['parameter']
      elif "variable" in scope:
        color = styles['variable']
      elif "keyword" in scope or "storage" in scope:
        color = styles['keyword']
      elif "entity.name.function" in scope:
        color = styles['function']
      elif "keyword.operator" in scope or "punctuation" in scope:
        color = styles['operator']
      text = code[i:j].translate(escape_table)
      if color:
        append('<span style="color:{0}">{1}</span>'.format(color, text))
      else:
        append(text)
      i = j
    html = ''.join(result)
    if '<span style="color:' not in html:
      html = _regex_highlight_gscript(code, view)
    if len(_highlight_cache) > 50:
      first_key = next(iter(_highlight_cache))
      del _highlight_cache[first_key]
    _highlight_cache[cache_key] = html
    return html
  finally:
    if temp_view and temp_view.window():
      window.focus_view(temp_view)
      window.run_command("close_file")

class GScriptLspListener(sublime_plugin.ViewEventListener):
  api_definitions = None
  _completion_cache = {}
  _FUNC_PATTERN = re.compile(r'(?:public\s+|private\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)')
  _PARAM_PATTERN = re.compile(r'function\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(([^)]*)\)')

  @classmethod
  def is_applicable(cls, settings):
    syntax = settings.get('syntax')
    return syntax and 'gscript.sublime-syntax' in syntax

  def __init__(self, view):
    super(GScriptLspListener, self).__init__(view)
    self.document_functions = {}
    self.parse_timer = None
    self._last_content_hash = None
    self.parse_document_functions()

  def parse_document_functions(self):
    content = self.view.substr(sublime.Region(0, self.view.size()))
    content_hash = hash(content[:8192])
    if self._last_content_hash == content_hash:
      return
    self._last_content_hash = content_hash
    self.document_functions.clear()
    clientside_marker = content.find('//#CLIENTSIDE')
    for match in self._FUNC_PATTERN.finditer(content):
      func_name = match.group(1)
      params_str = match.group(2).strip()
      params = [p.strip() for p in params_str.split(',') if p.strip()] if params_str else []
      func_scope = 'clientside' if (clientside_marker != -1 and match.start() > clientside_marker) else ('serverside' if clientside_marker != -1 else 'document')
      line_num = content[:match.start()].count('\n')
      self.document_functions[func_name] = {
        'name': func_name,
        'params': params,
        'returns': 'void',
        'description': 'User-defined function in current script',
        'scope': func_scope,
        'is_custom': True,
        'line': line_num
      }

  @staticmethod
  def _server_object_names():
    if not _has_server_objects:
      return [], [], []
    try:
      plugin = _main.GPlugin
      def unique_names(values):
        by_lower = {}
        for value in values:
          name = str(value or '').strip()
          if name:
            by_lower.setdefault(name.lower(), name)
        return sorted(by_lower.values(), key=lambda item: item.lower())
      npcs = unique_names(npc.get('name', '') for npc in getattr(plugin, 'npcs', []))
      classes = unique_names(getattr(plugin, 'classes', []))
      weapons = unique_names(getattr(plugin, 'weapons', []))
      return npcs, classes, weapons
    except Exception:
      return [], [], []

  @classmethod
  def _server_object_cache_key(cls):
    npcs, classes, weapons = cls._server_object_names()
    return (len(npcs), len(classes), len(weapons), hash(tuple(npcs[:20] + classes[:20] + weapons[:20])))

  @staticmethod
  def _server_object_completion(name, annotation, detail, kind, in_string=False):
    snippet = name if in_string else name
    return sublime.CompletionItem.snippet_completion(
      trigger=name,
      snippet=snippet,
      annotation=annotation,
      kind=kind,
      details=detail
    )

  @classmethod
  def _server_object_completions(cls, prefix, in_string=False):
    prefix_lower = (prefix or "").lower()
    npcs, classes, weapons = cls._server_object_names()
    def matches(name):
      name_lower = name.lower()
      return name_lower.startswith(prefix_lower) or name_lower.rsplit('/', 1)[-1].startswith(prefix_lower)
    completions = []
    for name in npcs:
      if matches(name):
        completions.append(cls._server_object_completion(name, "NPC", "NPC database object on the connected server", (sublime.KIND_ID_NAMESPACE, "n", "NPC"), in_string))
    for name in classes:
      if matches(name):
        completions.append(cls._server_object_completion(name, "CLASS", "Class on the connected server", (sublime.KIND_ID_TYPE, "c", "Class"), in_string))
    for name in weapons:
      if matches(name):
        completions.append(cls._server_object_completion(name, "WEAPON", "Weapon on the connected server", (sublime.KIND_ID_VARIABLE, "w", "Weapon"), in_string))
    return completions

  @classmethod
  def load_api_definitions(cls):
    if cls.api_definitions is None:
      try:
        json_path = get_user_api_definitions_path()
        if not os.path.exists(json_path):
          cls.api_definitions = {}
          sublime.status_message("SublimeRC API definitions not downloaded yet; run RC: Update LSP Definitions")
          return cls.api_definitions
        with open(json_path, 'r', encoding='utf-8') as f:
          cls.api_definitions = json.load(f)
        sublime.status_message("Loaded {0} API definitions".format(len(cls.api_definitions)))
      except Exception:
        cls.api_definitions = {}
    return cls.api_definitions

  def _build_hover_html(self, info, word, example, point):
    styler = PopupStyler(self.view)
    c, fs, px = styler.c, styler.fs, styler.px
    is_variable = word.startswith('$')
    if is_variable:
      signature = '<span style="color:{0}">{1}</span>'.format(c('variable'), word)
    else:
      params = info.get('params', [])
      if params:
        param_items = []
        for p in params:
          param_items.append('<span style="color:{0}">{1}</span>'.format(c('parameter'), p))
        param_str = ', '.join(param_items)
      else:
        param_str = ''
      signature = '<span style="color:{0}">{1}</span>({2})'.format(c('function'), word, param_str)
    badges = []
    scope = info.get('scope', '')
    if scope:
      badge_map = {
        'document': ('#b97a00', 'USER'),
        'global': ('#4a5f6b', 'GLOBAL'),
        'clientside': ('#3a8fa3', 'CLIENT'),
        'serverside': ('#5a8f5d', 'SERVER')
      }
      bg, text = badge_map.get(scope, ('#81c784', 'UNDEFINED'))
      badges.append("<span style='background-color: {}; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: {}px; font-weight: bold; margin-right: 6px;'>{}</span>".format(bg, fs(10), text))
    if is_variable:
      badges.append("<span style='background-color: {}; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: {}px; font-weight: bold;'>VARIABLE</span>".format('#a33527', fs(10)))
    else:
      badges.append("<span style='background-color: {}; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: {}px; font-weight: bold;'>FUNCTION</span>".format('#7a1f8a', fs(10)))
    html_parts = []
    html_parts.append('<div style="padding:{0}px;font-family:system-ui,-apple-system,sans-serif;background:{1};color:{2}">'.format(
      px(10), c('background'), c('text')))
    html_parts.append('<div style="font-family:Consolas,Monaco,monospace;font-size:{0}px;margin-bottom:{1}px">'.format(
      fs(13), px(8)))
    html_parts.append('<strong>{0}</strong>'.format(signature))
    html_parts.append('</div>')
    returns = info.get('returns', 'void')
    if returns and returns != 'void':
      bg_blend = styler._blend(c('background'), c('text'), 0.1)
      html_parts.append('<div style="font-size:{0}px;color:{1};margin-bottom:{2}px">Returns: <code style="background:{3};padding:2px {4}px;border-radius:3px;color:{5}">{6}</code></div>'.format(
        fs(11), c('muted'), px(8), bg_blend, px(6), c('constant'), returns))
    if badges or (not info.get('is_custom', False) and not word.startswith('$')):
      badge_html = ''.join(badges)
      if not info.get('is_custom', False) and not word.startswith('$'):
        link_color = styler._blend(c('text'), c('muted'), 0.3)
        safe_word = word.replace('"', '\\"').replace("'", "\\'")[:50]
        badge_html += '<a href=\'subl:rc_open_wiki_search {{"name":"{0}"}}\' style="color:{1};text-decoration:none;cursor:pointer;font-size:{2}px" title="Search Wiki">&nbsp;&#x1f50d; Search Wiki</a>'.format(
          safe_word, link_color, fs(12))
      html_parts.append('<div style="margin-bottom:{0}px">{1}</div>'.format(px(8), badge_html))
    desc = info.get('description', '').replace('\n', '<br>')[:300]
    if desc and desc != "No matching script function found!":
      html_parts.append('<div style="font-size:{0}px;line-height:1.5;margin:{1}px 0;padding-top:{2}px;border-top:1px solid {3}">{4}</div>'.format(
        fs(12), px(10), px(8), c('border'), desc))
    html_parts.append('<div style="margin-top:{0}px;padding-top:{1}px;border-top:1px solid {2}">'.format(
      px(10), px(8), c('border')))
    html_parts.append('<div style="font-size:{0}px;color:{1};margin-bottom:{2}px">Example:</div>'.format(
      fs(11), c('muted'), px(4)))
    if example:
      highlighted = syntax_highlight_gscript(example.strip(), self.view)
      bg_blend = styler._blend(c('background'), c('text'), 0.08)
      html_parts.append('<pre style="background:{0};padding:{1}px;border-radius:4px;margin:0;font-family:Consolas,Monaco,monospace;font-size:{2}px;overflow-x:auto;white-space:pre-wrap">{3}</pre>'.format(
        bg_blend, px(8), fs(14), highlighted))
    else:
      html_parts.append('<div style="color:{0};font-style:italic;font-size:{1}px">(no example)</div>'.format(
        c('muted'), fs(11)))
    html_parts.append('</div></div>')
    return ''.join(html_parts)

  def on_query_completions(self, prefix, locations):
    if not self.view.match_selector(locations[0], "source.gscript"):
      return None
    definitions = self.load_api_definitions()
    if not definitions:
      definitions = {}
    cache_key = (prefix.lower(), len(definitions), self._server_object_cache_key())
    has_server_objects = any(self._server_object_cache_key()[:3])
    cached = None if has_server_objects else self._completion_cache.get(cache_key)
    if cached is not None:
      return cached
    point = locations[0]
    if self.view.match_selector(point, "string.quoted") and _has_player_completions:
      line_region = self.view.line(point)
      line_text = self.view.substr(line_region)
      col = point - line_region.begin()
      start = col
      while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '_'):
        start -= 1
      prefix_in_string = line_text[start:col]
      player_completions = _lsp_players.get_player_completions(prefix_in_string)
      if player_completions:
        result = sublime.CompletionList(player_completions, flags=sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
        if not has_server_objects:
          self._completion_cache[cache_key] = result
        return result
    all_definitions = {}
    all_definitions.update(self.document_functions)
    all_definitions.update(definitions)
    line_region = self.view.line(point)
    line_text = self.view.substr(line_region)
    col = point - line_region.begin()
    start = col
    while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '$_:'):
      start -= 1
    expanded_prefix = line_text[start:col]
    if expanded_prefix:
      prefix = expanded_prefix
    prefix_lower = prefix.lower()
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    max_results = settings.get("completion_max_results_short", 50) if len(prefix) < 2 else settings.get("completion_max_results_long", 200)
    completions = []
    completions.extend(self._server_object_completions(prefix, in_string=False))
    result_count = 0
    for name, info in all_definitions.items():
      if result_count >= max_results:
        break
      if name.lower().startswith(prefix_lower):
        result_count += 1
        params = info.get('params', [])
        returns = info.get('returns', 'void')
        description = info.get('description', '')
        scope = info.get('scope', '')
        is_custom = info.get('is_custom', False)
        item_type = info.get('type', '')
        is_variable = name.startswith('$')
        annotation = ""
        if is_custom or scope:
          if scope == 'document' or is_custom:
            annotation = 'USER'
          elif scope == 'global':
            annotation = 'GLOBAL'
          elif 'client' in scope.lower():
            annotation = 'CLIENTSIDE'
          elif 'server' in scope.lower():
            annotation = 'SERVERSIDE'
          else:
            annotation = 'UNDEFINED'
        if is_variable:
          insert_text = name
          kind = sublime.KIND_VARIABLE
        elif not params:
          insert_text = "{0}() {{".format(name)
          kind = sublime.KIND_FUNCTION
        else:
          placeholders = []
          for i, param in enumerate(params):
            label = str(param).replace('$', '\\$').replace('}', '\\}')
            if i == 0 and any(word in label.lower() for word in ('weapon', 'class', 'npc', 'name')):
              label = '"{}"'.format(label.strip('"'))
            placeholders.append("${{{}:{}}}".format(i + 1, label))
          insert_text = "{0}({1})".format(name, ", ".join(placeholders))
          kind = sublime.KIND_FUNCTION
        completion_item = sublime.CompletionItem.snippet_completion(
          trigger=name,
          snippet=insert_text,
          annotation=annotation,
          kind=kind,
          details=description.replace('\n', ' ')[:100] + '...' if len(description) > 100 else description.replace('\n', ' ')
        )
        completions.append(completion_item)
    result = sublime.CompletionList(completions, flags=sublime.INHIBIT_WORD_COMPLETIONS)
    if not has_server_objects:
      self._completion_cache[cache_key] = result
    return result

  def on_hover(self, point, hover_zone):
    self.view.erase_regions("rc_hover_underline")
    if hover_zone != sublime.HOVER_TEXT:
      return
    if not self.view.match_selector(point, "source.gscript"):
      return
    line_region = self.view.line(point)
    line_text = self.view.substr(line_region)
    func_match = self._PARAM_PATTERN.search(line_text)
    if func_match:
      param_start = func_match.start(1)
      param_end = func_match.end(1)
      col = point - line_region.begin()
      if param_start <= col <= param_end:
        return
    if '//#CLIENTSIDE' in line_text:
      styler = PopupStyler(self.view)
      c, fs, px = styler.c, styler.fs, styler.px
      html = """
      <div style="padding:{px10}px;font-family:system-ui,-apple-system,sans-serif;background:{bg};color:{fg}">
        <div style="font-family:Consolas,Monaco,monospace;font-size:{fs13}px;color:{keyword};margin-bottom:{px8}px">
          <strong>//#CLIENTSIDE</strong>
        </div>
        <div style="font-size:{fs12}px;line-height:1.5;margin:{px10}px 0;padding-top:{px8}px;border-top:1px solid {border}">
          Marks the divider between server-side and client-side code. Functions after this marker are executed on the client.
        </div>
      </div>
      """.format(
        px10=px(10), px8=px(8),
        bg=styler.c('background'), fg=styler.c('text'),
        fs13=fs(13), fs12=fs(12),
        keyword=styler.c('keyword'),
        border=styler.c('border')
      )
      max_width_main, _, max_height_main, _ = _get_popup_dimensions()
      self.view.show_popup(
        html,
        location=point,
        max_width=max_width_main,
        max_height=max_height_main,
        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY
      )
      return
    col = point - line_region.begin()
    start = col
    end = col
    while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '$_:'):
      start -= 1
    while end < len(line_text) and (line_text[end].isalnum() or line_text[end] in '$_:'):
      end += 1
    word = line_text[start:end].strip()
    if not word:
      return
    if _has_player_completions and word:
      player_info = _lsp_players.get_player_info(word)
      if player_info:
        styler = PopupStyler(self.view)
        c, fs, px = styler.c, styler.fs, styler.px
        badges_html = ''.join([
          "<span style='background-color:{0};color:#fff;padding:2px {1}px;border-radius:3px;font-size:{2}px;font-weight:bold;margin-right:{3}px'>{4}</span>".format(
            '#4caf50' if badge == 'RC' else '#2196f3', px(8), fs(10), px(4), badge
          ) for badge in player_info['badges']
        ])
        html = """
        <div style="padding:{px10}px;font-family:system-ui,-apple-system,sans-serif;background:{bg};color:{fg}">
          <div style="margin-bottom:{px8}px">{badges}</div>
          <div style="font-family:Consolas,Monaco,monospace;font-size:{fs13}px;color:{keyword};margin-bottom:{px8}px">
            <strong>{account}</strong>
          </div>
          <div style="font-size:{fs12}px;line-height:1.8;margin:{px10}px 0;padding-top:{px8}px;border-top:1px solid {border}">
            <div><strong>Nickname:</strong> {nick}</div>
            <div><strong>Level:</strong> {level}</div>
            <div><strong>Player ID:</strong> {player_id}</div>
          </div>
        </div>
        """.format(
          px10=px(10), px8=px(8),
          bg=styler.c('background'), fg=styler.c('text'),
          fs13=fs(13), fs12=fs(12),
          keyword=styler.c('keyword'),
          border=styler.c('border'),
          badges=badges_html,
          account=player_info['account'],
          nick=player_info['nick'],
          level=player_info['level'],
          player_id=player_info['id']
        )
        _, max_width_compact, _, max_height_compact = _get_popup_dimensions()
        self.view.show_popup(
          html,
          location=point,
          max_width=max_width_compact,
          max_height=max_height_compact,
          flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY
        )
        return
    definitions = self.load_api_definitions()
    if not definitions:
      definitions = {}
    all_definitions = {}
    all_definitions.update(self.document_functions)
    all_definitions.update(definitions)
    word_lower = word.lower()
    info = None
    for name, data in all_definitions.items():
      if name.lower() == word_lower:
        info = data
        break
    if info is None:
      return
    word_region = sublime.Region(line_region.begin() + start, line_region.begin() + end)
    self.view.add_regions("rc_hover_underline", [word_region], "entity.name.function", "",
      sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SOLID_UNDERLINE)
    example = info.get('example', '')
    html = self._build_hover_html(info, word, example, point)
    if not isinstance(html, str) or not html.strip():
      html = '<div style="padding:10px;color:#f44336;background:#ffebee;font-family:system-ui">Documentation unavailable</div>'
    self.view.hide_popup()
    max_width_main, _, max_height_main, _ = _get_popup_dimensions()
    try:
      max_width_main = int(max_width_main)
      max_height_main = int(max_height_main)
    except (TypeError, ValueError):
      max_width_main, max_height_main = 600, 600
    def show():
      if not self.view or not self.view.is_valid():
        return
      self.view.hide_popup()
      self.view.show_popup(
        html,
        flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY | sublime.COOPERATE_WITH_AUTO_COMPLETE,
        location=point,
        max_width=max_width_main,
        max_height=max_height_main
      )
    sublime.set_timeout(show, 10)
    return True

  def show_param_hint(self):
    if not self.view or not self.view.is_valid() or not self.view.sel():
      self.view.hide_popup()
      return
    if not self.view.match_selector(self.view.sel()[0].begin(), "source.gscript"):
      self.view.hide_popup()
      return
    definitions = self.load_api_definitions()
    if not definitions:
      definitions = {}
    all_definitions = {}
    all_definitions.update(self.document_functions)
    all_definitions.update(definitions)
    point = self.view.sel()[0].begin()
    line_region = self.view.line(point)
    line_text = self.view.substr(line_region)
    col = point - line_region.begin()
    if col > 0:
      paren_pos = line_text.rfind('(', 0, col)
      if paren_pos != -1:
        close_pos = line_text.find(')', paren_pos)
        if close_pos == -1 or close_pos >= col:
          start = paren_pos - 1
          while start >= 0 and (line_text[start].isalnum() or line_text[start] == '_'):
            start -= 1
          start += 1
          func_name = line_text[start:paren_pos].strip()
          if func_name:
            func_name_lower = func_name.lower()
            info = None
            for name, data in all_definitions.items():
              if name.lower() == func_name_lower:
                info = data
                break
            if info is None:
              return
            params = info.get('params', [])
            returns = info.get('returns', 'void')
            description = info.get('description', '')
            example = info.get('example', '')
            scope = info.get('scope', '')
            if params:
              param_text = line_text[paren_pos + 1:col]
              comma_count = param_text.count(',')
              current_param = comma_count if comma_count < len(params) else len(params) - 1
              param_list = []
              for i, param in enumerate(params):
                if i == current_param:
                  param_list.append("<strong style='color:#ffd700;text-decoration:underline'>{0}</strong>".format(param))
                else:
                  param_list.append("<span style='color:#4ec9b0'>{0}</span>".format(param))
              param_str = ', '.join(param_list)
              styler = PopupStyler(self.view)
              c, fs, px = styler.c, styler.fs, styler.px
              bg_blend = styler._blend(c('background'), c('text'), 0.15)
              hint_parts = []
              hint_parts.append('<div style="padding:{0}px;font-family:system-ui,-apple-system,sans-serif;background:{1}">'.format(px(8), c('background')))
              hint_parts.append('<div style="font-family:Consolas,Monaco,monospace;font-size:{0}px;margin-bottom:{1}px">'.format(fs(13), px(6)))
              hint_parts.append('<span style="color:{0}">{1}</span><span style="color:{2}">(</span>{3}<span style="color:{2}">)</span>'.format(
                c('function'), func_name, c('text'), param_str))
              hint_parts.append('</div>')
              if scope:
                badge_map = {
                  'document': ('#b97a00', 'USER'),
                  'global': ('#4a5f6b', 'GLOBAL'),
                  'clientside': ('#3a8fa3', 'CLIENT'),
                  'serverside': ('#5a8f5d', 'SERVER')
                }
                bg, text = badge_map.get(scope, ('#81c784', 'UNDEFINED'))
                hint_parts.append('<div style="margin-bottom:{0}px">'.format(px(6)))
                hint_parts.append("<span style='background: {}; color: #fff; padding: 2px 6px; border-radius: 3px; font-size: {}px; font-weight: bold;'>{}</span>".format(bg, fs(9), text))
                hint_parts.append('</div>')
              hint_parts.append('<div style="font-size:{0}px;color:{1};margin-bottom:{2}px">'.format(fs(11), c('muted'), px(4)))
              hint_parts.append('Parameter {0}/{1} &bull; Returns: <span style="color:{2}">{3}</span>'.format(
                current_param + 1, len(params), c('constant'), returns))
              hint_parts.append('</div>')
              if description and description != "No matching script function found!":
                short_desc = description[:100] + '...' if len(description) > 100 else description
                hint_parts.append('<div style="font-size:{0}px;color:{1};padding-top:{2}px;border-top:1px solid {3}">{4}</div>'.format(
                  fs(11), c('text'), px(6), c('border'), short_desc))
              hint_parts.append('<div style="margin-top:{0}px;padding-top:{1}px;border-top:1px solid {2}">'.format(px(6), px(6), c('border')))
              hint_parts.append('<div style="font-size:{0}px;color:{1};margin-bottom:{2}px">Example:</div>'.format(fs(10), c('muted'), px(3)))
              if example:
                highlighted = syntax_highlight_gscript(example.strip(), self.view)
                hint_parts.append('<pre style="background:{0};padding:{1}px;border-radius:3px;margin:0;font-family:Consolas,Monaco,monospace;font-size:{2}px;white-space:pre-wrap">{3}</pre>'.format(
                  bg_blend, px(6), fs(11), highlighted))
              else:
                hint_parts.append('<div style="color:{0};font-style:italic;font-size:{1}px">(no example)</div>'.format(c('muted'), fs(10)))
              hint_parts.append('</div></div>')
              hint = ''.join(hint_parts)
              max_width_main, _, max_height_main, _ = _get_popup_dimensions()
              self.view.show_popup(
                hint,
                flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY | sublime.COOPERATE_WITH_AUTO_COMPLETE,
                location=point,
                max_width=max_width_main,
                max_height=max_height_main
              )
              return
    self.view.hide_popup()

  def on_post_save_async(self):
    self.parse_document_functions()

  def schedule_parse(self):
    if self.parse_timer:
      try:
        sublime.cancel_timeout(self.parse_timer)
      except:
        pass
    self.parse_timer = sublime.set_timeout(lambda: self.parse_document_functions(), 1000)

  def on_modified_async(self):
    self.schedule_parse()

  def on_selection_modified_async(self):
    if self.view.window() and self.view.window().active_panel():
      return
    self.show_param_hint()

  def on_load(self):
    self.load_api_definitions()

class RcGotoDefinitionCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    point = self.view.sel()[0].begin()
    line_region = self.view.line(point)
    line_text = self.view.substr(line_region)
    col = point - line_region.begin()
    start, end = col, col
    while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in '$_:'):
      start -= 1
    while end < len(line_text) and (line_text[end].isalnum() or line_text[end] in '$_:'):
      end += 1
    word = line_text[start:end].strip()
    if not word:
      return
    listener = GScriptLspListener.for_view(self.view) if hasattr(GScriptLspListener, 'for_view') else None
    doc_funcs = {}
    for listener_inst in GScriptLspListener._instances if hasattr(GScriptLspListener, '_instances') else []:
      if listener_inst.view.id() == self.view.id():
        doc_funcs = listener_inst.document_functions
        break
    if not doc_funcs:
      content = self.view.substr(sublime.Region(0, self.view.size()))
      pattern = GScriptLspListener._FUNC_PATTERN
      clientside_marker = content.find('//#CLIENTSIDE')
      for match in pattern.finditer(content):
        func_name = match.group(1)
        line_num = content[:match.start()].count('\n')
        doc_funcs[func_name] = {'line': line_num}
    word_lower = word.lower()
    for name, data in doc_funcs.items():
      if name.lower() == word_lower and 'line' in data:
        pt = self.view.text_point(data['line'], 0)
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(pt))
        self.view.show_at_center(pt)
        line_reg = self.view.line(pt)
        line_text = self.view.substr(line_reg)
        m = GScriptLspListener._FUNC_PATTERN.search(line_text)
        if m:
          name_start = line_reg.begin() + m.start(1)
          name_end = line_reg.begin() + m.end(1)
          dest_region = sublime.Region(name_start, name_end)
          self.view.add_regions("rc_goto_underline", [dest_region], "entity.name.function", "",
            sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SOLID_UNDERLINE)
          sublime.set_timeout(lambda: self.view.erase_regions("rc_goto_underline"), 1500)
        return
    sublime.status_message("No definition found for '{}'".format(word))

class RcUpdateLspDefinitionsCommand(sublime_plugin.WindowCommand):
  def run(self):
    print("[LSP UPDATE] Starting LSP definitions update...")
    sublime.status_message("Downloading LSP definitions...")
    threading.Thread(target=self.download_definitions).start()

  def download_definitions(self):
    try:
      import urllib.request
      url = "https://api.gscript.dev".strip()
      req = urllib.request.Request(url, headers={'User-Agent': 'SublimeRC/1.0'})
      response = urllib.request.urlopen(req, timeout=30)
      data = response.read()
      print("[LSP UPDATE] Downloaded {0} bytes".format(len(data)))
      json_path = get_user_api_definitions_path()
      print("[LSP UPDATE] Saving to: {0}".format(json_path))
      with open(json_path, 'wb') as f:
        f.write(data)
      GScriptLspListener.api_definitions = None
      GScriptLspListener.load_api_definitions()
      sublime.set_timeout(lambda: sublime.status_message("LSP definitions updated successfully! {0} definitions loaded".format(len(GScriptLspListener.api_definitions))), 0)
    except Exception as e:
      print("[LSP UPDATE] Error: {0}".format(str(e)))
      import traceback
      traceback.print_exc()
      err_str = str(e)
      if '403' in err_str or 'Forbidden' in err_str:
        msg = "Access denied (403). API may require auth or changed."
      else:
        msg = err_str
      sublime.set_timeout(lambda: sublime.status_message("LSP update failed: {0}".format(msg)), 0)

class RcOpenWikiSearchCommand(sublime_plugin.WindowCommand):
  def run(self, name):
    import urllib.parse
    import webbrowser
    if not name or not isinstance(name, str):
      sublime.status_message("Invalid search term")
      return
    sanitized = ''.join(c for c in name if c.isalnum() or c == '_')
    if not sanitized or len(sanitized) > 100:
      sublime.status_message("Cannot search invalid name: '{0}'".format(name[:20]))
      return
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    engine = settings.get("wiki_search_engine", "gscript")
    if engine == "graal":
      base_url = "https://graalonline.net/index.php"
    else:
      base_url = "https://wiki.gscript.dev/index.php"
    params = {'title': 'Special:Search', 'search': sanitized, 'go': 'Go'}
    full_url = "{0}?{1}".format(base_url, urllib.parse.urlencode(params))
    try:
      webbrowser.open(full_url)
      sublime.status_message("Opened {0} wiki search for '{1}'".format(
        "GraalOnline" if engine == "graal" else "GScript", sanitized))
    except Exception as e:
      sublime.status_message("Browser error: {0}".format(str(e)[:50]))
      print("[WIKI SEARCH] Error: {0}".format(e))

def _ensure_default_settings():
  settings = sublime.load_settings("SublimeRC.sublime-settings")
  defaults = {
    "popup_ui_scale": 1,
    "popup_font_scale": 1,
    "popup_max_width": 800,
    "popup_max_width_compact": 500,
    "popup_max_height": 700,
    "popup_max_height_compact": 500,
    "completion_max_results_short": 50,
    "completion_max_results_long": 200,
    "wiki_search_engine": "gscript",
  }
  needs_save = False
  for key, default_val in defaults.items():
    current_val = settings.get(key)
    if current_val is None:
      settings.set(key, default_val)
      needs_save = True
  if needs_save:
    sublime.save_settings("SublimeRC.sublime-settings")
    print("[SublimeRC] Default settings initialized")

def plugin_loaded():
  _ensure_default_settings()
  GScriptLspListener.load_api_definitions()
