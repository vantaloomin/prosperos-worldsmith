# Vendored from prosperos-dungeon Program/dungeon/world/schema.py by scripts/sync_format.py. Edit it there, then sync.
"""Shape of the shipped world data. Loading validates every file, so a broken record fails the tests.

Every record names a source from its file's `sources` table, so each fact can be traced to where it
came from, under which license, and when it was gathered.
"""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
Id = Annotated[str, Field(pattern=r'^[a-z0-9]+(-[a-z0-9]+)*$', max_length=80)]
Text = Annotated[str, Field(min_length=1, max_length=400)]
Cost = Literal['free', '$', '$$', '$$$', '$$$$']
Season = Literal['winter', 'spring', 'summer', 'fall']
Company = Literal['solo', 'friends', 'date', 'family', 'coworkers']
DayPart = Literal['morning', 'afternoon', 'evening', 'late']
# Kinds the generators reason about. Place kinds, college types, transit kinds and local colour kinds are open:
# a city may add its own (a bowling alley, a film school), which work everywhere a specific kind is not asked for.
PLACE_KINDS = ('attraction', 'museum', 'park', 'beach', 'landmark', 'venue', 'stadium', 'market', 'shopping',
                    'restaurant', 'cafe', 'bar', 'nightlife', 'fitness', 'library', 'trail', 'vet',
                    # Kinds for historical, fictional and original settings.
                    'tavern', 'inn', 'temple', 'guildhall', 'workshop', 'square', 'docks', 'garden')
PlaceKind = Id
Exposure = Literal['indoor', 'outdoor', 'mixed']
Tier = Literal['low', 'mid', 'high', 'very-high']
Level = Literal['low', 'medium', 'high']
COLLEGE_TYPES = ('research-university', 'public-university', 'private-university', 'liberal-arts-college',
                      'community-college', 'art-school', 'medical-school', 'technical-institute', 'music-school',
                      'academy', 'seminary', 'guild-school')
CollegeType = Id
Size = Literal['small', 'medium', 'large']
TRANSIT_KINDS = ('subway', 'light-rail', 'commuter-rail', 'bus', 'ferry', 'water-taxi', 'monorail',
                      'streetcar', 'bike-share', 'car', 'rideshare', 'walk',
                      'carriage', 'horse', 'tram', 'airship', 'boat', 'stagecoach')
TransitKind = Id
# What a city is: a real place, a well-known fictional setting, or an original one (built in or the user's own).
Setting = Literal['real', 'fictional', 'original']
# A year a decade rule can name (dungeon/world/decades.py).
CalendarYear = Annotated[int, Field(ge=1800, le=2200)]
Era = Literal['modern', 'victorian', 'medieval', 'fantasy', 'steampunk', 'frontier', 'jazz-age', 'future', 'other']
ScheduleKind = Literal['office', 'shift-day', 'shift-night', 'rotating', 'evening', 'early', 'flexible', 'academic']
# Same days every week, a rota of shifts that changes weekly, or freelance gigs (dungeon/life/shifts.py).
Employment = Literal['staff', 'rota', 'freelance']


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Source(Record):
    kind: Id  # curated, wikidata, openstreetmap, government, user or other, or a city's own
    title: Text
    license: Text
    retrieved: Annotated[str, Field(pattern=r'^\d{4}-\d{2}-\d{2}$')]
    url: str = ''
    attribution: str = ''
    note: str = Field(default='', max_length=1000)


class Rent(Record):
    """Typical asking rent ranges in the city's currency, per its `rent_period`. Estimates for fiction, not listings."""
    studio: tuple[int, int]
    one_bedroom: tuple[int, int]
    two_bedroom: tuple[int, int]

    @model_validator(mode='after')
    def check(self):
        for low, high in (self.studio, self.one_bedroom, self.two_bedroom):
            if not 0 < low <= high:
                raise ValueError('Rent ranges are positive and low to high.')
        return self


class Neighborhood(Record):
    id: Id
    name: Text
    summary: Text
    vibe: list[Id] = Field(min_length=1, max_length=8)
    # Approximate centre, for distances and commute estimates only.
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    rent_tier: Tier = 'mid'
    # None where the setting has no rent to speak of (Oz has no money).
    rent: Rent | None = None
    housing: list[Id] = Field(min_length=1, max_length=6)
    walkability: Level
    transit: list[Id] = Field(default_factory=list, max_length=8)
    source: Id


