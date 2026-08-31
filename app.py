from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import threading
import time
from flask import Flask, jsonify, request, send_from_directory
import requests

app = Flask(__name__, static_folder=".", static_url_path="")

OPAP_GAME_IDS = {"joker": 5104, "lotto": 5103}


@app.route("/")
def serve_index():
  return send_from_directory(".", "index.html")


@app.route("/<path:path>")
def serve_static(path):
  return send_from_directory(".", path)


def weekly_daterange(start_date, end_date):
  current = start_date
  while current <= end_date:
    week_end = current + timedelta(days=6)
    if week_end > end_date:
      week_end = end_date
    yield current, week_end
    current = week_end + timedelta(days=1)


def perform_download_for_game(game_type):
  game_id = OPAP_GAME_IDS[game_type]
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
      "Referer": "https://www.opap.gr/",
      "Origin": "https://www.opap.gr",
  }

  start_date = datetime(1997, 1, 1)
  end_date = datetime.now()
  all_draws_dict = {}

  ranges = list(weekly_daterange(start_date, end_date))

  for from_dt, to_dt in ranges:
    fromDate = from_dt.strftime("%Y-%m-%d")
    toDate = to_dt.strftime("%Y-%m-%d")
    url = f"https://api.opap.gr/draws/v3.0/{game_id}/draw-date/{fromDate}/{toDate}"

    try:
      response = requests.get(url, headers=headers, timeout=20)
      if response.status_code == 200:
        data = response.json()
        draws_list = (
            data
            if isinstance(data, list)
            else data.get("content", data.get("draws", []))
        )
        for d in draws_list:
          did = d.get("drawId") or d.get("drawNo")
          if did:
            all_draws_dict[did] = d
    except Exception as e:
      print(f"Σφάλμα στο διάστημα {fromDate} - {toDate}: {e}")

  final_draws = list(all_draws_dict.values())
  final_draws.sort(key=lambda x: x.get("drawId") or x.get("drawNo", 0))

  if final_draws:
    filename = f"{game_type}_draws.json"
    with open(filename, "w", encoding="utf-8") as f:
      json.dump(final_draws, f, ensure_ascii=False, indent=4)
  return len(final_draws)


@app.route("/api/download-draws/<game_type>", methods=["POST"])
def trigger_download(game_type):
  if game_type not in OPAP_GAME_IDS:
    return jsonify({"status": "error", "message": "Μη έγκυρο παιχνίδι"}), 400
  try:
    count = perform_download_for_game(game_type)
    return jsonify({
        "status": "success",
        "count": count,
        "message": f"Επιτυχής λήψη {count} κληρώσεων.",
    })
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/load-draws/<game_type>", methods=["GET"])
def get_stored_draws(game_type):
  filename = f"{game_type}_draws.json"
  if not os.path.exists(filename):
    return jsonify({"last_update": "Άγνωστη", "draws": []})

  mtime = os.path.getmtime(filename)
  last_update = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

  with open(filename, "r", encoding="utf-8") as f:
    try:
      data = json.load(f)
      return jsonify({"last_update": last_update, "draws": data})
    except:
      return jsonify({"last_update": last_update, "draws": []})


def automated_updater():
  while True:
    now = datetime.now()
    if (now.hour == 23 and now.minute == 0) or (now.hour == 2 and now.minute == 0):
      print("⏰ [Auto Update] Έναρξη αυτόματης ενημέρωσης κληρώσεων...")
      for g in ["joker", "lotto"]:
        try:
          perform_download_for_game(g)
          print(f"✅ [Auto Update] Ολοκληρώθηκε για {g}")
        except Exception as e:
          print(f"❌ [Auto Update Error] {g}: {e}")
      time.sleep(70)
    time.sleep(30)


if __name__ == "__main__":
  t = threading.Thread(target=automated_updater, daemon=True)
  t.start()
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)