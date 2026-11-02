"""Maps as Mermaid flowcharts, both ways.

A map is a graph: nodes (with a label, the group they sit in, a kind and a position), groups (subgraphs) and links
(with a label). `text` writes it as a Mermaid flowchart anyone can paste into a Mermaid viewer; `parse` reads a
flowchart back, keeping positions from the graph it came from, since Mermaid text has no positions.

Only the flowchart subset a map needs is read: `subgraph id["Label"]` ... `end`, nodes as `id`, `id["Label"]`,
`id(["Label"])` or `id("Label")`, and links as `a --- b`, `a --> b`, `a ---|"label"| b` or `a -- "label" --- b`
(nodes may be declared inside a link). Anything else is reported by line number instead of guessed at.
"""
import re

from worldsmith.dungeon_format.errors import DomainError

ID = r'[A-Za-z0-9][A-Za-z0-9_-]*'
LABEL = r'(?:\["(?P<{0}>[^"]*)"\]|\(\["(?P<{0}r>[^"]*)"\]\)|\("(?P<{0}p>[^"]*)"\)|\[(?P<{0}b>[^\]"]*)\])'
NODE = re.compile(rf'^(?P<id>{ID})\s*{LABEL.format("l")}?$')
SUBGRAPH = re.compile(rf'^subgraph\s+(?P<id>{ID})\s*(?:\["(?P<label>[^"]*)"\]|\[(?P<bare>[^\]]*)\])?$')
ARROW = r'(?:<-->|-->|---|==>|===|-\.->|-\.-)'
LINK = re.compile(
    rf'^(?P<a>{ID})\s*{LABEL.format("al")}?\s*'
    rf'(?:--\s*"(?P<mid>[^"]*)"\s*{ARROW}|{ARROW}\s*(?:\|"?(?P<pipe>[^|"]*)"?\|)?)\s*'
    rf'(?P<b>{ID})\s*{LABEL.format("bl")}?$')
SHAPES = {'place': '(["{}"])', 'employer': '["{}"]', 'stop': '("{}")'}


def quoted(text: str) -> str:
    return str(text).replace('"', '#quot;')


def unquoted(text: str | None) -> str | None:
    return None if text is None else text.replace('#quot;', '"').strip()


def node_text(node: dict) -> str:
    return node['id'] + SHAPES.get(node.get('kind', ''), '["{}"]').format(quoted(node.get('label') or node['id']))


def text(graph: dict, direction: str = 'LR') -> str:
    lines = [f'flowchart {direction}']
    grouped: dict[str | None, list[dict]] = {}
    for node in graph['nodes']:
        grouped.setdefault(node.get('group'), []).append(node)
    for group in graph['groups']:
        lines.append(f'  subgraph {group["id"]}["{quoted(group.get("label") or group["id"])}"]')
        lines += [f'    {node_text(node)}' for node in grouped.pop(group['id'], [])]
        lines.append('  end')
    for nodes in grouped.values():  # nodes in no group, or in a group the graph does not list
        lines += [f'  {node_text(node)}' for node in nodes]
    for link in graph['links']:
        label = f'|"{quoted(link["label"])}"| ' if link.get('label') else ''
        lines.append(f'  {link["from"]} ---{label}{link["to"]}' if label else f'  {link["from"]} --- {link["to"]}')
    return '\n'.join(lines) + '\n'


def label_of(match: re.Match, name: str) -> str | None:
    for key in (name, f'{name}r', f'{name}p', f'{name}b'):
        if match.group(key) is not None:
            return unquoted(match.group(key))
    return None


SKIPPED = ('classDef ', 'class ', 'style ', 'linkStyle ', 'direction ', 'click ')


class Reader:
    """Reads a flowchart a line at a time."""

    def __init__(self, before: dict):
        self.old_nodes = {node['id']: node for node in before['nodes']}
        self.old_groups = {group['id']: group for group in before['groups']}
        self.nodes: dict[str, dict] = {}
        self.groups: dict[str, dict] = {}
        self.links: list[dict] = []
        self.problems: list[str] = []
        self.stack: list[str] = []

    def meet(self, node_id: str, label: str | None, declared: bool):
        old = self.old_nodes.get(node_id, {})
        node = self.nodes.setdefault(node_id, {**old, 'id': node_id, 'label': old.get('label') or node_id,
                                               'group': self.stack[-1] if self.stack else old.get('group')})
        if label is not None:
            node['label'] = label
        if declared:
            node['group'] = self.stack[-1] if self.stack else None

    def subgraph(self, found: re.Match):
        group_id = found['id']
        label = unquoted(found['label'] if found['label'] is not None else found['bare'])
        old = self.old_groups.get(group_id, {})
        self.groups[group_id] = {**old, 'id': group_id, 'label': label or old.get('label') or group_id}
        self.stack.append(group_id)

    def link(self, found: re.Match):
        self.meet(found['a'], label_of(found, 'al'), False)
        self.meet(found['b'], label_of(found, 'bl'), False)
        label = unquoted(found['mid'] if found['mid'] is not None else found['pipe'])
        self.links.append({'from': found['a'], 'to': found['b'], 'label': label or ''})

    def read(self, number: int, line: str):
        if not line or line.startswith('%%') or re.match(r'^(flowchart|graph)\b', line) or line.startswith(SKIPPED):
            return
        if line == 'end':
            if self.stack:
                self.stack.pop()
            else:
                self.problems.append(f'line {number}: "end" with no subgraph open')
        elif found := SUBGRAPH.match(line):
            self.subgraph(found)
        elif found := LINK.match(line):
            self.link(found)
        elif found := NODE.match(line):
            self.meet(found['id'], label_of(found, 'l'), True)
        else:
            self.problems.append(f'line {number}: not something a map understands: {line[:80]}')


def parse(source: str, before: dict | None = None) -> dict:
    """The graph a flowchart describes. Nodes and groups keep the position and kind they had in `before`; a node
    only named in a link takes its label and group from `before` too."""
    before = before or {'nodes': [], 'groups': [], 'links': []}
    reader = Reader(before)
    for number, raw in enumerate(source.splitlines(), start=1):
        reader.read(number, raw.strip().rstrip(';').strip())
    if reader.stack:
        reader.problems.append(f'subgraph {reader.stack[-1]} is never closed with "end"')
    clash = sorted(set(reader.nodes) & set(reader.groups))
    if clash:
        reader.problems.append(f'{", ".join(clash)} is used as both a node and a subgraph')
    if reader.problems:
        raise DomainError('The Mermaid text has problems: ' + '; '.join(reader.problems[:8]), 422, 'mermaid')
    return {**before, 'nodes': list(reader.nodes.values()), 'groups': list(reader.groups.values()),
            'links': reader.links}
