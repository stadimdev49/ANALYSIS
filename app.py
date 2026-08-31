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


def fetch_draws_range(game_id, start_date_str, end_date_str):
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
  url = f"https://api.opap.gr/draws/v3.0/{game_id}/draw-date/{start_date_str}/{end_date_str}"
  try:
    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code == 200:
      data = response.json()
      return (
          data
          if isinstance(data, list)
          else data.get("content", data.get("draws", []))
      )
  except Exception as e:
    print(f"Σφάλμα λήψης για {start_date_str} - {end_date_str}: {e}")
  return []


def perform_smart_update(game_type):
  game_id = OPAP_GAME_IDS[game_type]
  filename = f"{game_type}_draws.json"
  
  existing_draws = []
  last_date = datetime(1997, 1, 1)

  # 1. Έλεγχος αν υπάρχουν ήδη αποθηκευμένες κληρώσεις
  if os.path.exists(filename):
    try:
      with open(filename, "r", encoding="utf-8") as f:
        existing_draws = json.load(f)
    except:
      existing_draws = []

  # 2. Αν υπάρχουν δεδομένα, βρίσκουμε την ημερομηνία της τελευταίας κλήρωσης
  if existing_draws:
    # Ταξινομούμε για σιγουριά ώστε η τελευταία να είναι στο τέλος ή βρίσκουμε τη μέγιστη ημερομηνία
    latest_draw = max(existing_draws, key=lambda x: x.get("drawId") or x.get("drawNo", 0))
    draw_time = latest_draw.get("drawTime")
    if draw_time:
      if isinstance(draw_time, (int, float)):
        last_date = datetime.fromtimestamp(draw_time / 1000.0) if draw_time > 1e12 else datetime.fromtimestamp(draw_time)
      else:
        try:
          last_date = datetime.fromisoformat(draw_time.replace("Z", "+00:00")).replace(tzinfo=None)
        except:
          pass

    print(f"📂 Βρέθηκαν {len(existing_draws)} αποθηκευμένες κληρώσεις για {game_type}. Τελευταία ημερομηνία: {last_date.strftime('%Y-%m-%d')}")
    start_date = last_date - timedelta(days=2) # Ασφάλεια 2 ημερών πίσω για τυχόν κפוσίες καθυστερήσεις
  else:
    print(f"📥 Δεν βρέθηκε αρχείο για {game_type}. Γίνεται λήψη ολόκληρου του ιστορικού από 1997...")
    start_date = datetime(1997, 1, 1)

  end_date = datetime.now()
  
  # Αν η τελευταία ημερομηνία είναι σημερινή/μελλοντική, δεν χρειάζεται τίποτα
  if start_date > end_date:
    return len(existing_draws)

  # 3. Λήψη μόνο των νέων δεδομένων σε εβδομαδιαία διαστήματα
  all_draws_dict = { (d.get("drawId") or d.get("drawNo")): d for d in existing_draws }
  
  current = start_date
  new_draws_count = 0
  
  while current <= end_date:
    week_end = current + timedelta(days=6)
    if week_end > end_date:
      week_end = end_date
      
    fromDate = current.strftime("%Y-%m-%d")
    toDate = week_end.strftime("%Y-%m-%d")
    
    draws_list = fetch_draws_range(game_id, fromDate, toDate)
    for d in draws_list:
      did = d.get("drawId") or d.get("drawNo")
      if did and did not in all_draws_dict:
        all_draws_dict[did] = d
        new_draws_count += 1
        
    current = week_end + timedelta(days=1)

  final_draws = list(all_draws_dict.values())
  final_draws.sort(key=lambda x: x.get("drawId") or x.get("drawNo", 0))

  if final_draws:
    with open(filename, "w", encoding="utf-8") as f:
      json.dump(final_draws, f, ensure_ascii=False, indent=4)
      
  print(f"✨ Προστέθηκαν {new_draws_count} νέες κληρώσεις για το {game_type}.")
  return len(final_draws)


@app.route("/api/download-draws/<game_type>", methods=["POST"])
def trigger_download(game_type):
  if game_type not in OPAP_GAME_IDS:
    return jsonify({"status": "error", "message": "Μη έγκυρο παιχνίδι"}), 400
  try:
    count = perform_smart_update(game_type)
    return jsonify({
        "status": "success",
        "count": count,
        "message": f"Επιτυχής ενημέρωση. Συνολικά αρχείο: {count} κληρώσεις.",
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
      print("⏰ [Auto Update] Έναρξη αυτόματης έξυπνης ενημέρωσης κληρώσεων...")
      for g in ["joker", "lotto"]:
        try:
          perform_smart_update(g)
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