class Place(Record):
    id: Id
    name: Text
    kind: PlaceKind
    neighborhood: Id
    summary: Text
    tags: list[Id] = Field(default_factory=list, max_length=10)
    cost: Cost
    setting: Exposure
    good_for: list[Company] = Field(min_length=1)
    day_parts: list[DayPart] = Field(min_length=1)
    # Empty means all year.
    seasons: list[Season] = Field(default_factory=list)
    cuisine: str = Field(default='', max_length=60)
    # Named spots inside (the terrace, the café on L5), used as detail (dungeon/world/inside.py).
    spots: list[Text] = Field(default_factory=list, max_length=8)
    source: Id


class College(Record):
    id: Id
    name: Text
    type: CollegeType
    neighborhood: Id
    size: Size
    known_for: list[Id] = Field(min_length=1, max_length=10)
    source: Id


class Employer(Record):
    id: Id
    name: Text
    sector: Id
    neighborhood: Id
    size: Size
    summary: Text
    careers: list[Id] = Field(min_length=1)
    source: Id


class CareerHub(Record):
    id: Id
    name: Text
    neighborhoods: list[Id] = Field(min_length=1)
    sectors: list[Id] = Field(min_length=1)
    summary: Text
    source: Id


class TransitLine(Record):
    id: Id
    name: Text
    kind: TransitKind
    summary: Text
    source: Id


class Month(Record):
    high_f: int
    low_f: int
    rain_days: int = Field(ge=0, le=31)
    note: str = Field(default='', max_length=200)


class Climate(Record):
    summary: Text
    months: list[Month] = Field(min_length=12, max_length=12)
    source: Id


class AnnualEvent(Record):
    id: Id
    name: Text
    months: list[int] = Field(min_length=1)
    neighborhood: Id | None = None
    summary: Text
    source: Id

    @model_validator(mode='after')
    def check(self):
        if any(month < 1 or month > 12 for month in self.months):
            raise ValueError('Months are 1 to 12.')
        return self


class Career(Record):
    id: Id
    name: Text
    sector: Id
    schedule: ScheduleKind
    # Left out, it is read from the career's words (dungeon/life/shifts.py `employment_of`).
    employment: Employment | None = None
    pay: Cost
    summary: Text
    # Themes the life simulation may draw on for this work.
    themes: list[str] = Field(min_length=1, max_length=8)
    # Settings this career belongs to; a city offers the shared careers of its era plus its own.
    eras: list[Era] = Field(default_factory=lambda: ['modern'], min_length=1)
    # Place kinds the work needs; a city with none of them and no employer for it doesn't offer it.
    needs: list[Id] = Field(default_factory=list, max_length=4)
    # Adult work (a cam model, say): only ever chosen for an adult, and only offered to people while Settings >
    # Realism > Adult side of life is on. Never rolled for townsfolk, circles or job changes.
    adult: bool = False
    # Who did this work in its era where custom kept it to one side ('men' for a cabman in 1895, 'women' for a
    # governess); left out, anyone. Read only in a city whose era keeps work by gender (City.work_by_gender).
    worked_by: Literal['men', 'women'] | None = None
    # The ages (in human terms) someone works it at, [youngest, oldest]: a squire is young, a student 18 to 22.
    # Left out, any working age.
    ages: tuple[Annotated[int, Field(ge=16, le=99)], Annotated[int, Field(ge=16, le=99)]] | None = None
    # The years the work existed, [from, until], either null for open: a video store clerk until 2010. Read only in
    # a modern city (dungeon/world/decades.py); left out, any year.
    years: tuple[CalendarYear | None, CalendarYear | None] | None = None

    @model_validator(mode='after')
    def check_ages(self):
        if self.ages and self.ages[0] > self.ages[1]:
            raise ValueError('A career\'s ages run from the youngest to the oldest.')
        if self.years and None not in self.years and self.years[0] > self.years[1]:
            raise ValueError('A career\'s years run from the first to the last.')
        return self


class Currency(Record):
    code: Annotated[str, Field(min_length=1, max_length=12)] = 'USD'
    symbol: Annotated[str, Field(max_length=8)] = '$'
    name: Annotated[str, Field(min_length=1, max_length=40)] = 'US dollars'


