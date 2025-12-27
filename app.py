import os  # Environment variables ke liye
from flask import Flask, redirect, url_for, session # <--- session add kiya
from flask_mail import Mail
from pymongo import MongoClient, GEOSPHERE
import webbrowser 
from threading import Timer 
from datetime import timedelta # <--- Naya add kiya session timing ke liye

app = Flask(__name__, template_folder='templates')

# --- 🔑 SESSION CONFIG (Fix for Logout on Refresh) ---
app.secret_key = os.getenv("SECRET_KEY", "emergency_secret_key")
app.permanent_session_lifetime = timedelta(days=7) # Session 7 din tak valid rahega

@app.before_request
def make_session_permanent():
    session.permanent = True # Har request par session ko refresh/permanent rakhega

# --- 🗺️ GOOGLE MAPS API CONFIG ---
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyCsPEckg1hZpu9_cV4QJ8mKg3ByvMDmYOM") 
app.config['GOOGLE_MAPS_API_KEY'] = GOOGLE_MAPS_API_KEY

# --- ☁️ MONGODB CONFIGURATION ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://mavlabot:mavlabot@mavlabotcluster0.uoqbuck.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client['hospital_system']

# --- 📍 AUTO-INDEXING & UNIQUE KEYS ---
# 1. Geo-Spatial Indexing (Location ke liye)
collections_to_index = ['users', 'hospitals', 'usersTree', 'emergency_requests']
for coll in collections_to_index:
    try:
        db[coll].create_index([("location", "2dsphere")])
        print(f"✅ MongoDB: Geo-Index (2dsphere) for '{coll}' is Active!")
    except Exception as e:
        print(f"⚠️ Index Check ({coll}): {e}")

# 2. Aadhar Card Unique Index (Taki ek Aadhar se duplicate register na ho)
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
    
    # Local machine par ho toh hi browser khulega
    if not os.getenv("RAILWAY_STATIC_URL") and not os.getenv("KOYEB_APP_NAME"):
        Timer(1.5, open_browser).start()
        app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
    else:
        app.run(host='0.0.0.0', port=port)
