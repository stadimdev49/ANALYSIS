from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import pandas as pd
import requests

OPAP_GAME_IDS = {"joker": 5104, "lotto": 5103}


def weekly_daterange(start_date, end_date):
    """Δημιουργεί διαστήματα ακριβώς 7 ημερών για να μην ξεπερνιούνται τα όρια του API[cite: 1]."""
    current = start_date
    while current <= end_date:
        week_end = current + timedelta(days=6)
        if week_end > end_date:
            week_end = end_date
        yield current, week_end
        current = week_end + timedelta(days=1)


def download_all_draws():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
        "Referer": "https://www.opap.gr/",
        "Origin": "https://www.opap.gr",
    }

    start_date = datetime(1997, 1, 1)
    end_date = datetime.now()

    for game_type, game_id in OPAP_GAME_IDS.items():
        print(
            f"Λήψη πλήρους ιστορικού ανά εβδομάδα για το παιχνίδι:"
            f" {game_type.upper()}...[cite: 1]"
        )
        all_draws_dict = {}

        for from_dt, to_dt in weekly_daterange(start_date, end_date):
            fromDate = from_dt.strftime("%Y-%m-%d")
            toDate = to_dt.strftime("%Y-%m-%d")

            url = f"https://api.opap.gr/draws/v3.0/{game_id}/draw-date/{fromDate}/{toDate}"

            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    draws_list = []
                    if isinstance(data, list):
                        draws_list = data
                    elif isinstance(data, dict):
                        draws_list = data.get("content", data.get("draws", []))

                    for d in draws_list:
                        did = d.get("drawId") or d.get("drawNo")
                        if did:
                            all_draws_dict[did] = d
            except Exception as e:
                print(
                    f" -> Σφάλμα στο διάστημα {fromDate} - {toDate}:"
                    f" {e}[cite: 1]"
                )

        final_draws = list(all_draws_dict.values())
        final_draws.sort(key=lambda x: x.get("drawId") or x.get("drawNo", 0))

        if final_draws:
            filename = f"{game_type}_draws.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(final_draws, f, ensure_ascii=False, indent=4)
            print(
                f"✅ Επιτυχής αποθήκευση συνολικά {len(final_draws)}"
                f" μοναδικών κληρώσεων στο αρχείο: {filename}\n"
                f"[cite: 1]"
            )
        else:
            print(f"❌ Αποτυχία λήψης κληρώσεων για {game_type}.\n")


def load_and_process_game(game_type):
    filename = f"{game_type}_draws.json"
    if not Path(filename).exists():
        print(f"Το αρχείο {filename} δεν βρέθηκε. Εκτελέστε πρώτα τη λήψη.")
        return

    with open(filename, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    parsed = []
    for d in raw_data:
        did = d.get("drawId") or d.get("drawNo")
        draw_time = d.get("drawTime")
        if isinstance(draw_time, int):
            dt = datetime.fromtimestamp(draw_time / 1000.0)
        else:
            dt = datetime.fromisoformat(str(draw_time).replace("Z", "+00:00"))

        winning_numbers = d.get("winningNumbers", {})
        numbers = winning_numbers.get("list", [])
        if not numbers and "results" in d:
            numbers = d.get("results", [])

        if numbers:
            parsed.append(
                {
                    "draw_id": did,
                    "date": dt,
                    "year": dt.year,
                    "numbers": sorted(numbers),
                }
            )

    df = pd.DataFrame(parsed)
    if df.empty:
        return

    df = df.sort_values(by="date", ascending=False).reset_index(drop=True)
    max_num = 45 if game_type == "joker" else 49
    all_nums = list(range(1, max_num + 1))

    print(f"\n================ ANKΛΥΣΗ ΓΙΑ {game_type.upper()} ================")

    # 1. Συχνότητες & Καθυστερήσεις (Συνολικά & Ανά Έτος)
    flat_all = [num for sublist in df["numbers"] for num in sublist]
    overall_freq = pd.Series(flat_all).value_counts().to_dict()

    overall_delays = {}
    for num in all_nums:
        matching = df[df["numbers"].apply(lambda x: num in x)]
        overall_delays[num] = (
            matching.index[0] if not matching.empty else len(df)
        )

    yearly_stats = {}
    for year in df["year"].unique():
        df_y = df[df["year"] == year].reset_index(drop=True)
        flat_y = [num for sublist in df_y["numbers"] for num in sublist]
        y_freq = pd.Series(flat_y).value_counts().to_dict()

        y_delays = {}
        for num in all_nums:
            matching_y = df_y[df_y["numbers"].apply(lambda x: num in x)]
            y_delays[num] = (
                matching_y.index[0] if not matching_y.empty else len(df_y)
            )
        yearly_stats[year] = {"freq": y_freq, "delays": y_delays}

    print(f"Υπολογίστηκαν οι συχνότητες και καθυστερήσεις για {len(df.year.unique())} έτη.")

    # 2. Κατηγορίες (0, 1, 2, 3+) σε παράθυρα 5, 10, 15, 20 κληρώσεων
    windows = [5, 10, 15, 20]
    last_20_subset = df.head(20)

    print("\n--- ΠΡΟΤΑΣΕΙΣ ΑΡΙΘΜΩΝ ΑΝΑ ΚΑΤΗΓΟΡΙΑ ---")
    for w in windows:
        recent_df = df.head(w)
        w_numbers = [num for sublist in recent_df["numbers"] for num in sublist]
        counts = pd.Series(w_numbers).value_counts()

        categories = {0: [], 1: [], 2: [], "3+": []}
        for num in all_nums:
            c = counts.get(num, 0)
            if c == 0:
                categories[0].append(num)
            elif c == 1:
                categories[1].append(num)
            elif c == 2:
                categories[2].append(num)
            else:
                categories["3+"].append(num)

        print(f"\n[ Παράθυρο Τελευταίων {w} Κληρώσεων ]")
        for cat_key, num_list in categories.items():
            k = (
                min(len(num_list), 3)
                if len(num_list) >= 3
                else min(len(num_list), 2)
            )
            selected = random.sample(num_list, k) if k > 0 else []

            details = []
            for s_num in selected:
                appearances = [
                    row["draw_id"]
                    for _, row in last_20_subset.iterrows()
                    if s_num in row["numbers"]
                ]
                details.append(
                    {"number": s_num, "past_draw_ids": appearances}
                )
            print(f"  Κατηγορία {cat_key} -> {details}")

    # 3. Επικουρική παρακολούθηση τελευταίων 10 κληρώσεων
    print(f"\n--- ΕΠΙΚΟΥΡΙΚΗ ΠΑΡΑΚΟΛΟΥΘΗΣΗ ΤΕΛΕΥΤΑΙΩΝ 10 ΚΛΗΣΕΩΝ ---")
    last_10 = df.head(10)
    for _, row in last_10.iterrows():
        print(
            f"Draw ID: {row['draw_id']} | Ημερομηνία:"
            f" {row['date'].strftime('%Y-%m-%d')} | Αριθμοί:"
            f" {row['numbers']}"
        )


if __name__ == "__main__":
    # Βήμα 1: Λήψη και αποθήκευση όλων των δεδομένων
    download_all_draws()

    # Βήμα 2: Εκτέλεση όλων των αναλύσεων για Τζόκερ και Λόττο
    for game in ["joker", "lotto"]:
        load_and_process_game(game)