class NameGroup(Record):
    """Given and family names that commonly go together, for one heritage in one period."""
    feminine: list[Text] = Field(default_factory=list)
    masculine: list[Text] = Field(default_factory=list)
    neutral: list[Text] = Field(default_factory=list)
    family: list[Text] = Field(min_length=1)
    # In modern settings, the shares of given names drawn from each culture's popular names for the person's
    # birth year (given_names.json) instead of the lists above. `local` is the city's own country.
    cultures: dict[Id, float] = Field(default_factory=dict)
    # Keep this group's own family names even when a linked culture lists its own (a mill town's local names).
    own_family: bool = False
    # Endings a woman's family name takes instead (Roman Cornelius becomes Cornelia): {"ius": "ia"}.
    feminine_family: dict[str, str] = Field(default_factory=dict)
    # The kind of people this group's names belong to (dungeon/world/lifespans.py), built in or the city's own;
    # empty for humans. An unknown kind is dropped when the city loads.
    kind: str | None = Field(default=None, max_length=40)

    @model_validator(mode='after')
    def check(self):
        if not (self.feminine or self.masculine or self.neutral):
            raise ValueError('A name group needs some given names.')
        return self


class CityNames(Record):
    """How a city names its residents: a shared bank (its era's by default), group weights, and its own groups."""
    bank: Id | None = None
    mix: dict[Id, float] = Field(default_factory=dict)
    groups: dict[Id, NameGroup] = Field(default_factory=dict)
    # The year the city's present day is set in, so ages count back from it (2077 for a future city).
    year: int | None = Field(default=None, ge=1, le=3000)


Year = Annotated[str, Field(pattern=r'^\d{4}$')]
MonthDay = Annotated[str, Field(pattern=r'^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$')]


class Holiday(Record):
    """One holiday, by exactly one rule: a fixed date, the nth weekday of a month, days from Easter, or a table of
    dates by year (holidays on a lunar calendar, or set by astronomy, such as Seollal or an equinox)."""
    id: Id
    name: Text
    kind: Literal['public', 'observance', 'feast']
    summary: Text
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    # Monday is 0. `nth` counts from 1, or -1 for the last in the month.
    weekday: int | None = Field(default=None, ge=0, le=6)
    nth: int | None = Field(default=None, ge=-1, le=5)
    easter: int | None = Field(default=None, ge=-70, le=70)
    # "MM-DD" by year ("2026": "02-17"); a year missing from the table has no such holiday.
    dates: dict[Year, MonthDay] | None = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def check(self):
        plain = (self.month, self.day, self.weekday, self.nth, self.easter) == (None,) * 5
        shapes = {
            'fixed': self.month is not None and self.day is not None and self.weekday is None and self.nth is None,
            'weekday': self.month is not None and self.day is None and self.weekday is not None
            and self.nth not in (None, 0),
            'easter': self.easter is not None and self.month is None,
            'dates': self.dates is not None and plain,
        }
        if sum(shapes.values()) != 1 or (self.easter is not None and (self.weekday, self.nth) != (None, None)) or \
                (self.dates is not None and not plain):
            raise ValueError(f'Holiday {self.id} needs one rule: month and day, month weekday and nth, easter, '
                             'or dates by year.')
        return self


# 'legend' and 'rumor' are hearsay: what locals tell, never confirmed fact (generators.local_color and facts say so).
LOCAL_COLOR_KINDS = ('dish', 'drink', 'saying', 'custom', 'team', 'shop', 'legend', 'rumor', 'other')
HEARSAY_KINDS = ('legend', 'rumor')
SOURCE_KINDS = ('curated', 'wikidata', 'openstreetmap', 'government', 'user', 'other')


class LocalColor(Record):
    """Something locals eat, drink, say, root for, do or tell (a legend, a rumour), so the model can mention it
    without inventing it."""
    id: Id
    name: Text
    kind: Id  # LOCAL_COLOR_KINDS, or a city's own
    summary: Text
    # Where it is easiest to find, when it is a thing found in particular places.
    places: list[Id] = Field(default_factory=list, max_length=6)
    seasons: list[Season] = Field(default_factory=list)
    source: Id


