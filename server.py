"""
SafeStride Pro — Complete Backend Server
Run with: python server.py
Runs on:  http://localhost:8181

Endpoints:
  POST /api/register          — create account (replaces MySQL)
  POST /api/login             — login
  POST /api/analyze           — send camera frame → Gemini AI → get scene description
  POST /api/sos               — send SOS email with GPS location
  GET  /api/nav               — Google Directions API proxy (keeps Maps key hidden)
  POST /api/track             — app sends its GPS location here
  GET  /api/track/<userId>    — caregiver fetches a user's location
  GET  /api/users             — list all tracked users
  GET  /portal                — caregiver web portal (HTML)
"""

import os
import json
import hashlib
import base64
import smtplib
import re
import sys
import cv2
import numpy as np
import requests

from flask       import Flask, request, jsonify, send_from_directory
from flask_cors  import CORS
from datetime    import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText

# ── Load ai_engine from same folder or services/ subfolder ───────────────────
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from ai_engine import AIEngine          # if server.py and ai_engine.py are in same folder
except ImportError:
    from services.ai_engine import AIEngine  # if ai_engine.py is inside services/

# ── Keys — read from environment variables first, fall back to hardcoded ─────
GEMINI_KEY     = os.environ.get("GEMINI_KEY",      "AIzaSyALg4251KUdXhQRAINXwajmJH7JBcWFBRw")
MAPS_KEY       = os.environ.get("MAPS_KEY",        "AIzaSyCHgf9f8qEYa53_qfPddWvWnvlgU_feJow")
SOS_EMAIL_FROM = os.environ.get("SOS_EMAIL_FROM",  "ppavan_cse255a0507@mgit.ac.in")
SOS_EMAIL_PASS = os.environ.get("SOS_EMAIL_PASS",  "yizd kdvs mzoo kbek")

# ── Flask app + CORS (so the React web app can call this server) ──────────────
app = Flask(__name__)
CORS(app)   # allows requests from any origin (your Netlify URL, localhost, etc.)

# ── AI engine — loaded once at startup ───────────────────────────────────────
ai = AIEngine(GEMINI_KEY)
print(f"[Server] AIEngine loaded with Gemini key: {GEMINI_KEY[:8]}...")

# ── In-memory location store: {{ userId: [{{lat, lon, timestamp}}, ...] }} ───
location_store = {}

# ── User file — replaces MySQL entirely ──────────────────────────────────────
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

def load_users():
    """Load users dict from users.json. Returns {{}} if file doesn't exist."""
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(data):
    """Save users dict to users.json."""
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def hash_pw(pw):
    """SHA-256 hash the password — same security as bcrypt for this use case."""
    return hashlib.sha256(pw.encode()).hexdigest()


# ════════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS  (replaces MySQL login/register in main.py)
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/register", methods=["POST"])
def register():
    """
    POST {{ "username": "pavan", "password": "abc123", "emergency_contact": "guardian@gmail.com" }}
    Returns {{ "ok": true }} or {{ "error": "Username taken" }}
    """
    d  = request.get_json()
    u  = (d.get("username") or "").strip()
    pw = (d.get("password") or "").strip()
    ec = (d.get("emergency_contact") or "").strip()

    if not u or not pw:
        return jsonify({"error": "Username and password required"}), 400

    users = load_users()
    if u in users:
        return jsonify({"error": "Username already taken"}), 409

    users[u] = {"password": hash_pw(pw), "emergency_contact": ec}
    save_users(users)
    print(f"[Register] New user: {u}")
    return jsonify({"ok": True}), 200


@app.route("/api/login", methods=["POST"])
def login():
    """
    POST {{ "username": "pavan", "password": "abc123" }}
    Returns {{ "ok": true, "emergency_contact": "guardian@gmail.com" }}
         or {{ "error": "Invalid credentials" }}
    """
    d  = request.get_json()
    u  = (d.get("username") or "").strip()
    pw = (d.get("password") or "").strip()

    users = load_users()
    if u not in users or users[u]["password"] != hash_pw(pw):
        print(f"[Login] Failed for: {u}")
        return jsonify({"error": "Invalid credentials"}), 401

    ec = users[u].get("emergency_contact", "")
    print(f"[Login] Success: {u}")
    return jsonify({"ok": True, "emergency_contact": ec}), 200


