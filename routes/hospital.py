from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
import random
import requests 
from datetime import datetime

hospital_bp = Blueprint('hospital_bp', __name__, url_prefix='/hospital')

# Helper function: Address to coordinates
def get_coordinates(address):
    from app import GOOGLE_MAPS_API_KEY
    if not address:
        return None
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_MAPS_API_KEY}"
    try:
        response = requests.get(url).json()
        if response['status'] == 'OK':
            loc = response['results'][0]['geometry']['location']
            return [float(loc['lng']), float(loc['lat'])] 
    except Exception as e:
        print(f"Geocoding Error: {e}")
    return None

@hospital_bp.route('/home')
def hospital_home():
    from app import db  
    if session.get('user_type') != 'hospital': 
        return redirect(url_for('auth_bp.login')) 
    
    hospital_data = db.users.find_one({"user_id": session.get('user_id')}) 
    if not hospital_data: 
        return redirect(url_for('auth_bp.login')) 

    return render_template('hospital_home.html', hospital=hospital_data) 

# --- SOS Alerts Logic ---
@hospital_bp.route('/check_emergencies')
def check_emergencies():
    from app import db
    if session.get('user_type') != 'hospital':
        return jsonify({"alerts": []})

    current_hospital = db.users.find_one({"user_id": session.get('user_id')})
    if not current_hospital or 'location' not in current_hospital or not current_hospital['location']:
        return jsonify({"alerts": []})

    h_coords = current_hospital['location']['coordinates'] 

    try:
        active_alerts = list(db.emergency_requests.find({
            "location": {
                "$nearSphere": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": h_coords
                    },
                    "$maxDistance": 50000 # 50 KM (as per your code)
                }
            },
            "status": "active" 
        }))
    except Exception as e:
        print(f"SOS Search Error: {e}")
        active_alerts = []

    formatted_alerts = []
    for alert in active_alerts:
        formatted_alerts.append({
            "user_id": alert.get("patient_id"),
            "patient_name": alert.get("patient_name"),
            "phone": alert.get("phone"),
            "description": alert.get("description"),
            "location": alert.get("location"),
            "sos_id": alert.get("sos_id") # Match with SOS-XXXXX format
        })

    return jsonify({"alerts": formatted_alerts})

# --- UPDATED: ACCEPT SOS (Pushes data to the correct collection) ---
@hospital_bp.route('/accept_sos', methods=['POST'])
def accept_sos():
    from app import db
    if session.get('user_type') != 'hospital':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.json
    sos_id = data.get('sos_id')
    specialist = data.get('specialist_name', 'General Doctor')
    beds = data.get('free_beds', 'Unknown')

    # Hospital details for response
    hospital_id = session.get('user_id')
    hospital_data = db.users.find_one({"user_id": hospital_id})

    if not hospital_data:
        return jsonify({"status": "error", "message": "Hospital data not found"}), 404

    new_response = {
        "hospital_id": hospital_id,
        "hospital_name": hospital_data.get('hospital_name'),
        "specialist_name": specialist,
        "free_beds": beds,
        "phone": hospital_data.get('phone'),
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }

    # 1. Update the MAIN emergency_requests document (So patient sees it in polling)
    # Hum 'responses' array mein ye naya hospital data push kar rahe hain
    db.emergency_requests.update_one(
        {"sos_id": sos_id},
        {"$push": {"responses": new_response}}
    )

    # 2. Backup log in sos_responses (Optional, as per your previous logic)
    db.sos_responses.insert_one({
        "sos_id": sos_id,
        **new_response,
        "full_timestamp": datetime.now()
    })

    return jsonify({"status": "success", "message": "Response sent to patient!"})