class Price(Record):
    """A typical price range for an everyday purchase, in the city's currency. Estimates for fiction."""
    id: Id
    item: Text
    low: float = Field(ge=0)
    high: float = Field(ge=0)
    # What the price is for, when it isn't obvious: "a pint", "one way", "a week's board".
    per: str = Field(default='', max_length=80)
    source: Id

    @model_validator(mode='after')
    def check(self):
        if self.low > self.high:
            raise ValueError(f'Price {self.id} runs low to high.')
        return self


class Notable(Record):
    """A named person a city places in town, such as a character from the setting a pack draws on. They join the
    townsfolk at their place and live by the same rules (shifts or visits, goals, meetings), but with the name,
    role and description given here instead of drawn ones."""
    id: Id
    name: Text
    # What people call them; the first word of `name` when left out.
    given: str = Field(default='', max_length=60)
    pronouns: Literal['she/her', 'he/him', 'they/them'] = 'they/them'
    # Real years; past 120 only makes sense for a long-lived `kind` (dungeon/world/lifespans.py).
    age: int = Field(ge=16, le=5000)
    # Their kind ('elf', 'half-elf', a city's own); human when left out.
    kind: Id | None = None
    place: Id
    role: Annotated[str, Field(min_length=1, max_length=80)]
    # Works there (keeps shifts) or only turns up as a regular (keeps visits).
    staff: bool = False
    about: Text
    # What they are after now, which they pursue in a scene unprompted; their drawn goals when left out.
    wants: str = Field(default='', max_length=200)
    temperament: Id | None = None
    source: Id
    # Whether they can move away or retire like other townsfolk (dungeon/world/turnover.py). A setting's own
    # characters stay put unless the pack says otherwise.
    can_leave: bool = False
    # The weekdays a staff notable works (0 is Monday); two drawn days off when left out. A one-person shop's keeper
    # works every day, so the shop is open whenever its place is.
    days: list[Annotated[int, Field(ge=0, le=6)]] | None = None


# Where a townsperson goes to work on a goal (dungeon/world/townsfolk.py GOAL_KINDS).
PracticeSpot = Literal['park', 'venue', 'library', 'cafe', 'gym', 'market', 'workshop', 'museum', 'beach', 'temple',
                       'restaurant']


class TownQuirk(Record):
    """A quirk particular to the city's townsfolk, beside the shared bank (world/data/quirks.json)."""
    text: Text  # A subject-less clause: 'keeps the tide table pinned by the door'.
    bio: str = Field(default='', max_length=400)  # First-person line for their dating profile.


class TownGoal(Record):
    """A goal particular to the city's townsfolk, beside the shared bank (world/data/goals.json), in its era's words."""
    id: Id
    text: Text  # Completes 'trying to ...'.
    steps: int = Field(ge=1, le=12)
    practice: tuple[PracticeSpot, DayPart] | None = None
    progress: Text  # Starts with {name}.
    done: Text  # Starts with {name}.
    interest: str = Field(default='', max_length=80)
    bio: str = Field(default='', max_length=400)


class Townsfolk(Record):
    """How the city flavours its townsfolk: quirks and goals they draw beside the shared ones, more often than any
    one shared quirk or goal, so the town's people sound like the town."""
    quirks: list[TownQuirk] = Field(default_factory=list, max_length=40)
    goals: list[TownGoal] = Field(default_factory=list, max_length=40)


class Water(Record):
    """Sea, a river or a lake, for the drawn map of a city without a street map (src/features/map/drawn.ts)."""
    kind: Literal['sea', 'river', 'lake']
    name: str = Field(default='', max_length=80)
    # A sea: the side of the city its coast faces.
    side: Literal['north', 'south', 'east', 'west'] | None = None
    # A river: [lat, lon] points along it, in order (two or more); a lake: its centre (one).
    points: list[tuple[float, float]] = Field(default_factory=list, max_length=40)
    width_km: float = Field(default=0.3, gt=0, le=20)

    @model_validator(mode='after')
    def check(self):
        needs = {'sea': self.side is not None, 'river': len(self.points) >= 2, 'lake': len(self.points) == 1}
        if not needs[self.kind]:
            raise ValueError({'sea': 'A sea needs a side.', 'river': 'A river needs two or more points.',
                              'lake': 'A lake needs one point, its centre.'}[self.kind])
        return self


