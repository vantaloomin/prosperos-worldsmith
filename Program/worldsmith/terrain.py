"""The world map painter's land and water: paint some sea, coast, mountains or forest on a world's hex map, and the
rest of the land, its rivers and lakes and good places for towns follow the way land and water work.

The map is Dungeon's hex map (world/data/hexes/<map>.json, or engine/hexes/<map>.json in a world folder; Dungeon's
dungeon/hexes.py): flat-topped hexes in offset rows, odd columns shifted down half a hex, one character a hex (the
legend below), with places, roads and rivers in axial coordinates (q = column, r = row - (column - (column & 1)) / 2).
What the author painted is kept as `paint` beside the terrain, so the map can be generated again around it.

How the land is worked out, all from the paint and a seed (the same paint and seed always give the same map):

- **Land and sea.** Unpainted hexes take the land or sea of the nearest painted ones, with a ragged coast (with only
  sea painted, the rest is land). A map with nothing painted is a continent from noise.
- **Height.** Land rises with distance from the sea, and steeply around painted mountains and hills, which fall away
  over a few hexes; with no mountains painted, ridges come from noise inland.
- **Rain.** The wind (west by default) carries moisture off the sea and drops it as the land rises, so the windward
  side of a range is wet and the lee lies in a rain shadow.
- **Rivers and lakes.** Water runs downhill to the sea. Basins with nowhere lower to drain fill up to their lowest rim
  and become lakes when enough rain reaches them (a dry basin stays a waste); the water then spills over the rim
  and runs on (priority-flood, so every hex has one way down). Rivers are the hexes enough water runs through; they
  join and grow as they go, and end at the sea or a lake.
- **Unpainted land** follows height and water: mountains and hills high up, marsh in wet lowlands and river mouths,
  forest where it rains, waste in the rain shadow, open plains between.
- **Town sites** score what people have always looked for: a river mouth or a sheltered bay for a port, where two
  rivers meet, a lake's outlet, a river crossing on flat land, a hill by water, water in dry country; kept apart.
"""
import heapq
import math
import random
from collections import deque

LEGEND = {'~': 'water', '.': 'plains', 'f': 'forest', 'h': 'hills', 'm': 'mountains', 'w': 'waste', 's': 'marsh'}
CODES = {name: code for code, name in LEGEND.items()}
WINDS = {'west': (1, 0), 'east': (-1, 0), 'north': (0, 1), 'south': (0, -1)}
# Hexes of river: the share of all the map's rain that must run through a hex before it is a river (lower: more).
RIVERS = {'few': 0.02, 'some': 0.008, 'many': 0.003}
TOWN_SPACING = 7
LAND_SHARE = 0.45  # Of a map with nothing painted.


def axial(column: int, row: int) -> tuple[int, int]:
    return column, row - (column - (column & 1)) // 2


def offset(q: int, r: int) -> tuple[int, int]:
    return q, r + (q - (q & 1)) // 2


AXIAL_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1))


class Map:
    """A hex map being worked out: cells by (column, row)."""

    def __init__(self, columns: int, rows: int, seed: str):
        self.columns, self.rows, self.seed = columns, rows, seed
        self.cells = [(column, row) for row in range(rows) for column in range(columns)]
        self._near = {}

    def inside(self, column: int, row: int) -> bool:
        return 0 <= column < self.columns and 0 <= row < self.rows

    def neighbours(self, cell: tuple[int, int]) -> list[tuple[int, int]]:
        if cell not in self._near:
            q, r = axial(*cell)
            found = [offset(q + dq, r + dr) for dq, dr in AXIAL_STEPS]
            self._near[cell] = [other for other in found if self.inside(*other)]
        return self._near[cell]

    def edge(self, cell: tuple[int, int]) -> bool:
        column, row = cell
        return column in (0, self.columns - 1) or row in (0, self.rows - 1)

    def point(self, cell: tuple[int, int]) -> tuple[float, float]:
        column, row = cell
        return column * 0.866, row + (0.5 if column & 1 else 0)

    def noise(self, field: str, cell: tuple[int, int], scale: float) -> float:
        """Smooth noise from 0 to 1 (value noise, three octaves) at a hex."""
        x, y = self.point(cell)
        total, weight, amplitude = 0.0, 0.0, 1.0
        for octave in range(3):
            total += amplitude * value_noise(f'{self.seed}:{field}:{octave}', x / scale, y / scale)
            weight += amplitude
            amplitude, scale = amplitude / 2, scale / 2
        return total / weight


