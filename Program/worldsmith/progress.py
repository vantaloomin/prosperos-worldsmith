"""How far a long model job has got, for the screen to show while it waits: drafting a world, a town, or one list.

Each job is kept by its world folder and kind, in memory only; the screen polls /api/progress while its request runs.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from worldsmith import worlds

# The steps of each kind of job, in order, with the line the screen shows for each.
STEPS: dict[str, dict[str, str]] = {
    'world': {'outline': 'Writing the outline: regions, towns and roads',
              'people': 'Writing the people: names, careers, prices and climate',
              'play': 'Writing the factions and their jobs',
              'story': 'Writing the story: arcs, encounters, sites, truths and lore',
              'check': "Checking the world against Dungeon's format"},
    'town': {'write': 'Writing the town: neighborhoods, places, people and prices',
             'check': "Checking the town against Dungeon's format"},
    'draft': {'write': 'Writing the draft',
              'check': "Checking the draft against Dungeon's format"},
}
JOBS: dict[str, dict] = {}


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def key_of(opened: worlds.Opened, job: str) -> str:
    return f'{opened.folder}|{job}'


def report(opened: worlds.Opened | None, job: str, step: str, attempt: int = 1, problems: list[str] | None = None,
           about: str = ''):
    """Note the step a job is on (and which try at it, with what was wrong with the last one)."""
    if opened is None:
        return
    steps = STEPS[job]
    was = JOBS.get(key_of(opened, job)) or {}
    JOBS[key_of(opened, job)] = {'started': was.get('started') or now_text(), 'running': True, 'job': job,
                                 'about': about or was.get('about', ''), 'step': step,
                                 'index': list(steps).index(step) + 1, 'of': len(steps), 'label': steps[step],
                                 'attempt': attempt, 'step_started': now_text(), 'problems': (problems or [])[:3]}


def finish(opened: worlds.Opened, job: str, error: str | None = None):
    was = JOBS.get(key_of(opened, job)) or {}
    JOBS[key_of(opened, job)] = {**was, 'running': False, 'error': error, 'ended': now_text()}


def running(opened: worlds.Opened, job: str) -> bool:
    return bool((JOBS.get(key_of(opened, job)) or {}).get('running'))


def of(opened: worlds.Opened, job: str) -> dict:
    """Where the job is: {running, job, about, step, index, of, label, attempt, started, step_started, problems}."""
    if job not in STEPS:
        return {'running': False}
    return JOBS.get(key_of(opened, job)) or {'running': False}


@contextmanager
def tracked(opened: worlds.Opened, job: str, about: str = '') -> Iterator[None]:
    """Run a job from a fresh start, and mark it ended (with its error, if it failed) however it ends."""
    JOBS.pop(key_of(opened, job), None)
    if about:
        JOBS[key_of(opened, job)] = {'running': False, 'about': about}
    try:
        yield
    except Exception as error:
        finish(opened, job, getattr(error, 'message', None) or str(error))
        raise
    finish(opened, job)