class Intensity(Record):
    """How far a world's stories go by default, the narrator's voice there and how eventful they are (requirements
    "Intensity and tone")."""
    preset: Literal['restrained', 'mature', 'unflinching'] = 'unflinching'
    voice: str = Field(default='', max_length=300)
    # How eventful its stories are by default: how often Life Cards turn up, and which (dungeon/happenings.py).
    drama: Literal['quiet', 'uneasy', 'eventful', 'merciless'] = 'uneasy'


class TownMap(Record):
    """How the town's street map is drawn (dungeon/townmap.py): its look, left out to let the era decide ('none' for a
    city that is a world's roads or wilds, not a town), and whether a wall rings it."""
    style: Literal['ink', 'street', 'floor', 'none'] | None = None
    walls: bool | None = None


class City(Record):
    """One city. Minimums are small so a user can start a city of their own with a neighborhood and a place."""
    schema_version: Literal[1]
    id: Id
    name: Text
    setting: Setting = 'real'
    era: Era = 'modern'
    # 'private' marks a personal city pack (for example fan fiction of owned settings): loaded from a local
    # folder, never shipped or committed.
    distribution: Literal['public', 'private'] = 'public'
    # Where the city sits in city lists: 'real' (real places today), 'other-eras' (a real or realistic past) or
    # 'fictional'. Open text so a stray word never stops a city loading; when it is not one of those three it is
    # worked out from the setting and era (catalog.category).
    category: str = Field(default='', max_length=40)
    # For fictional settings: the work it draws on and why it may be shipped (for example, public domain).
    basis: str = Field(default='', max_length=400)
    region: Text
    country: Text
    # Used for display and as the suggested companion timezone; fictional cities borrow a real zone.
    timezone: Text
    aliases: list[str] = Field(default_factory=list)
    summary: Text
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    currency: Currency = Currency()
    rent_period: Literal['month', 'week'] = 'month'
    # Typical door-to-door speeds in km/h for commute estimates.
    speeds: dict[TransitKind, float] = Field(default_factory=lambda: {'walk': 4.5})
    sources: dict[Id, Source] = Field(min_length=1)
    neighborhoods: list[Neighborhood] = Field(min_length=1, max_length=200)
    places: list[Place] = Field(min_length=1, max_length=2000)
    colleges: list[College] = Field(default_factory=list, max_length=200)
    employers: list[Employer] = Field(default_factory=list, max_length=500)
    career_hubs: list[CareerHub] = Field(default_factory=list, max_length=100)
    transit: list[TransitLine] = Field(default_factory=list, max_length=100)
    climate: Climate | None = None
    annual_events: list[AnnualEvent] = Field(default_factory=list, max_length=200)
    # Careers particular to this city or its setting, beside the shared catalogue.
    careers: list[Career] = Field(default_factory=list, max_length=200)
    # Whether townsfolk's jobs follow the careers' `worked_by`: left out, the era decides (on before about 1920 and
    # in the Middle Ages, off today and in fantasy settings, which turn it on themselves; generators.by_gender).
    work_by_gender: bool | None = None
    names: CityNames | None = None
    # The world's default intensity and narrator voice; left out, every category is unflinching with no voice.
    intensity: Intensity | None = None
    local_color: list[LocalColor] = Field(default_factory=list, max_length=100)
    prices: list[Price] = Field(default_factory=list, max_length=60)
    # A shared holiday calendar ('none' for no shared one); by default chosen from the era and country.
    calendar: Id | None = None
    # Holidays particular to this city, beside its calendar's.
    holidays: list[Holiday] = Field(default_factory=list, max_length=100)
    # Sea, rivers and lakes, drawn on the map of a city without a street map.
    water: list[Water] = Field(default_factory=list, max_length=12)
    # The town's street map (dungeon/townmap.py): laid out from the neighborhoods, places and water above.
    town_map: TownMap | None = None
    # False for the stretch between towns (a world's roads, a tower's floors): somewhere to pass through, not to
    # live, so the pickers for where someone lives leave it out.
    home: bool = True
    # Named people placed in town (a pack's characters), beside the seeded townsfolk.
    notables: list[Notable] = Field(default_factory=list, max_length=200)
    # Quirks and goals of the city's own for its townsfolk (dungeon/world/townsfolk.py).
    townsfolk: Townsfolk | None = None
    # Kinds of people (dungeon/world/lifespans.py): a built-in kind's lifespan here ({"elf": {"lifespan": 750}}) or
    # a kind of the city's own (label, lifespan and words). Checked when the city loads (lifespans.clean), which
    # drops a bad entry with a note rather than stopping the city loading.
    kinds: Any = None  # Any shape here: a wrong one is dropped with a note (lifespans.clean), not a failed load.

    @model_validator(mode='after')
    def check(self):
        groups = (self.neighborhoods, self.places, self.colleges, self.employers, self.career_hubs, self.transit,
                  self.annual_events)
        records = [item for group in groups for item in group]
        ids = [item.id for item in records]
        if len(ids) != len(set(ids)):
            raise ValueError(f'Duplicate ids {sorted({i for i in ids if ids.count(i) > 1})}.')
        cited = [(item.id, item.source) for item in records]
        cited += [('climate', self.climate.source)] if self.climate else []
        cited += [(item.id, item.source) for item in [*self.local_color, *self.prices, *self.notables]]
        missing = [name for name, source in cited if source not in self.sources]
        if missing:
            raise ValueError(f'Unknown sources cited by {missing}.')
        hoods = {item.id for item in self.neighborhoods}
        located = [(item.id, {item.neighborhood}) for item in [*self.places, *self.colleges, *self.employers]]
        located += [(item.id, {item.neighborhood} - {None}) for item in self.annual_events]
        located += [(item.id, set(item.neighborhoods)) for item in self.career_hubs]
        stray = [f'{name} ({", ".join(sorted(used - hoods))})' for name, used in located if not used <= hoods]
        if stray:
            raise ValueError(f'Unknown neighborhoods named by {", ".join(stray)}.')
        known = {item.id for item in [*self.places, *self.neighborhoods]}
        stray = [item.id for item in self.local_color if not set(item.places) <= known]
        if stray:
            raise ValueError(f'Local colour names unknown places: {stray}.')
        lines = {item.id for item in self.transit}
        stray = [item.id for item in self.neighborhoods if not set(item.transit) <= lines]
        if stray:
            raise ValueError(f'Unknown transit lines named by {stray}.')
        return self

    @model_validator(mode='after')
    def check_notables(self):
        places = {item.id for item in self.places}
        stray = [item.id for item in self.notables if item.place not in places]
        if stray:
            raise ValueError(f'Notables placed at unknown places: {stray}.')
        people = [item.id for item in self.notables]
        if len(people) != len(set(people)):
            raise ValueError(f'Duplicate notables {sorted({i for i in people if people.count(i) > 1})}.')
        return self


