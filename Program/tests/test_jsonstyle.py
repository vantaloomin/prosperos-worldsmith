"""Saves keep a file's layout, so a Dungeon PR shows only what changed."""
import json

from worldsmith import jsonstyle

TRAVEL = '''{
 "about": "Roads.",
 "odds": {"none": 0, "low": 15},
 "nodes": [
  {"id": "kingswood", "name": "Kingswood", "map": {"x": 0.33, "y": 0.62}},
  {"id": "convila", "name": "Convila", "map": {"x": 0.31, "y": 0.66}}
 ],
 "routes": [
  {"from": "kingswood", "to": "convila", "hours": 8}
 ],
 "empty": [],
 "spots": [
  []
 ]
}
'''


def test_an_unchanged_file_is_written_back_byte_for_byte():
    assert jsonstyle.rewritten(json.loads(TRAVEL), TRAVEL, 1) == TRAVEL


def test_a_new_road_goes_on_one_line_like_the_others():
    data = json.loads(TRAVEL)
    data['routes'].append({'from': 'convila', 'to': 'eriane', 'hours': 6})
    text = jsonstyle.rewritten(data, TRAVEL, 1)
    assert '  {"from": "convila", "to": "eriane", "hours": 6}\n' in text
    assert text.count('\n') == TRAVEL.count('\n') + 1


def test_empty_lists_do_not_teach_one_line_and_mixed_paths_go_by_width():
    text = ('{\n "a": [\n  {"x": [1]},\n  {\n   "x": [\n    1,\n    2,\n    3333333333\n   ]\n  }\n ],\n'
            ' "b": [],\n "c": [\n  1\n ]\n}\n')
    assert jsonstyle.rewritten(json.loads(text), text, 1) == text
    data = json.loads(text)
    data['c'] = [1, 2]
    assert '"c": [\n  1,\n  2\n ]' in jsonstyle.rewritten(data, text, 1)


def test_a_new_file_is_plainly_indented():
    assert jsonstyle.rewritten({'a': [1]}, None, 2) == '{\n  "a": [\n    1\n  ]\n}\n'
