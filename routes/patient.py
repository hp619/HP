from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
import random
import requests 

patient_bp = Blueprint('patient_bp', __name__, url_prefix='/patient')

@patient_bp.route('/home')
def patient_home():
    from app import db
    if session.get('user_type') != 'patient':
        return redirect(url_for('auth_bp.login'))
    
    patient_data = db.users.find_one({"user_id": session.get('user_id')})
    if not patient_data:
        return redirect(url_for('auth_bp.login'))

    return render_template('patient_home.html', user=patient_data)

@patient_bp.route('/update_profile', methods=['POST'])
def update_profile():
    from app import db
    if session.get('user_type') != 'patient':
        return redirect(url_for('auth_bp.login'))
    
    user_id = session.get('user_id')
    updated_fields = {
        "patient_name": request.form.get('name'),
        "phone": request.form.get('phone'),
        "gender": request.form.get('gender')
    }
    
    db.users.update_one({"user_id": user_id}, {"$set": updated_fields})
    session['name'] = updated_fields['patient_name']
    flash("Profile Updated Successfully!", "success")
    return redirect(url_for('patient_bp.patient_home'))

# --- OTP ROUTES (SECURE UPDATE) ---

@patient_bp.route('/request_update_otp', methods=['POST'])
def request_update_otp():
    from app import mail, db
    from flask_mail import Message
    
    try:
        data = request.json 
        otp = str(random.randint(1000, 9999))
        session['update_otp'] = otp 
        session['temp_update_data'] = data 
        
        msg = Message("Patient Profile Update OTP", 
                      sender="anujmore726@gmail.com", 
                      recipients=[data['email']])
        
        msg.body = f"Aapka profile update verification code hai: {otp}"
        mail.send(msg)
        
        print(f"DEBUG: OTP {otp} sent to {data['email']}") 
        return jsonify({"status": "sent"}), 200
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@patient_bp.route('/verify_update', methods=['POST'])
def verify_update():
    from app import db
    try:
        user_otp = request.json.get('otp')
        
        if str(user_otp) == str(session.get('update_otp')):
            data = session.get('temp_update_data')
            
            db.users.update_one(
                {"user_id": session.get('user_id')},
                {"$set": {
                    "patient_name": data['name'],
                    "email": data['email'],
                    "phone": data['phone'],
                    "gender": data['gender']
                }}
            )
            
            session['name'] = data['name']
            session.pop('update_otp', None)
            session.pop('temp_update_data', None)
            
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "error", "message": "Invalid OTP"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- SMART SEARCH LOGIC ---

@patient_bp.route('/search_hospitals', methods=['GET'])
def search_hospitals():
    from app import db, GOOGLE_MAPS_API_KEY
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    db_results = list(db.hospitals.find({
        "hospital_name": {"$regex": query, "$options": "i"}
    }).limit(5))

    results = []
    for h in db_results:
        results.append({
            "name": h.get('hospital_name'),
            "address": h.get('address', 'Registered in System'),
            "type": "Registered",
            "is_live": False
        })

    try:
        google_url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={query}&types=establishment&location=20.5937,78.9629&radius=2000000&key={GOOGLE_MAPS_API_KEY}"
        response = requests.get(google_url).json()
        
        if response['status'] == 'OK':
            for place in response['predictions']:
                description = place['description'].lower()
                if any(word in description for word in ['hospital', 'health', 'medical', 'clinic']):
                    results.append({
                        "name": place['structured_formatting']['main_text'],
                        "address": place['structured_formatting']['secondary_text'],
                        "type": "Live (India)",
                        "is_live": True,
                        "place_id": place['place_id']
                    })
    except Exception as e:
        print(f"Google Search Error: {e}")

    return jsonify(results)

# --- NEW: POLLING ROUTE FOR PATIENT (Hospitals ki list dekhne ke liye) ---

@patient_bp.route('/get_sos_responses', methods=['GET'])
def get_live_responses():
    from app import db
    patient_id = session.get('user_id')
    
    # Patient ki sabse latest active request uthao
    latest_request = db.emergency_requests.find_one(
        {"patient_id": patient_id, "status": "active"},
        sort=[("_id", -1)]
    )
    
    if not latest_request:
        return jsonify({"status": "no_active_request", "hospitals": []})
    
    return jsonify({
        "status": "success",
        "sos_id": latest_request['sos_id'],
        "hospitals": latest_request.get('responses', []) # Hospital list yahan se jayegi
    })

# --- NEW: FINAL SELECTION BY PATIENT ---

@patient_bp.route('/final_selection', methods=['POST'])
def final_selection():
    from app import db
    data = request.json
    sos_id = data.get('sos_id')
    hospital_id = data.get('hospital_id')
    
    # Status update karo taaki baki hospitals ko pata chale selection ho gaya
    db.emergency_requests.update_one(
        {"sos_id": sos_id},
        {"$set": {
            "status": "patient_confirmed",
            "selected_hospital_id": hospital_id
        }}
    )
    return jsonify({"status": "success", "message": "Hospital Selected! Specialist Assigning..."})


# --- EMERGENCY BROADCAST (UPDATED FOR TWO-WAY) ---

@patient_bp.route('/broadcast_emergency', methods=['POST'])
def broadcast_emergency():
    from app import db
    try:
        data = request.json
        p_lat = float(data.get('lat'))
        p_lng = float(data.get('lng'))
        description = data.get('description', 'Medical Emergency!')

        sos_id = f"SOS-{random.randint(10000, 99999)}"
        sos_entry = {
            "sos_id": sos_id,
            "patient_id": session.get('user_id'),
            "patient_name": session.get('name'),
            "phone": session.get('phone', 'N/A'),
            "description": description,
            "location": { "type": "Point", "coordinates": [p_lng, p_lat] },
            "status": "active",
            "responses": [],  # <--- NAYA: Hospitals yahan jama honge
            "timestamp": random.randint(100000, 999999) 
        }
        db.emergency_requests.insert_one(sos_entry)

        nearby_hospitals = list(db.hospitals.find({
            "location": {
                "$nearSphere": {
                    "$geometry": { "type": "Point", "coordinates": [p_lng, p_lat] },
                    "$maxDistance": 50000 
                }
            }
        }))

        count = len(nearby_hospitals)
        print(f"🚨 SOS BROADCAST: From [{p_lat}, {p_lng}] - Found {count} hospitals.")
        
        return jsonify({"status": "success", "found": count, "sos_id": sos_id}), 200

    except Exception as e:
        print(f"SOS Error Details: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500