# --- LIVE ALL-INDIA SEARCH API ---
@hospital_bp.route('/get_google_suggestions')
def get_google_suggestions():
    from app import GOOGLE_MAPS_API_KEY
    query = request.args.get('q', '')
    if len(query) < 3:
        return jsonify([])

    url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={query}&types=establishment&location=20.5937,78.9629&radius=2000000&key={GOOGLE_MAPS_API_KEY}"
    
    try:
        response = requests.get(url).json()
        suggestions = []
        if response['status'] == 'OK':
            for place in response['predictions']:
                if 'hospital' in place['types'] or 'health' in place['types'] or 'medical' in place['description'].lower():
                    suggestions.append({
                        "description": place['description'],
                        "place_id": place['place_id']
                    })
        return jsonify(suggestions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Profile update ---
@hospital_bp.route('/update_profile', methods=['POST'])
def update_profile():
    from app import db  
    if session.get('user_type') != 'hospital': 
        return redirect(url_for('auth_bp.login')) 
    
    user_id = session.get('user_id') 
    address = request.form.get('address')
    form_lat = request.form.get('lat')
    form_lng = request.form.get('lng')

    updated_fields = {
        "hospital_name": request.form.get('hospital_name'), 
        "phone": request.form.get('phone'), 
        "address": address,
        "beds_available": request.form.get('beds_available'),
        "type": "physical"
    }

    if form_lat and form_lng:
        updated_fields["location"] = {
            "type": "Point", 
            "coordinates": [float(form_lng), float(form_lat)]
        }
    else:
        coords = get_coordinates(address)
        if coords:
            updated_fields["location"] = {"type": "Point", "coordinates": coords}
    
    db.users.update_one({"user_id": user_id}, {"$set": updated_fields}) 
    db.hospitals.update_one(
        {"user_id": user_id}, 
        {"$set": {
            "hospital_name": updated_fields["hospital_name"],
            "address": updated_fields["address"],
            "location": updated_fields.get("location"),
            "type": "physical",
            "phone": updated_fields["phone"]
        }},
        upsert=True 
    )

    session['name'] = updated_fields['hospital_name'] 
    flash("Profile Updated Successfully!", "success") 
    return redirect(url_for('hospital_bp.hospital_home')) 

# --- OTP ROUTES ---
@hospital_bp.route('/request_update_otp', methods=['POST'])
def request_update_otp():
    from app import mail
    from flask_mail import Message
    
    data = request.json 
    otp = str(random.randint(1000, 9999))
    session['update_otp'] = otp 
    session['temp_update_data'] = data 
    
    try:
        msg = Message("Hospital Profile Update Verification", 
                      sender="anujmore726@gmail.com", 
                      recipients=[data['email']])
        msg.body = f"Verify your hospital profile update with this code: {otp}"
        mail.send(msg)
        return jsonify({"status": "sent"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@hospital_bp.route('/verify_update', methods=['POST'])
def verify_update():
    from app import db
    user_otp = request.json.get('otp')
    
    if str(user_otp) == str(session.get('update_otp')):
        data = session.get('temp_update_data')
        f_lat = data.get('lat')
        f_lng = data.get('lng')

        update_payload = {
            "hospital_name": data['hospital_name'],
            "email": data['email'],
            "phone": data['phone'],
            "address": data.get('address'),
            "beds_available": data['beds_available'],
            "type": "physical"
        }

        if f_lat and f_lng:
            update_payload["location"] = {
                "type": "Point", 
                "coordinates": [float(f_lng), float(f_lat)]
            }
        else:
            coords = get_coordinates(data.get('address'))
            if coords:
                update_payload["location"] = {"type": "Point", "coordinates": coords}
        
        db.users.update_one({"user_id": session.get('user_id')}, {"$set": update_payload})
        db.hospitals.update_one(
            {"user_id": session.get('user_id')},
            {"$set": {
                "hospital_name": update_payload["hospital_name"],
                "address": update_payload.get("address"),
                "location": update_payload.get("location"),
                "type": "physical"
            }},
            upsert=True
        )

        session.pop('update_otp', None)
        session.pop('temp_update_data', None)
        return jsonify({"status": "success"}), 200
    
    return jsonify({"status": "error", "message": "Invalid OTP"}), 400