from datetime import datetime, date, time, timedelta, timezone


IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def now_ist() -> datetime:
    return datetime.now(IST)


def current_working_week_start(now: datetime = None) -> date:
    """Returns the Sunday that starts the data week currently being worked on.

    Convention (per product): a "working week" analyzes the prior calendar
    Sun-Sat data. So on Wed May 13 IST the working week is May 3-9 (Week 19).
    At Sunday 00:00 IST the working week rolls forward.
    """
    if now is None:
        now = now_ist()
    today = now.date()
    days_since_sunday = (today.weekday() + 1) % 7
    this_sunday = today - timedelta(days=days_since_sunday)
    return this_sunday - timedelta(days=7)


def week_end(week_start: date) -> date:
    return week_start + timedelta(days=6)


def week_label(week_start: date) -> str:
    """ISO-week numbered using the Monday inside the Sun-Sat week."""
    monday = week_start + timedelta(days=1)
    iso = monday.isocalendar()
    return f"Week {iso[1]}"


def is_week_locked(week_start: date, now: datetime = None) -> bool:
    """A week locks at the next Sunday 00:00 IST after its working window ends.

    Working window for week_start = week_start + 7 days .. week_start + 13 days.
    Lock at week_start + 14 days, 00:00 IST.
    """
    if now is None:
        now = now_ist()
    lock_at = datetime.combine(week_start + timedelta(days=14), time(0, 0), tzinfo=IST)
    return now >= lock_at
