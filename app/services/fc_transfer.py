import pandas as pd
from app.services.fc_planning import calculate_fc_plan


def calculate_fc_transfers(
    replenish_weeks: int = 8,
    channel: str = "All",
    account: str = "Nexlev"
) -> pd.DataFrame:
    """
    FC Transfer Engine

    Logic:
    1. Get FC planning output
    2. Identify excess inventory FCs
    3. Identify shortage FCs
    4. Transfer excess to shortage within same SKU
    """

    df = calculate_fc_plan(
    replenish_weeks=replenish_weeks,
    channel=channel,
    account=account
)

    transfers = []

    # -------------------------------------------------
    # Calculate excess inventory
    # -------------------------------------------------
    df["excess"] = (df["fc_inventory"] - df["required_units"]).clip(lower=0)

    # -------------------------------------------------
    # Process SKU wise
    # -------------------------------------------------
    for sku in df["sku"].unique():

        sku_df = df[df["sku"] == sku].copy()

        # Sort highest shortage first
        shortage_fcs = (
            sku_df[sku_df["fc_shortfall"] > 0]
            .sort_values("fc_shortfall", ascending=False)
        )

        # Sort highest excess first
        excess_fcs = (
            sku_df[sku_df["excess"] > 0]
            .sort_values("excess", ascending=False)
        )

        for s_idx, short_row in shortage_fcs.iterrows():

            remaining_shortage = short_row["fc_shortfall"]

            for e_idx, excess_row in excess_fcs.iterrows():

                if remaining_shortage <= 0:
                    break

                available_excess = df.loc[e_idx, "excess"]

                transfer_qty = min(available_excess, remaining_shortage)

                if transfer_qty > 0:
                    transfers.append(
                        {
                            "sku": sku,
                            "from_fc": excess_row["fulfillment_center"],
                            "to_fc": short_row["fulfillment_center"],
                            "transfer_qty": int(round(transfer_qty, 0)),
                        }
                    )

                    # Reduce excess and shortage dynamically
                    df.loc[e_idx, "excess"] -= transfer_qty
                    remaining_shortage -= transfer_qty

    # -------------------------------------------------
    # Aggregate transfers
    # -------------------------------------------------
    df_transfer = pd.DataFrame(transfers)

    if not df_transfer.empty:
        df_transfer = (
            df_transfer
            .groupby(["sku", "from_fc", "to_fc"], as_index=False)
            .agg(transfer_qty=("transfer_qty", "sum"))
        )

    return df_transfer