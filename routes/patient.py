from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
import random
import requests 

patient_bp = Blueprint('patient_bp', __name__, url_prefix='/patient')

# Helper function to check session (Isse login redirect issue solve hoga)
def is_logged_in():
    return session.get('user_type') == 'patient' and session.get('user_id')

# --- 1. PATIENT HOME ---
@patient_bp.route('/home')
def patient_home():
    from app import db
    if not is_logged_in():
        return redirect(url_for('auth_bp.login'))
    
    patient_data = db.users.find_one({"user_id": session.get('user_id')})
    if not patient_data:
        return redirect(url_for('auth_bp.login'))

    return render_template('patient_home.html', user=patient_data)

# --- 2. UPDATE PROFILE ---
@patient_bp.route('/update_profile', methods=['POST'])
def update_profile():
    from app import db
    if not is_logged_in():
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

# --- 3. OTP ROUTES ---
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
        return jsonify({"status": "sent"}), 200
    except Exception as e:
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

# --- 4. SMART SEARCH LOGIC ---
@patient_bp.route('/search_hospitals', methods=['GET'])
def search_hospitals():
    from app import db, db_external, GOOGLE_MAPS_API_KEY
    query = request.args.get('q', '').strip()
    u_lat = request.args.get('lat')
    u_lng = request.args.get('lng')

    if len(query) < 2:
        return jsonify([])

    results = []

    # A. Registered Hospitals
    db_results = list(db.hospitals.find({"hospital_name": {"$regex": query, "$options": "i"}}).limit(5))
    for h in db_results:
        results.append({
            "name": h.get('hospital_name'),
            "address": h.get('address') or h.get('location_address') or 'Registered Partner',
            "type": "Certified",
            "is_registered": True,
            "id": h.get('user_id') 
        })

    # B. External Hospitals (2 Lakh CSV) - Address fix added here
    geo_query = {"hospital_name": {"$regex": query, "$options": "i"}}
    if u_lat and u_lng:
        geo_query["location"] = {"$near": {"$geometry": {"type": "Point", "coordinates": [float(u_lng), float(u_lat)]}, "$maxDistance": 10000}}

    csv_results = list(db_external.external_hospitals.find(geo_query).limit(10))
    for c in csv_results:
        coords = c.get('location', {}).get('coordinates', [0, 0])
        # Yaha address ko concatenate kiya taaki empty na dikhe
        full_addr = f"{c.get('district', '')}, {c.get('state', '')}".strip(", ")
        results.append({
            "name": c.get('hospital_name'),
            "address": full_addr if full_addr else "Address Details N/A",
            "type": "Govt/Public",
            "is_registered": False,
            "lat": coords[1],
            "lng": coords[0]
        })

    # C. Google Maps Search
    try:
        google_url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?input={query}&types=establishment&location=20.5937,78.9629&radius=2000000&key={GOOGLE_MAPS_API_KEY}"
        response = requests.get(google_url).json()
        if response['status'] == 'OK':
            for place in response['predictions']:
                results.append({
                    "name": place['structured_formatting']['main_text'],
                    "address": place['structured_formatting']['secondary_text'],
                    "type": "Live (India)",
                    "is_registered": False,
                    "google_search": True,
                    "place_id": place['place_id']
                })
    except: pass
    return jsonify(results)

# --- 5. HOSPITAL INFO PAGE (Fixed Image & Address) ---
@patient_bp.route('/hospital-info/<hos_id>')
def hospital_info(hos_id):
    from app import db
    # Check if user is logged in first
    if not is_logged_in():
        return redirect(url_for('auth_bp.login'))

    hospital = db.hospitals.find_one({"user_id": hos_id})
    if not hospital:
        return "Hospital Not Found", 404

    # Fix: Default Image agar database mein image_url nahi hai
    if not hospital.get('image_url'):
        hospital['image_url'] = "/static/images/default-hospital.jpg" # Ya koi live URL

    # Fix: Address fallback
    if not hospital.get('address'):
        hospital['address'] = "Address information is being updated by the hospital."

    reviews = list(db.reviews.find({"hospital_id": hos_id}))
    avg_rating = sum([r['rating'] for r in reviews]) / len(reviews) if reviews else 5.0
    
    return render_template('hospital_info.html', hospital=hospital, avg_rating=round(avg_rating, 1), review_count=len(reviews))

# --- 6. POLLING & SOS LOGIC ---
@patient_bp.route('/get_sos_responses', methods=['GET'])
def get_live_responses():
    from app import db
    if not is_logged_in():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    patient_id = session.get('user_id')
    latest_request = db.emergency_requests.find_one({"patient_id": patient_id, "status": "active"}, sort=[("_id", -1)])
    if not latest_request:
        return jsonify({"status": "no_active_request", "hospitals": []})
    
    return jsonify({
        "status": "success",
        "sos_id": latest_request['sos_id'],
        "hospitals": latest_request.get('responses', []) 
    })

@patient_bp.route('/final_selection', methods=['POST'])
def final_selection():
    from app import db
    # Isse login redirect problem solve hogi
    if not is_logged_in():
        return jsonify({"status": "redirect", "url": url_for('auth_bp.login')}), 401

    data = request.json
    sos_id = data.get('sos_id')
    hospital_id = data.get('hospital_id')
    
    db.emergency_requests.update_one(
        {"sos_id": sos_id},
        {"$set": {
            "status": "patient_confirmed",
            "selected_hospital_id": hospital_id
        }}
    )
    return jsonify({"status": "success", "message": "Hospital Selected!"})

# --- 7. EMERGENCY BROADCAST ---
@patient_bp.route('/broadcast_emergency', methods=['POST'])
def broadcast_emergency():
    from app import db
    if not is_logged_in():
        return jsonify({"status": "error", "message": "Please Login First"}), 401
    try:
        data = request.json
        p_lat, p_lng = float(data.get('lat')), float(data.get('lng'))
        sos_id = f"SOS-{random.randint(10000, 99999)}"
        
        sos_entry = {
            "sos_id": sos_id,
            "patient_id": session.get('user_id'),
            "patient_name": session.get('name'),
            "phone": session.get('phone', 'N/A'),
            "description": data.get('description', 'Medical Emergency!'),
            "location": { "type": "Point", "coordinates": [p_lng, p_lat] },
            "status": "active",
            "responses": [], 
            "timestamp": random.randint(100000, 999999) 
        }
        db.emergency_requests.insert_one(sos_entry)
        return jsonify({"status": "success", "sos_id": sos_id}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
