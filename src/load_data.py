"""
Shared data loading for the U.S. flight delay analysis.

Every notebook imports from here so the cleaning steps only live in one place:
    from src.load_data import load_flights
    df = load_flights("data/flights.csv")
"""

from pathlib import Path

import pandas as pd

# The DOT and the airline industry count a flight as delayed at 15+ minutes late.
DELAY_THRESHOLD_MIN = 15

AIRLINE_NAMES = {
    "AA": "American",
    "AS": "Alaska",
    "B6": "JetBlue",
    "DL": "Delta",
    "EV": "ExpressJet",
    "F9": "Frontier",
    "HA": "Hawaiian",
    "MQ": "Envoy",
    "NK": "Spirit",
    "OO": "SkyWest",
    "UA": "United",
    "US": "US Airways",
    "VX": "Virgin America",
    "WN": "Southwest",
}

SEASONS = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring", 5: "Spring",
    6: "Summer", 7: "Summer", 8: "Summer",
    9: "Fall", 10: "Fall", 11: "Fall",
}

DELAY_CAUSES = {
    "LATE_AIRCRAFT_DELAY": "Late inbound aircraft",
    "AIRLINE_DELAY": "Airline (crew, maintenance, ops)",
    "AIR_SYSTEM_DELAY": "Air traffic system",
    "WEATHER_DELAY": "Weather",
    "SECURITY_DELAY": "Security",
}


def build_october_airport_map(df: pd.DataFrame) -> dict:
    """
    The 2015 file stores October airports as 5-digit DOT IDs (e.g. "10397")
    instead of IATA codes ("ATL"). Rebuild the mapping from the data itself:
    the same airline + flight number + distance in Sep/Nov flies the same route,
    so each numeric ID gets the IATA code it lines up with most often.
    """
    key = ["AIRLINE", "FLIGHT_NUMBER", "DISTANCE"]
    is_numeric = df["ORIGIN_AIRPORT"].str.isdigit()

    october = df.loc[is_numeric, key + ["ORIGIN_AIRPORT", "DESTINATION_AIRPORT"]].drop_duplicates()
    neighbors = (
        df.loc[~is_numeric & df["MONTH"].isin([9, 11]),
               key + ["ORIGIN_AIRPORT", "DESTINATION_AIRPORT"]]
        .drop_duplicates()
    )

    pairs = october.merge(neighbors, on=key, suffixes=("_ID", "_IATA"))
    votes = pd.concat([
        pairs[["ORIGIN_AIRPORT_ID", "ORIGIN_AIRPORT_IATA"]].set_axis(["id", "iata"], axis=1),
        pairs[["DESTINATION_AIRPORT_ID", "DESTINATION_AIRPORT_IATA"]].set_axis(["id", "iata"], axis=1),
    ])

    best = (
        votes.value_counts()
        .reset_index(name="n")
        .sort_values("n", ascending=False)
        .drop_duplicates("id")
    )
    return dict(zip(best["id"], best["iata"]))


def load_flights(path="data/flights.csv", fix_october=True, verbose=True) -> pd.DataFrame:
    """Load the 2015 DOT on-time file, fix October airport codes, and add analysis columns."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download flights.csv from Kaggle (usdot/flight-delays) "
            "and put it in the data/ folder."
        )

    df = pd.read_csv(
        path,
        dtype={"ORIGIN_AIRPORT": str, "DESTINATION_AIRPORT": str, "TAIL_NUMBER": str},
        low_memory=False,
    )

    if fix_october:
        id_to_iata = build_october_airport_map(df)
        for col in ["ORIGIN_AIRPORT", "DESTINATION_AIRPORT"]:
            df[col] = df[col].replace(id_to_iata)

        if verbose:
            october = df["MONTH"] == 10
            still_numeric = (
                df.loc[october, "ORIGIN_AIRPORT"].str.isdigit()
                | df.loc[october, "DESTINATION_AIRPORT"].str.isdigit()
            )
            print(f"October airport fix: mapped {len(id_to_iata)} airport IDs, "
                  f"{1 - still_numeric.mean():.2%} of October flights recovered "
                  f"({still_numeric.sum():,} left unmatched)")

    # Analysis columns
    df["AIRLINE_NAME"] = df["AIRLINE"].map(AIRLINE_NAMES)
    df["SEASON"] = df["MONTH"].map(SEASONS)
    df["DEP_HOUR"] = df["SCHEDULED_DEPARTURE"] // 100
    # 1.0 = delayed, 0.0 = on time, NaN = cancelled/diverted (no arrival, so not counted either way).
    # Using floats means .mean() gives the delay rate and skips cancelled flights automatically.
    df["IS_DELAYED"] = (
        (df["ARRIVAL_DELAY"] >= DELAY_THRESHOLD_MIN).astype(float).where(df["ARRIVAL_DELAY"].notna())
    )

    if verbose:
        print(f"Loaded {len(df):,} flights | {df['IS_DELAYED'].mean():.1%} delayed "
              f"{DELAY_THRESHOLD_MIN}+ min (completed flights only)")
    return df
