def format_fc_allocation(df):
    if df is None or df.empty:
        return []

    return [
        {
            "model": row.get("model"),
            "sku": row.get("sku"),
            "fulfillment_center": row.get("fulfillment_center"),
            "weekly_velocity": int(round(row.get("weekly_velocity", 0))),
            "fc_inventory": int(round(row.get("fc_inventory", 0))),
            "transfer_in": int(round(row.get("transfer_in", 0))),
            "target_cover_units": int(round(row.get("target_cover_units", 0))),
            "post_transfer_stock": int(round(row.get("post_transfer_stock", 0))),
            "coverage_gap_units": int(round(row.get("coverage_gap_units", 0))),
            "send_qty": int(round(row.get("send_qty", 0))),
            "expected_units": int(round(row.get("expected_units", 0))),
            "velocity_fill_ratio": float(row.get("velocity_fill_ratio", 0)),
            "velocity_flag": row.get("velocity_flag"),
        }
        for _, row in df.iterrows()
    ]