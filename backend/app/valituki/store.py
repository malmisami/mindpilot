"""Repository over one JSON file (the same pattern as the earlier loop store), plus id, clock and lookup helpers.

The demo has its own clock: `currentDate` moves only with the demo controls, and every timestamp is derived from it so
that a replayed demo is fully deterministic. Within a day the clock only moves forward.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from threading import RLock
from typing import Iterator, Optional

from app.config import settings
from app.valituki.models import STATE_VERSION, ClientProfile, Therapist, ValitukiState


class NotFoundError(Exception):
    """A referenced record does not exist (HTTP 404)."""


class ValitukiRepository:
    """Load / save / transaction over the JSON state file. Swap this class for a database-backed one in production."""

    def __init__(self) -> None:
        self._lock = RLock()

    @staticmethod
    def _path() -> Path:
        return Path(settings.VALITUKI_STATE_PATH)

    def load(self) -> ValitukiState:
        with self._lock:
            path = self._path()
            if path.exists():
                try:
                    loaded = ValitukiState.model_validate_json(path.read_text(encoding='utf-8'))
                    if loaded.version == STATE_VERSION:
                        return loaded
                except ValueError:
                    pass  # a corrupt or outdated demo state is rebuilt from the seed
            return self.reset()

    def save(self, state: ValitukiState) -> None:
        with self._lock:
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(state.model_dump(), ensure_ascii=False), encoding='utf-8')
            tmp.replace(path)

    @contextmanager
    def transaction(self) -> Iterator[ValitukiState]:
        """Load, mutate and save under one lock. Nothing is saved if the block raises."""
        with self._lock:
            state = self.load()
            yield state
            self.save(state)

    def reset(self) -> ValitukiState:
        from app.valituki.seed import build_seed_state  # local import: the seed runs the whole engine

        with self._lock:
            state = build_seed_state()
            self.save(state)
            return state

    def replace(self, state: ValitukiState) -> ValitukiState:
        with self._lock:
            self.save(state)
            return state


repository = ValitukiRepository()


# --- ids and the demo clock -------------------------------------------------------------------------------------------

def next_id(state: ValitukiState, prefix: str) -> str:
    state.counters[prefix] = state.counters.get(prefix, 0) + 1
    return f'{prefix}-{state.counters[prefix]:04d}'


def next_seq(state: ValitukiState, key: str) -> int:
    state.counters[f'seq:{key}'] = state.counters.get(f'seq:{key}', 0) + 1
    return state.counters[f'seq:{key}']


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(':')
    return int(hours) * 60 + int(minutes)


def now(state: ValitukiState, at: Optional[str] = None) -> str:
    """A timestamp on the demo date. The clock ticks per cascade, not per record: `at` ('HH:MM') moves it forward to
    that time (e.g. a check-in at 14:40), and the agents' reactions to it land one minute later (14:41) – however many
    records they write. The clock never goes backwards within a day; records with equal times keep their sequence."""
    if state.clockDate != state.currentDate:
        state.clockDate = state.currentDate
        state.clockMinutes = 8 * 60
        state.clockReact = False
    if at:
        if _minutes(at) > state.clockMinutes:
            state.clockMinutes = _minutes(at)
            state.clockReact = True
    elif state.clockReact:
        state.clockMinutes = min(state.clockMinutes + 1, 23 * 60 + 59)
        state.clockReact = False
    return f'{state.currentDate}T{state.clockMinutes // 60:02d}:{state.clockMinutes % 60:02d}'


def begin_action(state: ValitukiState) -> None:
    """A new user action (one API mutation) happens a couple of minutes after the previous one on the demo clock."""
    if state.clockDate != state.currentDate:
        now(state)
    state.clockMinutes = min(state.clockMinutes + 2, 23 * 60 + 59)
    state.clockReact = False


def add_days(iso_date: str, days: int) -> str:
    return (date.fromisoformat(iso_date[:10]) + timedelta(days=days)).isoformat()


def days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days


def weekday(iso_date: str) -> int:
    return date.fromisoformat(iso_date[:10]).weekday()


# --- lookups ---------------------------------------------------------------------------------------------------------

def get_client(state: ValitukiState, client_id: str) -> ClientProfile:
    for client in state.clients:
        if client.id == client_id:
            return client
    raise NotFoundError(f'Client {client_id} not found.')


def get_therapist(state: ValitukiState, therapist_id: str) -> Therapist:
    for therapist in state.therapists:
        if therapist.id == therapist_id:
            return therapist
    raise NotFoundError(f'Therapist {therapist_id} not found.')


def find(items: list, item_id: str, label: str = 'Record'):
    for item in items:
        if item.id == item_id:
            return item
    raise NotFoundError(f'{label} {item_id} not found.')


def maybe_find(items: list, item_id: Optional[str]):
    if item_id is None:
        return None
    return next((item for item in items if item.id == item_id), None)