def corner(seed: str, x: int, y: int) -> float:
    return random.Random(f'{seed}:{x}:{y}').random()


def value_noise(seed: str, x: float, y: float) -> float:
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    top = corner(seed, x0, y0) * (1 - fx) + corner(seed, x0 + 1, y0) * fx
    bottom = corner(seed, x0, y0 + 1) * (1 - fx) + corner(seed, x0 + 1, y0 + 1) * fx
    return top * (1 - fy) + bottom * fy


def ranked(values: dict) -> dict:
    """Each value's place among them all, from 0 (the least) to 1 (the most)."""
    order = sorted(values, key=lambda key: (values[key], key))
    last = max(len(order) - 1, 1)
    return {key: index / last for index, key in enumerate(order)}


def distances(world: Map, sources) -> dict[tuple[int, int], int]:
    """Hex steps from the nearest of `sources` to every hex."""
    found = {cell: 0 for cell in sources}
    queue = deque(found)
    while queue:
        cell = queue.popleft()
        for other in world.neighbours(cell):
            if other not in found:
                found[other] = found[cell] + 1
                queue.append(other)
    return found


# Land and sea ------------------------------------------------------------------------------------------------------

def land_and_sea(world: Map, paint: dict) -> set[tuple[int, int]]:
    """The land hexes: painted land, painted sea, and the unpainted taking after the nearest painted, raggedly."""
    sea_painted = [cell for cell, code in paint.items() if code == '~']
    land_painted = [cell for cell, code in paint.items() if code != '~']
    land = set()
    if not paint:
        score = {}
        for cell in world.cells:
            x, y = world.point(cell)
            # Falls off towards the edges, so the land is a continent with sea around it.
            dx, dy = x / (world.columns * 0.866) - 0.5, y / world.rows - 0.5
            score[cell] = world.noise('land', cell, 14) - math.sqrt(dx * dx + dy * dy) * 0.9
        level = ranked(score)
        return {cell for cell in world.cells if level[cell] > 1 - LAND_SHARE and not world.edge(cell)}
    to_sea = distances(world, sea_painted) if sea_painted else {}
    to_land = distances(world, land_painted) if land_painted else {}
    for cell in world.cells:
        code = paint.get(cell)
        if code is not None:
            if code != '~':
                land.add(cell)
            continue
        if not land_painted or not sea_painted:  # Only sea painted: the rest is land; only land: no more sea.
            land.add(cell)
            continue
        ragged = (world.noise('coast', cell, 4) - 0.5) * 4
        if to_land[cell] + ragged < to_sea[cell]:
            land.add(cell)
    return land


# Height and rain ---------------------------------------------------------------------------------------------------

