import os  # <--- Naya add kiya environment variables ke liye
from flask import Flask, redirect, url_for
from flask_mail import Mail
from pymongo import MongoClient, GEOSPHERE
import webbrowser 
from threading import Timer 

app = Flask(__name__, template_folder='templates')
# Railway par SECRET_KEY variable set kar dena, nahi toh ye use hoga
app.secret_key = os.getenv("SECRET_KEY", "emergency_secret_key")

# --- 🗺️ GOOGLE MAPS API CONFIG ---
# Railway ke dashboard mein GOOGLE_MAPS_API_KEY add karna mat bhulna
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyCsPEckg1hZpu9_cV4QJ8mKg3ByvMDmYOM") 
app.config['GOOGLE_MAPS_API_KEY'] = GOOGLE_MAPS_API_KEY

# --- ☁️ MONGODB CONFIGURATION ---
# Railway ke variables mein MONGO_URI set karna hoga
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://mavlabot:mavlabot@mavlabotcluster0.uoqbuck.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client['hospital_system']

# --- 📍 AUTO-INDEXING ---
collections_to_index = ['users', 'hospitals', 'usersTree', 'emergency_requests']

for coll in collections_to_index:
    try:
        db[coll].create_index([("location", "2dsphere")])
        print(f"✅ MongoDB: Geo-Index (2dsphere) for '{coll}' is Active!")
    except Exception as e:
        print(f"⚠️ Index Check ({coll}): {e}")

# --- 📧 EMAIL CONFIG ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME", 'anujmore726@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD", 'pllr axia ofnl xdsi')
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
    # Production (Railway) par browser open karne ki zaroorat nahi hoti
    if not os.getenv("RAILWAY_STATIC_URL"): 
        webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == '__main__':
    print("Server starting...")
    
    # Railway environment variable se PORT uthayega, nahi toh local 5000 use karega
    port = int(os.environ.get("PORT", 5000))
    
    # Local machine par ho toh hi browser khulega
    if not os.getenv("RAILWAY_STATIC_URL"):
        Timer(1.5, open_browser).start()
        app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
    else:
        # Railway ke liye direct run
        app.run(host='0.0.0.0', port=port)