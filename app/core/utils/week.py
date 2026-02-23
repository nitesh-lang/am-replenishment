def to_week(dt):
    year, week, _ = dt.isocalendar()
    return f"{year}-{week:02d}"