class Careers(Record):
    schema_version: Literal[1]
    source: Source
    careers: list[Career] = Field(min_length=10)


class EraNames(Record):
    bank: Id
    mix: dict[Id, float] = Field(default_factory=dict)


class Names(Record):
    schema_version: Literal[1]
    source: Source
    banks: dict[Id, dict[Id, NameGroup]] = Field(min_length=1)
    eras: dict[Era, EraNames]

    @model_validator(mode='after')
    def check(self):
        for era, entry in self.eras.items():
            groups = self.banks.get(entry.bank)
            if groups is None or not set(entry.mix) <= set(groups):
                raise ValueError(f'Era {era} names an unknown bank or group.')
        return self


class Cohort(Record):
    """The most popular given names for babies born in these years, most popular first."""
    start: int = Field(ge=1700, le=2100)
    end: int = Field(ge=1700, le=2100)
    estimate: bool
    feminine: list[Text] = Field(min_length=1)
    masculine: list[Text] = Field(min_length=1)


class Culture(Record):
    name: Text
    sources: list[Source] = Field(min_length=1)
    # Most common family names, most common first; empty when people take the city group's family names.
    surnames: list[Text] = Field(default_factory=list)
    cohorts: list[Cohort] = Field(min_length=1)


class InventedNames(Record):
    given: list[Text]
    family: list[Text]


class GivenNames(Record):
    schema_version: Literal[1]
    # Ages count back from this year, so a name never changes with the clock.
    present_year: int = Field(ge=1900, le=2100)
    # The year each era's present day is set in. Eras listed here ground given names in birth years.
    era_years: dict[str, int]
    cultures: dict[Id, Culture] = Field(min_length=1)
    # Country names (lower case) to the culture whose names are local there.
    countries: dict[str, Id]
    invented: InventedNames

    @model_validator(mode='after')
    def check(self):
        unknown = set(self.countries.values()) - set(self.cultures)
        if unknown:
            raise ValueError(f'Countries name unknown cultures: {sorted(unknown)}.')
        blocked = {word.casefold() for word in [*self.invented.given, *self.invented.family]}
        for key, culture in self.cultures.items():
            words = {word.casefold() for cohort in culture.cohorts for word in [*cohort.feminine, *cohort.masculine]}
            words |= {word.casefold() for word in culture.surnames}
            if clash := words & blocked:
                raise ValueError(f'{key} lists invented-sounding names: {sorted(clash)}.')
        return self


