def add_risk_flags(df, weeks: int):
    weekly_velocity = df["sales_velocity"] / max(weeks, 1)

    df["is_risky"] = df["Total AM Inventory"] < weekly_velocity
    df["is_overstock"] = df["Total AM Inventory"] > (weekly_velocity * 8)

    return df