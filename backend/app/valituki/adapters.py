"""Integration points. Every external system is an interface with a mock implementation.

Nothing here talks to a real system. The mocks read from and write to the demo state so the flow is visible end to end;
the docstrings name what a production implementation would connect to. See README → "Integraatiopisteet".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Optional

from app.valituki.models import (
    Booking,
    HandoverSummary,
    Notification,
    ProfessionalReviewTask,
    Referral,
    Therapist,
    TherapistAvailability,
    ValitukiState,
    WaitingListEpisode,
)


class WaitingListAdapter(ABC):
    """Production: the wellbeing services county's referral / waiting-list system (e.g. the patient administration
    system's queue for short therapy or rehabilitative psychotherapy)."""

    @abstractmethod
    def referral_for(self, state: ValitukiState, client_id: str) -> Optional[Referral]: ...

    @abstractmethod
    def episode_for(self, state: ValitukiState, client_id: str) -> Optional[WaitingListEpisode]: ...

    @abstractmethod
    def is_allocatable(self, state: ValitukiState, client_id: str) -> bool:
        """Whether the waiting list allows therapist allocation to begin for this client."""


class HealthRecordAdapter(ABC):
    """Production: storing the client-approved handover to the patient record (e.g. Kanta / the county's EHR)."""

    @abstractmethod
    def publish_handover(self, state: ValitukiState, handover: HandoverSummary) -> dict: ...


class TherapistDirectoryAdapter(ABC):
    """Production: the provider / service-voucher directory and the therapists' own calendars."""

    @abstractmethod
    def therapists(self, state: ValitukiState) -> list[Therapist]: ...

    @abstractmethod
    def free_slots(self, state: ValitukiState, therapist_id: str) -> list[TherapistAvailability]: ...

    @abstractmethod
    def sync_calendars(self, state: ValitukiState, therapist_id: Optional[str] = None) -> list[TherapistAvailability]: ...


class AppointmentAdapter(ABC):
    """Production: the booking system (appointment reservation and confirmation)."""

    @abstractmethod
    def book(self, state: ValitukiState, booking: Booking) -> Booking: ...


class NotificationAdapter(ABC):
    """Production: in-app push, SMS or e-mail according to the client's communication preference."""

    @abstractmethod
    def send(self, state: ValitukiState, notification: Notification) -> Notification: ...


class ProfessionalTaskAdapter(ABC):
    """Production: the care coordinator's work queue in the professional system."""

    @abstractmethod
    def create_task(self, state: ValitukiState, task: ProfessionalReviewTask) -> ProfessionalReviewTask: ...


# --- Mocks ---------------------------------------------------------------------------------------------------------

class MockWaitingListAdapter(WaitingListAdapter):
    def referral_for(self, state, client_id):
        return next((r for r in state.referrals if r.clientId == client_id), None)

    def episode_for(self, state, client_id):
        return next((e for e in state.episodes if e.clientId == client_id), None)

    def is_allocatable(self, state, client_id):
        episode = self.episode_for(state, client_id)
        return bool(episode and episode.status == 'waiting' and episode.allocatableFrom <= state.currentDate)


class MockHealthRecordAdapter(HealthRecordAdapter):
    def publish_handover(self, state, handover):
        return {'sent': False, 'reference': None,
                'note': 'Demo: the summary was not sent to a patient record system. In production it would be stored here.'}


