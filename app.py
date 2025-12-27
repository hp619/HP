import os  # Environment variables ke liye
from flask import Flask, redirect, url_for, session, jsonify, request # <--- jsonify/request add kiya search ke liye
from flask_mail import Mail
from pymongo import MongoClient, GEOSPHERE
import webbrowser 
from threading import Timer 
from datetime import timedelta 
from bson.objectid import ObjectId # <--- Database IDs ke liye

app = Flask(__name__, template_folder='templates')

# --- 🔑 SESSION CONFIG (Fix for Logout on Refresh) ---
app.secret_key = os.getenv("SECRET_KEY", "emergency_secret_key")
app.permanent_session_lifetime = timedelta(days=7) 

@app.before_request
def make_session_permanent():
    session.permanent = True 

# --- 🗺️ GOOGLE MAPS API CONFIG ---
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyCsPEckg1hZpu9_cV4QJ8mKg3ByvMDmYOM") 
app.config['GOOGLE_MAPS_API_KEY'] = GOOGLE_MAPS_API_KEY

# --- ☁️ MONGODB CONFIGURATION ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://hospitalemergancy:hospitalemergancy@cluster0.wqgziaf.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI)

# 1. Purana Database (Registration ke liye)
db = client['hospital_system']

# 2. Naya Database (2 Lakh Hospitals ke liye) - NEW ADDED
db_external = client['healthcare_db']
external_collection = db_external['external_hospitals']

# --- 📍 AUTO-INDEXING & UNIQUE KEYS ---
collections_to_index = ['users', 'hospitals', 'usersTree', 'emergency_requests']
for coll in collections_to_index:
    try:
        db[coll].create_index([("location", "2dsphere")])
        print(f"✅ MongoDB: Geo-Index for '{coll}' is Active!")
    except Exception as e:
        print(f"⚠️ Index Check ({coll}): {e}")

# Aadhar Card Unique Index
try:
    db.users.create_index("aadhar_card", unique=True)
    print("✅ MongoDB: Aadhar Card is now a Unique Primary Key!")
except Exception as e:
    print(f"⚠️ Aadhar Index Error: {e}")

# --- 📧 EMAIL CONFIG ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME", 'hospitalofficiall@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD", 'wzei dibe mcte ywhi')
mail = Mail(app)

# --- 🔍 GLOBAL SEARCH ENDPOINT (2 Lakh + Registered) ---
@app.route('/patient/search_hospitals')
def search_hospitals():
    query = request.args.get('q', '')
    lat = request.args.get('lat')
    lng = request.args.get('lng')

    results = []

    # A. Pehle Registered Hospitals search karo
    reg_hospitals = db.hospitals.find({
        "hospital_name": {"$regex": query, "$options": "i"}
    }).limit(5)

    for h in reg_hospitals:
        results.append({
            "id": str(h['_id']),
            "name": h['hospital_name'],
            "address": h.get('address', 'Partner Hospital'),
            "is_registered": True
        })

    # B. Phir 2 Lakh CSV hospitals search karo (Distance based)
    geo_query = {"hospital_name": {"$regex": query, "$options": "i"}}
    if lat and lng:
        geo_query["location"] = {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
                "$maxDistance": 15000 # 15 KM radius
            }
        }

    ext_hospitals = db_external.external_hospitals.find(geo_query).limit(10)

    for h in ext_hospitals:
        results.append({
            "id": str(h['_id']),
            "name": h['hospital_name'],
            "address": h.get('address', 'Govt/Public Facility'),
            "is_registered": False
        })

    return jsonify(results)

# --- 🔄 AUTO REDIRECT LOGIC ---
@app.route('/')
def home():
    return redirect(url_for('auth_bp.login'))

# --- 🚀 BLUEPRINTS ---
from routes.auth import auth_bp
from routes.patient import patient_bp
from routes.hospital import hospital_bp

app.register_blueprint(auth_bp)
app.register_blueprint(patient_bp)
app.register_blueprint(hospital_bp)

# --- 🌐 BROWSER AUTO-OPEN FUNCTION ---
def open_browser():
    if not os.getenv("RAILWAY_STATIC_URL") and not os.getenv("KOYEB_APP_NAME"): 
        webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == '__main__':
    print("Server starting...")
    port = int(os.environ.get("PORT", 5000))
    
    if not os.getenv("RAILWAY_STATIC_URL") and not os.getenv("KOYEB_APP_NAME"):
        Timer(1.5, open_browser).start()
        app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
    else:
        app.run(host='0.0.0.0', port=port)