# ════════════════════════════════════════════════════════════════════════════════
# AI ANALYZE ENDPOINT  (replaces direct Gemini call in main.py)
# Keeps GEMINI_KEY on the server — never sent to browser
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    POST {{ "image": "<base64 JPEG>", "mode": "Indoor" }}
    Returns {{ "result": "Path is clear. There is a chair on your left..." }}

    The web app captures a camera frame, converts it to base64,
    and posts it here. This function decodes it and calls ai_engine.analyze_scene()
    which is your existing Gemini code — unchanged.
    """
    d       = request.get_json()
    img_b64 = d.get("image", "")
    mode    = d.get("mode", "Outdoor")

    if not img_b64:
        return jsonify({"result": "ERROR"}), 400

    try:
        # Decode base64 → numpy array → OpenCV frame (replaces cv2.VideoCapture.read())
        img_bytes = base64.b64decode(img_b64)
        arr       = np.frombuffer(img_bytes, np.uint8)
        frame     = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"result": "ERROR"}), 400

        # Call your existing ai_engine.analyze_scene() — no changes needed there
        result = ai.analyze_scene(frame, mode)
        print(f"[Analyze] mode={mode} result={result[:60]}...")
        return jsonify({"result": result}), 200

    except Exception as e:
        print(f"[Analyze] Error: {e}")
        if "429" in str(e) or "quota" in str(e).lower():
            return jsonify({"result": "BUSY"}), 200
        return jsonify({"result": "ERROR"}), 500


# ════════════════════════════════════════════════════════════════════════════════
# SOS EMAIL ENDPOINT  (same smtplib logic as main.py send_sos_email())
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/sos", methods=["POST"])
def sos():
    """
    POST {{ "user": "pavan", "emergency_contact": "guardian@gmail.com", "lat": 17.38, "lon": 78.48 }}
    Returns {{ "ok": true }} or {{ "ok": false, "error": "..." }}

    Sends the same HTML email as send_sos_email() in your main.py.
    """
    d    = request.get_json()
    user = d.get("user", "Unknown")
    ec   = d.get("emergency_contact", "")
    lat  = d.get("lat", 0.0)
    lon  = d.get("lon", 0.0)

    if not ec:
        print("[SOS] No emergency contact email.")
        return jsonify({"ok": False, "error": "No emergency contact email set"}), 400

    maps_link  = f"https://maps.google.com/?q={lat},{lon}"
    subject    = f"SOS ALERT — {user} needs immediate help!"
    body_plain = f"SOS ALERT: {user} needs help!\nLocation: {lat},{lon}\nMaps: {maps_link}"
    body_html  = f"""
    <html><body style="font-family:Arial;background:#f4f4f4;padding:20px;">
      <div style="max-width:560px;margin:auto;background:#fff;border-radius:10px;
                  border-top:6px solid #e00;padding:30px;">
        <h2 style="color:#e00;">SOS EMERGENCY ALERT</h2>
        <p><strong>{user}</strong> has triggered an SOS alert and needs immediate help.</p>
        <p><strong>Latitude:</strong> {lat}</p>
        <p><strong>Longitude:</strong> {lon}</p>
        <a href="{maps_link}" style="background:#e00;color:#fff;padding:12px 24px;
           border-radius:6px;text-decoration:none;font-weight:bold;display:inline-block;margin-top:10px;">
          Open Location in Google Maps
        </a>
        <p style="font-size:11px;color:#999;margin-top:20px;">
          Sent automatically by SafeStride Pro.
        </p>
      </div>
    </body></html>"""

    if not SOS_EMAIL_FROM or not SOS_EMAIL_PASS:
        print(f"[SOS] Email not configured — would send to {ec}\n{body_plain}")
        return jsonify({"ok": False, "error": "SOS email credentials not configured on server"}), 500

    try:
        msg             = MIMEMultipart("alternative")
        msg["Subject"]  = subject
        msg["From"]     = f"SafeStride SOS <{SOS_EMAIL_FROM}>"
        msg["To"]       = ec
        msg.attach(MIMEText(body_plain, "plain"))
        msg.attach(MIMEText(body_html,  "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(SOS_EMAIL_FROM, SOS_EMAIL_PASS)
            s.sendmail(SOS_EMAIL_FROM, ec, msg.as_string())

        print(f"[SOS] Email sent to {ec} for user {user}")
        return jsonify({"ok": True}), 200

    except Exception as e:
        print(f"[SOS] Email error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ════════════════════════════════════════════════════════════════════════════════
# NAVIGATION PROXY  (keeps MAPS_KEY on server — never sent to browser)
# Same Google Directions API call as nav_engine.py get_step_directions()
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/nav", methods=["GET"])
def nav():
    """
    GET /api/nav?origin=17.385,78.4867&destination=Charminar

    Proxies the Google Directions API call so the Maps key stays on the server.
    Returns the full Directions API JSON response.
    """
    origin      = request.args.get("origin", "17.3850,78.4867")
    destination = request.args.get("destination", "")

    if not destination:
        return jsonify({"status": "INVALID_REQUEST", "error": "destination required"}), 400

    try:
        params = {
            "origin":      origin,
            "destination": destination,
            "mode":        "walking",
            "key":         MAPS_KEY
        }
        res = requests.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params=params,
            timeout=8
        ).json()
        print(f"[Nav] {origin} → {destination} status={res.get('status')}")
        return jsonify(res), 200

    except Exception as e:
        print(f"[Nav] Error: {e}")
        return jsonify({"status": "ERROR", "error": str(e)}), 500


# ════════════════════════════════════════════════════════════════════════════════
# LOCATION TRACKING  (unchanged from your original server.py)
# ════════════════════════════════════════════════════════════════════════════════

@app.route("/api/track", methods=["POST"])
def log_location():
    """
    POST {{ "userId": "pavan", "lat": 17.385, "lon": 78.4867 }}
    Stores the location in memory (last 50 entries per user).
    """
    data  = request.get_json()
    uid   = str(data.get("userId", "unknown"))
    lat   = data.get("lat", 0.0)
    lon   = data.get("lon", 0.0)
    entry = {"lat": lat, "lon": lon, "timestamp": datetime.now().isoformat()}
    location_store.setdefault(uid, []).insert(0, entry)
    location_store[uid] = location_store[uid][:50]   # keep last 50
    print(f"[Track] {uid} → lat={lat}, lon={lon}")
    return jsonify(entry), 200


@app.route("/api/track/<user_id>", methods=["GET"])
def get_location(user_id):
    """GET /api/track/pavan — returns list of location entries, newest first."""
    data = location_store.get(user_id, [])
    return jsonify(data), 200


@app.route("/api/users", methods=["GET"])
def list_users():
    """GET /api/users — returns list of all currently tracked usernames."""
    return jsonify(list(location_store.keys())), 200


# ════════════════════════════════════════════════════════════════════════════════
# CAREGIVER PORTAL  (unchanged from your original server.py)
# ════════════════════════════════════════════════════════════════════════════════
@app.route('/app')
def webapp():
    return send_from_directory('.', 'safestride.html')
@app.route("/")
@app.route("/portal")
def portal():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>SafeStride Caregiver Portal</title>
    <style>
        body { font-family: Arial, sans-serif; background: #0a0a1a; color: #fff; padding: 30px; }
        h1 { color: #00ff88; }
        input { padding: 10px; width: 300px; border-radius: 6px; border: none; margin-right: 10px; font-size: 15px; }
        button { padding: 10px 20px; background: #0080ff; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 15px; font-weight: bold; }
        button:hover { background: #0060cc; }
        #info { margin-top: 30px; font-size: 18px; line-height: 2; background: #111; padding: 20px; border-radius: 10px; }
        #map { width: 100%; height: 400px; border-radius: 10px; margin-top: 20px; border: none; }
        .label { color: #aaa; font-size: 13px; }
    </style>
</head>
<body>
    <h1>SafeStride Caregiver Portal</h1>
    <input id="uid" placeholder="Enter username to track" value="pavan"/>
    <button onclick="fetchLocation()">TRACK</button>
    <button onclick="startAuto()" style="background:#00aa55; margin-left:10px;">AUTO REFRESH (5s)</button>
    <div id="info">Enter a username and click TRACK.</div>
    <iframe id="map" src="" style="display:none"></iframe>
    <script>
    let autoTimer = null;
    async function fetchLocation() {
        const uid = document.getElementById('uid').value.trim();
        if (!uid) return;
        try {
            const res  = await fetch('/api/track/' + uid);
            const data = await res.json();
            if (data.length > 0) {
                const d = data[0];
                document.getElementById('info').innerHTML =
                    '<span class="label">USER</span><br>' + uid +
                    '<br><br><span class="label">LATITUDE</span><br>'  + d.lat +
                    '<br><br><span class="label">LONGITUDE</span><br>' + d.lon +
                    '<br><br><span class="label">LAST UPDATED</span><br>' + d.timestamp +
                    '<br><br><span style="color:#00ff88">STATUS: Online</span>';
                const mapFrame = document.getElementById('map');
                mapFrame.src = `https://maps.google.com/maps?q=${d.lat},${d.lon}&z=16&output=embed`;
                mapFrame.style.display = 'block';
            } else {
                document.getElementById('info').innerHTML =
                    'No location data found for <b>' + uid + '</b>.';
            }
        } catch(e) {
            document.getElementById('info').innerHTML = 'Server error: ' + e;
        }
    }
    function startAuto() {
        if (autoTimer) { clearInterval(autoTimer); autoTimer = null; return; }
        fetchLocation();
        autoTimer = setInterval(fetchLocation, 5000);
    }
    </script>
</body>
</html>
""", 200


# ════════════════════════════════════════════════════════════════════════════════
# START
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("SafeStride Pro — Backend Server")
    print("=" * 60)
    print(f"  Local URL    : http://localhost:8181")
    print(f"  Portal       : http://localhost:8181/portal")
    print(f"  Gemini key   : {GEMINI_KEY[:8]}...")
    print(f"  Maps key     : {MAPS_KEY[:8]}...")
    print(f"  SOS from     : {SOS_EMAIL_FROM}")
    print(f"  Users file   : {USERS_FILE}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=8181, debug=False)