class MockTherapistDirectoryAdapter(TherapistDirectoryAdapter):
    WEEKS_AHEAD = 5

    def therapists(self, state):
        return list(state.therapists)

    def free_slots(self, state, therapist_id):
        return sorted((s for s in state.slots if s.therapistId == therapist_id and s.status == 'free'
                       and s.start[:10] > state.currentDate), key=lambda s: (s.start, s.id))

    def sync_calendars(self, state, therapist_id=None):
        """Materialise the therapists' recurring weekly times as bookable slots – but only while they have a free client
        place. The first new slot is at least `leadTimeDays` away (nearer times belong to existing clients)."""
        from app.valituki.store import next_id, now

        created: list[TherapistAvailability] = []
        today = date.fromisoformat(state.currentDate)
        state.slots = [s for s in state.slots if s.status == 'booked' or s.start[:10] > state.currentDate]
        for therapist in state.therapists:
            if therapist_id and therapist.id != therapist_id:
                continue
            if not therapist.active or therapist.currentCapacity >= therapist.maxCapacity:
                continue
            existing = {s.start for s in state.slots if s.therapistId == therapist.id}
            start = today + timedelta(days=therapist.leadTimeDays)
            for offset in range(self.WEEKS_AHEAD * 7):
                day = start + timedelta(days=offset)
                for template in therapist.availableTimes:
                    if day.weekday() != template.weekday:
                        continue
                    stamp_start = f'{day.isoformat()}T{template.time}'
                    if stamp_start in existing:
                        continue
                    stamp = now(state)
                    slot = TherapistAvailability(id=next_id(state, 'slot'), therapistId=therapist.id, start=stamp_start,
                                                 formats=list(template.formats), createdAt=stamp, updatedAt=stamp,
                                                 createdBy='therapist_directory_adapter', source='calendar_sync')
                    state.slots.append(slot)
                    existing.add(stamp_start)
                    created.append(slot)
        return created

    def withdraw_slots(self, state, therapist_id: str) -> None:
        """A therapist without free client places has no bookable new-client slots."""
        state.slots = [s for s in state.slots if not (s.therapistId == therapist_id and s.status == 'free')]


class MockAppointmentAdapter(AppointmentAdapter):
    def book(self, state, booking):
        state.bookings.append(booking)
        return booking


class InAppNotificationAdapter(NotificationAdapter):
    """The demo delivers every notification in the app only."""

    def send(self, state, notification):
        state.notifications.append(notification)
        return notification


class InMemoryProfessionalTaskAdapter(ProfessionalTaskAdapter):
    def create_task(self, state, task):
        state.tasks.append(task)
        return task


waiting_list: WaitingListAdapter = MockWaitingListAdapter()
health_records: HealthRecordAdapter = MockHealthRecordAdapter()
therapist_directory: MockTherapistDirectoryAdapter = MockTherapistDirectoryAdapter()
appointments: AppointmentAdapter = MockAppointmentAdapter()
notifications: NotificationAdapter = InAppNotificationAdapter()
professional_tasks: ProfessionalTaskAdapter = InMemoryProfessionalTaskAdapter()


def describe() -> list[dict[str, str]]:
    """Shown in the professional UI so the integration points are visible without pretending they exist."""
    return [
        {'name': 'WaitingListAdapter', 'mock': 'MockWaitingListAdapter',
         'production': "Referral and waiting list data from the wellbeing services county's patient administration system"},
        {'name': 'HealthRecordAdapter', 'mock': 'MockHealthRecordAdapter',
         'production': "Storing the approved summary in the patient record (Kanta / the county's patient record system)"},
        {'name': 'TherapistDirectoryAdapter', 'mock': 'MockTherapistDirectoryAdapter',
         'production': "Service provider and service voucher directory, and the therapists' calendars"},
        {'name': 'AppointmentAdapter', 'mock': 'MockAppointmentAdapter', 'production': 'Appointment booking system'},
        {'name': 'NotificationAdapter', 'mock': 'InAppNotificationAdapter',
         'production': "App notification, text message or email, as the client prefers"},
        {'name': 'ProfessionalTaskAdapter', 'mock': 'InMemoryProfessionalTaskAdapter',
         'production': "The care team's work queue in the professional's system"},
    ]


def next_weekday_on_or_after(iso: str, weekday: int) -> str:
    day = date.fromisoformat(iso[:10])
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day.isoformat()