def heights(world: Map, land: set, paint: dict) -> dict[tuple[int, int], float]:
    coast = distances(world, [cell for cell in world.cells if cell not in land] or [world.cells[0]])
    deepest = max([coast[cell] for cell in land] or [1]) or 1
    peaks = [cell for cell, code in paint.items() if code == 'm']
    hills = [cell for cell, code in paint.items() if code == 'h']
    to_peak = distances(world, peaks) if peaks else {}
    to_hill = distances(world, hills) if hills else {}
    height = {}
    for cell in world.cells:
        if cell not in land:
            height[cell] = -0.1
            continue
        inland = min(coast[cell] / max(deepest, 6), 1)
        lift = 0.0
        if peaks:
            lift = max(lift, math.exp(-to_peak[cell] / 2.5))
        if hills:
            lift = max(lift, 0.68 * math.exp(-to_hill[cell] / 2))
        if not peaks and not hills:
            ridge = 1 - abs(world.noise('ridge', cell, 10) * 2 - 1)
            lift = max(0.0, ridge - 0.55) / 0.45 * inland
        height[cell] = 0.02 + 0.33 * inland + 0.55 * lift + 0.1 * world.noise('height', cell, 5)
    if not peaks and not hills and land:
        # Unpainted relief: the highest tenth of the land is mountains, the next tenth hills.
        level = ranked({cell: height[cell] for cell in land})
        height.update({cell: 0.02 + 0.95 * level[cell] ** 2 for cell in land})
    for cell in peaks:
        height[cell] = max(height[cell], 0.85)
    for cell in hills:
        height[cell] = max(height[cell], 0.62)
    return height


def rain(world: Map, land: set, height: dict, wind: str) -> dict[tuple[int, int], float]:
    """Rain on each hex, carried by the wind off the sea and wrung out as the land rises."""
    step = WINDS.get(wind, WINDS['west'])
    found = {}
    if step[0]:  # Along the rows.
        lines = [[(column, row) for column in range(world.columns)] for row in range(world.rows)]
    else:
        lines = [[(column, row) for row in range(world.rows)] for column in range(world.columns)]
    for line in lines:
        if step[0] < 0 or step[1] < 0:
            line = line[::-1]
        moisture, last = 1.0, -0.1
        for cell in line:
            if cell not in land:
                moisture = min(1.0, moisture + 0.25)
                found[cell] = 0.0
                last = -0.1
                continue
            rise = max(0.0, height[cell] - last)
            fall = moisture * min(0.9, 0.05 + rise * 2.2 + height[cell] * 0.08)
            found[cell] = fall + 0.08 * world.noise('rain', cell, 6)
            moisture = max(0.0, moisture - fall)
            last = height[cell]
    # Smooth it a little across the lines.
    smooth = {}
    for cell in world.cells:
        around = [found[other] for other in world.neighbours(cell) if other in land]
        smooth[cell] = (found[cell] * 2 + sum(around)) / (2 + len(around)) if cell in land else 0.0
    # How wet a hex is among all the land: the wettest are forest, the driest waste.
    level = ranked({cell: smooth[cell] for cell in land})
    return {cell: level.get(cell, 0.0) for cell in world.cells}


# Water -------------------------------------------------------------------------------------------------------------

def drainage(world: Map, land: set, height: dict):
    """(order, downstream, filled): priority-flood from the sea and the map's edge, so every land hex has one way
    down; `filled` is each hex's height with basins filled to their rim."""
    filled, downstream, order, seen = {}, {}, [], set()
    queue = []
    for cell in world.cells:
        if cell not in land or world.edge(cell):
            heapq.heappush(queue, (height[cell], len(seen), cell))
            seen.add(cell)
            filled[cell] = height[cell]
            downstream[cell] = None
    count = len(seen)
    while queue:
        level, _, cell = heapq.heappop(queue)
        order.append(cell)
        for other in world.neighbours(cell):
            if other in seen:
                continue
            seen.add(other)
            count += 1
            filled[other] = max(height[other], level + 1e-5)
            downstream[other] = cell
            heapq.heappush(queue, (filled[other], count, other))
    return order, downstream, filled


def water(world: Map, land: set, height: dict, wet: dict, rivers: str):
    """(lakes, flow, downstream): lake hexes, the water through each hex, and where each hex drains."""
    order, downstream, filled = drainage(world, land, height)
    flow = {cell: (wet[cell] + 0.05 if cell in land else 0.0) for cell in world.cells}
    for cell in reversed(order):
        below = downstream.get(cell)
        if below is not None and cell in land:
            flow[below] += flow[cell]
    total = sum(wet[cell] + 0.05 for cell in land) or 1
    lakes = set()
    basins = [cell for cell in land if filled[cell] - height[cell] > 0.012]
    # A basin is a lake when enough water reaches it to fill it; a dry one stays land.
    for cell in basins:
        if flow[cell] / total > RIVERS.get(rivers, RIVERS['some']) * 0.6:
            lakes.add(cell)
    # Keep only lakes of two hexes or more, or one beside another lake hex.
    lakes = {cell for cell in lakes if any(other in lakes for other in world.neighbours(cell))}
    return lakes, flow, downstream, total