class HolidayCalendar(Record):
    name: Text
    holidays: list[Holiday] = Field(min_length=1)


class Holidays(Record):
    schema_version: Literal[1]
    source: Source
    calendars: dict[Id, HolidayCalendar] = Field(min_length=1)


class Opening(Record):
    first: list[Text] = Field(min_length=1)
    second: list[Text] = Field(min_length=1)
    summary: Text


class Roadworks(Record):
    summary: Text
    # Extra minutes a trip by road through the works takes.
    delay: int = Field(ge=1, le=60)


class ChangeStyle(Record):
    openings: dict[PlaceKind, Opening] = Field(min_length=1)
    renovation: list[Text] = Field(min_length=1)
    closing: list[Text] = Field(min_length=1)
    roadworks: list[Roadworks] = Field(min_length=1)


class Changes(Record):
    schema_version: Literal[1]
    source: Source
    styles: dict[Id, ChangeStyle] = Field(min_length=1)
    eras: dict[Era, Id]

    @model_validator(mode='after')
    def check(self):
        missing = sorted(set(Era.__args__) - set(self.eras))
        unknown = sorted(set(self.eras.values()) - set(self.styles))
        if missing or unknown:
            raise ValueError(f'Every era needs a known style (missing {missing}, unknown {unknown}).')
        return self


class Featured(Record):
    """The cities a release puts up front (dungeon/world/data/featured.json), edited at each release."""
    schema_version: Literal[1]
    # The release the list belongs to, as major.minor ('0.8'); its cities are marked new while the app is on it.
    release: Annotated[str, Field(pattern=r'^\d+\.\d+$')]
    title: Text
    note: str = Field(default='', max_length=200)
    cities: list[Id] = Field(default_factory=list, max_length=4)
    # The featured cities that first shipped in this release; only these get the New badge.
    new_cities: list[Id] = Field(default_factory=list, max_length=4)


# Interiors (requirements "### Interiors"): the inside of a keep, cave, crypt or mine as rooms joined by passages.

Difficulty = Literal['easy', 'normal', 'hard', 'very_hard', 'extreme']
RoomSize = Literal['cramped', 'room', 'hall', 'cavern']
Light = Literal['lit', 'dim', 'dark']
PassageKind = Literal['open', 'door', 'stairs', 'ladder', 'shaft', 'crawl', 'water', 'secret']
InteriorStyle = Literal['cave', 'keep', 'crypt', 'mine', 'tower', 'sewer', 'ruin', 'building', 'other']


class Foe(Record):
    """A foe in the shape road encounters use (dungeon/travel.py, dungeon/combat.py)."""
    name: Text
    count: int = Field(default=1, ge=1, le=12)
    vitality: int = Field(ge=1, le=60)
    resolve: int = Field(ge=1, le=60)
    weapon: int = Field(default=0, ge=0, le=4)
    wants: Id = 'kill'
    horror: bool = False


class Threat(Record):
    text: Text
    foe: Foe | None = None


class Hazard(Record):
    """Something to roll against: what the character tries, how hard, and what happens if it goes wrong."""
    action: Text
    difficulty: Difficulty = 'normal'
    threat: Text | Threat


class Lock(Record):
    # The item that opens it, if any; without it, a roll to pick or force it at this difficulty.
    key: Id | None = None
    difficulty: Difficulty = 'normal'


class InteriorLevel(Record):
    id: Id
    name: Text
    summary: str = Field(default='', max_length=400)


