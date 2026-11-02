"""Writing a JSON file back the way it was laid out, so a save makes a small diff in Dungeon's history.

Dungeon's data files are partly hand-compacted (the travel files keep each stop and road on one line), and
json.dumps would spread every one of them over many lines. `learn` reads which objects and lists the old text kept on
one line, by their path with list positions as `*` (so a new road sits on one line like the old ones), and `dumps`
writes the new data that way, expanded everywhere else. Where a file does both for one path, short ones stay on one
line.
"""
import json

Path = tuple[str, ...]


class Style:
    """What a file's layout says: the widest each path was kept on one line, and the paths also spread out."""

    def __init__(self):
        self.widths: dict[Path, int] = {}
        self.spread: set[Path] = set()

    def inline(self, path: Path, width: int) -> bool:
        """One line where the file always kept this path on one line, or (where it did both) when no wider than the
        widest it kept on one line."""
        if path not in self.widths:
            return False
        return path not in self.spread or width <= self.widths[path]


def string_end(text: str, at: int) -> int:
    """Where the JSON string starting at `at` ends (its closing quote)."""
    end = at + 1
    while text[end] != '"':
        end += 2 if text[end] == '\\' else 1
    return end


def learn(text: str) -> Style:
    """How `text` lays out its objects and lists, by path. Empty ones teach nothing (they are always on one line)."""
    style = Style()
    stack: list[tuple[Path, int, str, int]] = []  # (path, line it opened on, '{' or '[', where it opened)
    line, at, key, path = 0, 0, None, ()
    while at < len(text):
        char = text[at]
        if char == '"':
            end = string_end(text, at)
            if stack and stack[-1][2] == '{' and text[end + 1:end + 40].lstrip().startswith(':'):
                key = json.loads(text[at:end + 1])
            at = end + 1
            continue
        if char == '\n':
            line += 1
        elif char in '{[':
            if stack:
                path = stack[-1][0] + (key if stack[-1][2] == '{' else '*',)
            else:
                path = ()
            stack.append((path, line, char, at))
            key = None
            if text[at + 1:].lstrip()[:1] in '}]':  # empty: skip to its end
                close = text.index('}' if char == '{' else ']', at + 1)
                line += text.count('\n', at, close)
                stack.pop()
                at = close + 1
                continue
        elif char in '}]':
            opened, started, _, start = stack.pop()
            if started == line:
                style.widths[opened] = max(style.widths.get(opened, 0), at + 1 - start)
            else:
                style.spread.add(opened)
        at += 1
    return style


def dumps(data: object, indent: int, style: Style | None = None) -> str:
    style = style or Style()
    pad = ' ' * indent

    def render(value: object, path: Path, level: int) -> str:
        if not isinstance(value, (dict, list)) or not value:
            return json.dumps(value, ensure_ascii=False)
        one_line = json.dumps(value, ensure_ascii=False)
        if style.inline(path, len(one_line)):
            return one_line
        inner = pad * (level + 1)
        if isinstance(value, dict):
            parts = [f'{inner}{json.dumps(key, ensure_ascii=False)}: {render(item, path + (key,), level + 1)}'
                     for key, item in value.items()]
            return '{\n' + ',\n'.join(parts) + '\n' + pad * level + '}'
        parts = [inner + render(item, path + ('*',), level + 1) for item in value]
        return '[\n' + ',\n'.join(parts) + '\n' + pad * level + ']'

    return render(data, (), 0) + '\n'


def rewritten(data: object, before: str | None, indent: int) -> str:
    """`data` as JSON text laid out like `before` (or plainly indented when there was nothing before)."""
    if not before:
        return json.dumps(data, indent=indent, ensure_ascii=False) + '\n'
    try:
        style = learn(before)
    except (IndexError, ValueError):
        style = Style()
    return dumps(data, indent, style)