def river_courses(world: Map, land: set, lakes: set, flow: dict, downstream: dict, total: float, rivers: str):
    """Each river as the hexes it runs through, from its source to the sea, a lake or the river it joins."""
    least = total * RIVERS.get(rivers, RIVERS['some'])
    river = {cell for cell in land if cell not in lakes and flow[cell] >= least}
    inflow = {cell: 0 for cell in river}
    for cell in river:
        below = downstream.get(cell)
        if below in river:
            inflow[below] += 1
    courses, done = [], set()
    for source in sorted((cell for cell in river if inflow[cell] == 0), key=lambda cell: -flow[cell]):
        cells, cell = [], source
        while cell is not None:
            cells.append(cell)
            if cell in done or cell not in river:
                break
            done.add(cell)
            cell = downstream.get(cell)
        if len(cells) >= 3:
            courses.append(cells)
    return river, courses


# Terrain and towns -------------------------------------------------------------------------------------------------

def terrain_of(world: Map, cell, land, lakes, river, height, wet, paint) -> str:
    if cell in paint:
        return paint[cell]
    if cell not in land or cell in lakes:
        return '~'
    h, w = height[cell], wet[cell]
    near_water = cell in river or any(other in lakes or other in river for other in world.neighbours(cell))
    coastal = any(other not in land for other in world.neighbours(cell))
    if h > 0.78:
        return 'm'
    if h > 0.6:
        return 'h'
    if h < 0.1 and ((w > 0.8 and near_water) or (cell in river and coastal)):
        return 's'
    if w > 0.62 or (near_water and w > 0.4):
        return 'f'
    if w < 0.12 and not near_water:
        return 'w'
    return '.'


def by_water(world: Map, cell, land, lakes, river, downstream, inflows) -> tuple[float, str, list[str]]:
    """What the sea, rivers and lakes beside a hex give a town there."""
    around = world.neighbours(cell)
    sea = [other for other in around if other not in land]
    score, why, kind = 0.0, [], 'village'
    if cell in river and sea:
        score, kind = score + 6, 'port'
        why.append('a river mouth on the coast: a harbour and the way inland')
    elif len(sea) == 2 and not world.edge(cell):
        score, kind = score + 2, 'port'
        why.append('a sheltered bay for boats')
    elif sea:
        score += 1
        why.append('on the coast')
    if len([other for other in inflows.get(cell, []) if other in river]) >= 2:
        score += 5
        kind = kind if kind == 'port' else 'river town'
        why.append('where two rivers meet')
    lake = [other for other in around if other in lakes]
    if lake:
        if any(downstream.get(other) == cell for other in lake) and downstream.get(cell) in river:
            score += 4
            why.append("at the lake's outlet")
        else:
            score += 2
            why.append('on a lake shore')
        kind = kind if kind != 'village' else 'lake town'
    return score, kind, why


def site_score(world: Map, cell, code: str, land, lakes, river, downstream, inflows) -> tuple[float, str, list[str]]:
    """How good a hex is for a town, the kind of town it would be, and why."""
    score, kind, why = by_water(world, cell, land, lakes, river, downstream, inflows)
    around = world.neighbours(cell)
    coastal = any(other not in land for other in around)
    watered = cell in river or any(other in lakes or other in river for other in around)
    if cell in river and not coastal and code in ('.', 'f'):
        score += 2
        kind = kind if kind != 'village' else 'river town'
        why.append('a river crossing on level ground')
    if code == 'h' and watered:
        score += 2
        kind = 'hill fort' if kind == 'village' else kind
        why.append('high ground above water, easy to hold')
    if code == '.':
        score += 1
        if cell not in river and any(other in river for other in around):
            score += 1.5
            why.append('good farmland by a river')
    if code in ('s', 'w'):
        score -= 3
    if code == 'w' and not coastal and (cell in river or any(other in lakes for other in around)):
        score += 5
        kind = 'oasis'
        why.append('water in dry country')
    return score, kind, why