class MapAt(Record):
    """Where a room sits on the drawn rooms map, from 0 to 1 across and down (left out, rooms are laid out by level)."""
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Room(Record):
    id: Id
    name: Text
    level: Id | None = None
    kind: Id  # hall, cell, shrine, cavern, stair, vault... open, like place kinds
    size: RoomSize = 'room'
    light: Light = 'dark'
    summary: Text
    features: list[Text] = Field(default_factory=list, max_length=8)
    # Found only by searching (or by a passage that is found).
    hidden: bool = False
    foes: list[Foe] = Field(default_factory=list, max_length=6)
    hazard: Hazard | None = None
    # Item ids (the world's items) lying here to be found.
    loot: list[Id] = Field(default_factory=list, max_length=8)
    # What the narrator may tell when the room is looked at closely.
    lore: str = Field(default='', max_length=1000)
    map: MapAt | None = None
    source: Id


class Passage(Record):
    """A way between two rooms; `one_way` goes from the first to the second only."""
    between: tuple[Id, Id]
    kind: PassageKind = 'open'
    summary: str = Field(default='', max_length=300)
    lock: Lock | None = None
    hidden: bool = False
    one_way: bool = False
    trap: Hazard | None = None


class Wander(Record):
    """An entry of the interior's own encounter table, like a region's road encounters: a moment, or a roll."""
    weight: int = Field(default=1, ge=1, le=10)
    text: str = Field(default='', max_length=400)
    action: str = Field(default='', max_length=200)
    difficulty: Difficulty | None = None
    threat: Text | Threat | None = None

    @model_validator(mode='after')
    def check(self):
        if not self.text and not (self.action and self.difficulty and self.threat):
            raise ValueError('A wandering encounter is a text, or an action with a difficulty and a threat.')
        return self


class InteriorAt(Record):
    """Where the way in is: a town's place, a travel-map stop, or an authored hex site."""
    city: Id | None = None
    place: Id | None = None
    node: Id | None = None
    site: Id | None = None

    @model_validator(mode='after')
    def check(self):
        if not (self.place or self.node or self.site):
            raise ValueError('An interior is entered from a place, a travel-map stop or a site.')
        if self.place and not self.city:
            raise ValueError('A place is named with its city.')
        return self


class Interior(Record):
    schema_version: Literal[1]
    id: Id
    name: Text
    world: Id
    style: InteriorStyle
    summary: Text
    at: InteriorAt
    entrance: Id
    levels: list[InteriorLevel] = Field(default_factory=list, max_length=12)
    rooms: list[Room] = Field(min_length=1, max_length=120)
    passages: list[Passage] = Field(default_factory=list)
    wanders: list[Wander] = Field(default_factory=list, max_length=20)
    # A wandering encounter is rolled every this many moves.
    wander_every: int = Field(default=3, ge=1, le=20)
    sources: dict[Id, Source] = Field(min_length=1)

    @model_validator(mode='after')
    def check(self):
        rooms = [room.id for room in self.rooms]
        twice = sorted({room for room in rooms if rooms.count(room) > 1})
        if twice:
            raise ValueError(f'Room ids are used twice: {twice}.')
        known = set(rooms)
        if self.entrance not in known:
            raise ValueError(f'The entrance {self.entrance} is not a room.')
        levels = {level.id for level in self.levels}
        stray = sorted({room.level for room in self.rooms if room.level and room.level not in levels})
        if stray:
            raise ValueError(f'Rooms name unknown levels: {stray}.')
        ends = sorted({end for passage in self.passages for end in passage.between if end not in known})
        if ends:
            raise ValueError(f'Passages name unknown rooms: {ends}.')
        if any(passage.between[0] == passage.between[1] for passage in self.passages):
            raise ValueError('A passage joins two different rooms.')
        unsourced = sorted({room.source for room in self.rooms} - set(self.sources))
        if unsourced:
            raise ValueError(f'Rooms cite sources the file does not list: {unsourced}.')
        cut_off = sorted(known - self.reachable())
        if cut_off:
            raise ValueError(f'No passage reaches these rooms from the entrance: {cut_off}.')
        return self

    def reachable(self) -> set[str]:
        """The rooms one can get to from the entrance (hidden and locked ways count: they can be found or opened)."""
        ways: dict[str, set[str]] = {}
        for passage in self.passages:
            a, b = passage.between
            ways.setdefault(a, set()).add(b)
            if not passage.one_way:
                ways.setdefault(b, set()).add(a)
        seen, todo = {self.entrance}, [self.entrance]
        while todo:
            for room in ways.get(todo.pop(), ()):
                if room not in seen:
                    seen.add(room)
                    todo.append(room)
        return seen
