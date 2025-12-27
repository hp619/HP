import random
import string
import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mail import Message

auth_bp = Blueprint('auth_bp', __name__)

def generate_unique_id(prefix):
    digits = ''.join(random.choices(string.digits, k=7))
    return f"{prefix}{digits}"

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
        else:
            print(f"Geocoding Failed Status: {response['status']}")
    except Exception as e:
        print(f"Geocoding Error: {e}")
    return None

# ---------------- LOGIN LOGIC ----------------
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        from app import db 
        user_id = request.form.get('user_id', '').strip().upper()
        password = request.form.get('password', '').strip()
        user = db.users.find_one({"user_id": user_id, "password": password})
        if user:
            actual_role = user.get('role') or ('hospital' if user_id.startswith('HOS') else 'patient')
            session['user_id'] = user_id
            session['user_type'] = actual_role
            session['name'] = user.get('patient_name') or user.get('hospital_name', 'User')
            session['phone'] = user.get('phone', 'N/A')
            if actual_role == 'hospital':
                return redirect(url_for('hospital_bp.hospital_home'))
            else:
                return redirect(url_for('patient_bp.patient_home'))
        else:
            flash("Invalid ID or Password! Please check correctly.", "error")
            return redirect(url_for('auth_bp.login'))
    return render_template('login.html')

# ---------------- FORGOT PASSWORD LOGIC ----------------
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        from app import db, mail
        email = request.form.get('email')
        user_id = request.form.get('user_id', '').strip().upper() 
        user = db.users.find_one({"email": email, "user_id": user_id})
        if user:
            otp = random.randint(1000, 9999)
            session['reset_otp'] = str(otp)
            session['reset_email'] = email
            session['reset_user_id'] = user_id 
            try:
                msg = Message('Password Reset OTP - Health Connect', sender='anujmore726@gmail.com', recipients=[email])
                msg.body = f"Aapka Password Reset OTP hai: {otp}\nLogin ID: {user_id}"
                mail.send(msg)
                flash("OTP aapki email par bhej diya gaya hai.", "info")
                return render_template('reset_password.html') 
            except Exception as e:
                flash("Email bhejne mein dikkat aayi: " + str(e), "danger")
        else:
            flash("Ye ID aur Email match nahi ho rahe hain.", "danger")
    return render_template('forgot_password.html')

@auth_bp.route('/verify-reset-password', methods=['POST'])
def verify_reset_password():
    from app import db
    user_otp = request.form.get('otp')
    new_password = request.form.get('new_password')
    conf_password = request.form.get('conf_password') 
    email = session.get('reset_email')
    u_id = session.get('reset_user_id')
    if str(user_otp) != str(session.get('reset_otp')):
        flash("OTP sahi nahi hai!", "danger")
        return render_template('reset_password.html')
    if new_password != conf_password:
        flash("Passwords match nahi kar rahe!", "danger")
        return render_template('reset_password.html')
    db.users.update_one({"email": email, "user_id": u_id}, {"$set": {"password": new_password}})
    session.clear()
    flash("Password badal diya gaya hai! Login karein.", "success")
    return redirect(url_for('auth_bp.login'))

# ---------------- REGISTRATION VIEWS ----------------
@auth_bp.route('/register/patient')
def patient_register():
    return render_template('patient_register.html')

@auth_bp.route('/register/hospital')
def hospital_register():
    return render_template('hospital_register.html')

# ---------------- OTP & MONGODB REGISTRATION API ----------------
@auth_bp.route('/send-otp-only', methods=['POST'])
def send_otp():
    from app import mail, db 
    data = request.json
    email = data.get('email')
    role = data.get('role')
    aadhar = data.get('aadhar_card') # Frontend se aayega

    # --- 1. AADHAR UNIQUE CHECK (For Patients) ---
    if role == 'patient' and aadhar:
        existing_aadhar = db.users.find_one({"aadhar_card": aadhar})
        if existing_aadhar:
            return jsonify({"status": "error", "message": "Bhai, ye Aadhar Card pehle se registered hai!"}), 400

    # --- 2. EMAIL LIMIT CHECK ---
    if role == 'hospital':
        if db.hospitals.find_one({"email": email}):
            return jsonify({"status": "error", "message": "Hospital Email already registered!"}), 400
    elif role == 'patient':
        patient_count = db.users.count_documents({"email": email})
        if patient_count >= 5:
            return jsonify({"status": "error", "message": "Ek email par sirf 5 patients allow hain!"}), 400

    # --- 3. ANTI-SPAM CLEANUP ---
    # Har baar naya OTP mangne par purani temp details clear karo
    session.pop('otp', None)
    session.pop('temp_id', None)
    session.pop('temp_reg_data', None)

    prefix = "HOS" if role == 'hospital' else "PAT"
    generated_id = generate_unique_id(prefix)
    otp = random.randint(1000, 9999)

    session.permanent = True 
    session['otp'] = str(otp)
    session['temp_id'] = generated_id
    session['temp_reg_data'] = data 

    try:
        msg = Message('Your Unique ID & OTP', sender='anujmore726@gmail.com', recipients=[email])
        msg.body = f"Aapka OTP: {otp}\nAapka Login ID: {generated_id}\n\nYeh ID aapke Aadhar/Email ke liye Unique hai."
        mail.send(msg)
        return jsonify({"status": "success", "id": generated_id}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@auth_bp.route('/verify-and-register', methods=['POST'])
def verify_and_register():
    from app import db
    data = request.json
    user_otp = data.get('otp')
    
    if str(user_otp) == str(session.get('otp')):
        reg_data = session.get('temp_reg_data', {})
        reg_id = session.get('temp_id')
        
        reg_data.update(data)
        reg_data['user_id'] = reg_id
        role = reg_data.get('role')
        
        # Location Logic
        lat = reg_data.get('lat')
        lng = reg_data.get('lng')
        location_obj = None
        if lat and lng:
            location_obj = {"type": "Point", "coordinates": [float(lng), float(lat)]}
        else:
            address = reg_data.get('address') or reg_data.get('Address')
            coords = get_coordinates(address)
            if coords:
                location_obj = {"type": "Point", "coordinates": coords}
        
        reg_data['location'] = location_obj

        if role == 'patient':
            reg_data['patient_name'] = reg_data.get('patient_name') or reg_data.get('name')
            # Aadhar ko final data mein confirm karein
            reg_data['aadhar_card'] = reg_data.get('aadhar_card')
        else:
            reg_data['hospital_name'] = reg_data.get('hospital_name') or reg_data.get('h-name')
            reg_data['type'] = 'physical'

        # Final Database Insertion
        try:
            db.users.insert_one(reg_data)
            if role == 'hospital':
                db.hospitals.update_one(
                    {"user_id": reg_id},
                    {"$set": {
                        "user_id": reg_id,
                        "hospital_name": reg_data['hospital_name'],
                        "email": reg_data['email'],
                        "location": location_obj,
                        "phone": reg_data.get('phone')
                    }},
                    upsert=True
                )
            
            session.pop('otp', None)
            session.pop('temp_reg_data', None)
            session.pop('temp_id', None)
            return jsonify({"status": "success"}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": "Database Error: " + str(e)}), 500
    
    return jsonify({"status": "error", "message": "Invalid OTP"}), 400

@auth_bp.route('/logout')
def logout():
    session.clear() 
    flash("Aap successfully logout ho gaye hain.", "info")
    return redirect(url_for('auth_bp.login'))