def town_sites(world: Map, grid: dict, land, lakes, river, flow, downstream, places, count=8) -> list[dict]:
    inflows = {}
    for cell in river:
        below = downstream.get(cell)
        if below is not None:
            inflows.setdefault(below, []).append(cell)
    candidates = []
    for cell in land:
        if cell in lakes or grid[cell] in ('~', 'm'):
            continue
        score, kind, why = site_score(world, cell, grid[cell], land, lakes, river, downstream, inflows)
        if score >= 2.5 and why:
            candidates.append((score + flow[cell] * 1e-6, cell, kind, why))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    chosen, taken = [], [offset(*at) for at in places]
    ports = 0
    for score, cell, kind, why in candidates:
        # No more than half the suggestions are ports, so the inland gets its towns too.
        if kind == 'port' and ports >= max(1, count // 2):
            continue
        if any(hex_distance(cell, other) < TOWN_SPACING for other in taken):
            continue
        taken.append(cell)
        ports += kind == 'port'
        q, r = axial(*cell)
        chosen.append({'q': q, 'r': r, 'column': cell[0], 'row': cell[1], 'kind': kind, 'score': round(score, 1),
                       'why': why, 'terrain': LEGEND[grid[cell]]})
        if len(chosen) == count:
            break
    return chosen


def hex_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    (q1, r1), (q2, r2) = axial(*a), axial(*b)
    return (abs(q1 - q2) + abs(r1 - r2) + abs(q1 + r1 - q2 - r2)) // 2


# The whole map -----------------------------------------------------------------------------------------------------

def painted(paint_rows: list[str]) -> dict[tuple[int, int], str]:
    return {(column, row): code for row, line in enumerate(paint_rows) for column, code in enumerate(line)
            if code in LEGEND}


def generate(columns: int, rows: int, paint_rows: list[str] | None = None, seed: str = 'worldsmith',
             wind: str = 'west', rivers: str = 'some', places: list | None = None, towns: int = 8) -> dict:
    """The map from the author's paint: terrain rows, lakes, rivers (axial cells, with how much water each step
    carries), suggested town sites and each hex's height, for the painter to show and save."""
    world = Map(columns, rows, seed)
    paint = painted(paint_rows or [])
    land = land_and_sea(world, paint)
    height = heights(world, land, paint)
    wet = rain(world, land, height, wind)
    lakes, flow, downstream, total = water(world, land, height, wet, rivers)
    river, courses = river_courses(world, land, lakes, flow, downstream, total, rivers)
    grid = {cell: terrain_of(world, cell, land, lakes, river, height, wet, paint) for cell in world.cells}
    # A painted land hex in a lake keeps its paint; a lake never floods a painted hex.
    lakes = {cell for cell in lakes if cell not in paint}
    top = max(flow[cell] for cell in river) if river else 1
    return {
        'columns': columns, 'rows': rows, 'legend': LEGEND,
        'terrain': [''.join(grid[(column, row)] for column in range(columns)) for row in range(rows)],
        'lakes': sorted([list(axial(*cell)) for cell in lakes]),
        'rivers': [{'id': f'river-{index + 1}', 'name': '', 'cells': [list(axial(*cell)) for cell in cells],
                    'flow': [round(flow[cell] / top, 3) for cell in cells]}
                   for index, cells in enumerate(sorted(courses, key=lambda cells: -flow[cells[-1]]))],
        'height': [[round(height[(column, row)], 2) for column in range(columns)] for row in range(rows)],
        'towns': town_sites(world, grid, land, lakes, river, flow, downstream, places or [], towns),
    }
