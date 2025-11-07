"""
FarmFlow Enhanced Flask Application
Disease % Detection + DCRI + Insurance
"""

from flask import Flask, render_template, request, jsonify
import numpy as np
from PIL import Image
import requests
import json
import os
from io import BytesIO
import base64
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import random

# =============== Initialize Flask App ===============
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# =============== Configuration ===============
PINATA_API_KEY = ""
PINATA_SECRET_KEY = ""

# =============== Load Models ===============
print("=" * 60)
print("Loading models...")

# Disease Percentage Model
try:
    import tensorflow as tf
    from tensorflow import keras
    disease_pct_model = keras.models.load_model('disease_percentage_model.h5')
    DISEASE_PCT_MODEL_AVAILABLE = True
    print("✅ Disease Percentage model loaded")
except Exception as e:
    DISEASE_PCT_MODEL_AVAILABLE = False
    print(f"⚠️ Disease Percentage model not available: {e}")
    print("   Using mock predictions")

# DCRI Model (RandomForest version)
try:
    import joblib
    dcri_model, dcri_scaler = joblib.load('dcri_model.pkl')
    DCRI_MODEL_AVAILABLE = True
    print("✅ DCRI model loaded")
except Exception as e:
    DCRI_MODEL_AVAILABLE = False
    print(f"⚠️ DCRI model not available: {e}")
    print("   Using mock predictions")

# Store crop DCRI data
crop_dcri_data = {}

# Crop type mapping
CROP_MAP = {
    "Tomato": 0, "Potato": 1, "Pepper": 2,
    "Corn": 3, "Apple": 4, "Grape": 5,
    "Wheat": 6, "Rice": 7, "Cotton": 8
}

# =============== Helper Functions ===============

def upload_to_ipfs(image_file):
    """Upload image to IPFS via Pinata"""
    try:
        # Remove data URL prefix if present
        if isinstance(image_file, str):
            if ',' in image_file:
                image_file = image_file.split(',')[1]
            image_data = base64.b64decode(image_file)
            image_file = BytesIO(image_data)
        
        url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
        headers = {
            'pinata_api_key': PINATA_API_KEY,
            'pinata_secret_api_key': PINATA_SECRET_KEY
        }
        
        files = {'file': ('crop_image.jpg', image_file, 'image/jpeg')}
        response = requests.post(url, files=files, headers=headers, timeout=30)
        
        if response.status_code == 200:
            ipfs_hash = response.json()['IpfsHash']
            print(f"✅ Uploaded to IPFS: {ipfs_hash}")
            return ipfs_hash
        else:
            print(f"⚠️ IPFS upload failed: {response.text}")
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            return f"QmMock{timestamp}"
            
    except Exception as e:
        print(f"IPFS upload error: {e}")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"QmMock{timestamp}"

def get_weather_data(lat, lon):
    """Fetch weather data from Open-Meteo API (Free, no API key needed)"""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': lat,
            'longitude': lon,
            'current': 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
            'timezone': 'auto'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            current = data.get('current', {})
            
            weather_info = {
                'temperature': round(current.get('temperature_2m', 25.0), 1),
                'humidity': round(current.get('relative_humidity_2m', 60.0), 1),
                'rainfall': round(current.get('precipitation', 0.0), 1),
                'wind_speed': round(current.get('wind_speed_10m', 10.0), 1)
            }
            
            print(f"✅ Weather data fetched: Temp={weather_info['temperature']}°C, Humidity={weather_info['humidity']}%")
            return weather_info
        else:
            print(f"⚠️ Weather API error: {response.status_code}")
            return get_default_weather()
            
    except Exception as e:
        print(f"Weather API error: {e}")
        return get_default_weather()

def get_default_weather():
    """Return default weather values"""
    return {
        'temperature': 25.0,
        'humidity': 60.0,
        'rainfall': 10.0,
        'wind_speed': 12.0
    }

def get_soil_data(lat, lon):
    """Get soil data from ISRIC SoilGrids API"""
    try:
        # ISRIC SoilGrids v2.0 API
        url = f"https://rest.isric.org/soilgrids/v2.0/properties/query"
        params = {
            'lon': lon,
            'lat': lat,
            'property': 'nitrogen,phh2o,cec',  # nitrogen, pH, cation exchange capacity
            'depth': '0-5cm',
            'value': 'mean'
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            properties = data.get('properties', {}).get('layers', [])
            
            soil_info = {
                'ph': 6.5,  # default
                'moisture': 50.0,  # estimated
                'nitrogen': 30.0,  # default
                'phosphorus': 25.0,  # default
                'potassium': 35.0  # default
            }
            
            # Extract pH (phh2o)
            for prop in properties:
                if prop.get('name') == 'phh2o':
                    depths = prop.get('depths', [])
                    if depths:
                        # pH is stored as pH * 10, so divide by 10
                        ph_value = depths[0].get('values', {}).get('mean', 65) / 10
                        soil_info['ph'] = round(ph_value, 2)
                
                # Extract nitrogen
                elif prop.get('name') == 'nitrogen':
                    depths = prop.get('depths', [])
                    if depths:
                        # Nitrogen in cg/kg, convert to a reasonable scale
                        nitrogen_value = depths[0].get('values', {}).get('mean', 30) / 10
                        soil_info['nitrogen'] = round(nitrogen_value, 1)
            
            # Add some variation to other parameters
            soil_info['moisture'] = round(45 + np.random.uniform(-10, 10), 1)
            soil_info['phosphorus'] = round(25 + np.random.uniform(-5, 5), 1)
            soil_info['potassium'] = round(35 + np.random.uniform(-5, 5), 1)
            
            print(f"✅ Soil data fetched: pH={soil_info['ph']}, N={soil_info['nitrogen']}")
            return soil_info
        else:
            print(f"⚠️ Soil API error: {response.status_code}")
            return get_default_soil()
            
    except Exception as e:
        print(f"Soil API error: {e}")
        return get_default_soil()

def get_default_soil():
    """Return default soil values"""
    return {
        'ph': 6.5,
        'moisture': 50.0,
        'nitrogen': 30.0,
        'phosphorus': 25.0,
        'potassium': 35.0
    }

def predict_disease_percentage(image):
    """Predict disease percentage from crop image"""
    if not DISEASE_PCT_MODEL_AVAILABLE:
        # Dummy prediction based on simple image analysis
        return simple_disease_detection(image)
    
    try:
        img = image.resize((224, 224))
        img_array = np.array(img)[None, ...]
        img_array = img_array / 255.0
        
        disease_pct = disease_pct_model.predict(img_array, verbose=0)[0][0]
        print(f"✅ Disease detection: {disease_pct*100:.1f}%")
        return float(disease_pct)
    except Exception as e:
        print(f"Disease % prediction error: {e}")
        return simple_disease_detection(image)

def simple_disease_detection(image):
    """Simple color-based disease detection for demo"""
    try:
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize for faster processing
        image = image.resize((100, 100))
        pixels = np.array(image)
        
        # Detect brown/yellow spots (disease indicators)
        # Brown: high R, low G, low B
        brown_mask = (pixels[:,:,0] > 100) & (pixels[:,:,1] < 100) & (pixels[:,:,2] < 80)
        
        # Yellow spots: high R, high G, low B
        yellow_mask = (pixels[:,:,0] > 150) & (pixels[:,:,1] > 100) & (pixels[:,:,2] < 100)
        
        disease_pixels = np.sum(brown_mask | yellow_mask)
        total_pixels = pixels.shape[0] * pixels.shape[1]
        
        disease_ratio = disease_pixels / total_pixels
        
        # Add randomness for variety
        disease_pct = min(0.5, disease_ratio * 3 + np.random.uniform(0, 0.15))
        
        print(f"✅ Simple disease detection: {disease_pct*100:.1f}%")
        return round(disease_pct, 4)
        
    except Exception as e:
        print(f"Simple disease detection error: {e}")
        return np.random.uniform(0.05, 0.25)

def calculate_dcri(crop_name, disease_percent, weather_data, soil_data):
    """Calculate Dynamic Crop Risk Index (alpha score)"""
    
    # Get crop type encoding
    crop_type = CROP_MAP.get(crop_name, 0)
    
    if not DCRI_MODEL_AVAILABLE:
        # Dummy DCRI calculation
        return simple_dcri_calculation(disease_percent, weather_data, soil_data)
    
    try:
        # Prepare features for RandomForest model
        # Features: crop_type, disease_percent, soil_moisture, temperature,
        #           humidity, rainfall, soil_ph, region_risk_factor
        features = np.array([[
            crop_type,
            disease_percent * 100,  # Convert to percentage (0-100)
            soil_data.get('moisture', 50),
            weather_data['temperature'],
            weather_data['humidity'],
            weather_data['rainfall'],
            soil_data['ph'],
            0.5  # Default region risk factor
        ]])
        
        # Scale and predict
        features_scaled = dcri_scaler.transform(features)
        alpha = dcri_model.predict(features_scaled)[0]
        
        # Convert to 0-1000 scale
        alpha_score = int(alpha * 1000)
        
        print(f"✅ DCRI calculated: α={alpha:.3f} ({alpha_score}/1000)")
        return alpha_score
        
    except Exception as e:
        print(f"DCRI calculation error: {e}")
        return simple_dcri_calculation(disease_percent, weather_data, soil_data)

def simple_dcri_calculation(disease_percent, weather_data, soil_data):
    """Simple DCRI calculation for demo"""
    # Disease component (0-400)
    disease_score = disease_percent * 400
    
    # Climate component (0-300)
    temp = weather_data['temperature']
    humidity = weather_data['humidity']
    rainfall = weather_data['rainfall']
    
    temp_stress = abs(temp - 25) * 5
    humidity_stress = abs(humidity - 60) * 2
    rainfall_stress = max(0, rainfall - 30) * 3
    
    climate_score = min(300, temp_stress + humidity_stress + rainfall_stress)
    
    # Soil component (0-300)
    ph = soil_data.get('ph', 6.5)
    moisture = soil_data.get('moisture', 50)
    
    ph_stress = abs(ph - 6.5) * 50
    moisture_stress = abs(moisture - 50) * 3
    
    soil_score = min(300, ph_stress + moisture_stress)
    
    # Total alpha score (0-1000)
    alpha_score = int(disease_score + climate_score + soil_score)
    alpha_score = max(0, min(1000, alpha_score))
    
    print(f"✅ Simple DCRI: Disease={disease_score:.0f}, Climate={climate_score:.0f}, Soil={soil_score:.0f}, Total={alpha_score}")
    return alpha_score

# =============== Routes ===============

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/dashboard/<role>")
def dashboard(role):
    return render_template("index.html", role=role)

# =============== API Endpoints ===============

@app.route("/api/process_crop_listing", methods=["POST"])
def process_crop_listing():
    """Process new crop listing with DCRI calculation"""
    try:
        data = request.get_json()
        crop_id = data.get('cropId', 0)
        crop_name = data.get('cropName', 'Tomato')
        image_base64 = data['image']
        lat = float(data['latitude'])
        lon = float(data['longitude'])
        
        print(f"\n{'='*60}")
        print(f"Processing crop: {crop_name} at ({lat}, {lon})")
        print(f"{'='*60}")
        
        # Decode image
        image_data = base64.b64decode(image_base64.split(',')[1])
        img = Image.open(BytesIO(image_data)).convert("RGB")
        
        # Step 1: Upload to IPFS
        print("\n1️⃣ Uploading to IPFS...")
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        ipfs_hash = upload_to_ipfs(img_bytes)
        
        # Step 2: Predict disease percentage
        print("\n2️⃣ Analyzing crop for disease...")
        disease_pct = predict_disease_percentage(img)
        
        # Step 3: Get weather data
        print("\n3️⃣ Fetching weather data...")
        weather_data = get_weather_data(lat, lon)
        
        # Step 4: Get soil data
        print("\n4️⃣ Fetching soil data...")
        soil_data = get_soil_data(lat, lon)
        
        # Step 5: Calculate DCRI
        print("\n5️⃣ Calculating DCRI (alpha score)...")
        alpha_score = calculate_dcri(crop_name, disease_pct, weather_data, soil_data)
        
        # Store for daily updates
        if crop_id:
            crop_dcri_data[str(crop_id)] = {
                'crop_name': crop_name,
                'latitude': lat,
                'longitude': lon,
                'last_disease_pct': disease_pct,
                'last_update': datetime.now().isoformat()
            }
            
            # Save to file
            with open('crop_dcri_data.json', 'w') as f:
                json.dump(crop_dcri_data, f)
        
        print(f"\n{'='*60}")
        print(f"✅ Processing complete!")
        print(f"   IPFS: {ipfs_hash}")
        print(f"   Disease: {disease_pct*100:.1f}%")
        print(f"   Alpha: {alpha_score}/1000")
        print(f"{'='*60}\n")
        
        return jsonify({
            'success': True,
            'ipfsHash': ipfs_hash,
            'diseasePercentage': disease_pct,
            'alphaScore': alpha_score,
            'weatherData': weather_data,
            'soilData': soil_data
        })
        
    except Exception as e:
        print(f"\n❌ Error in process_crop_listing: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route("/api/update_dcri_daily", methods=["POST"])
def update_dcri_daily():
    """Update DCRI for all active crops (called by scheduler)"""
    try:
        print(f"\n{'='*60}")
        print(f"Daily DCRI Update - {datetime.now()}")
        print(f"{'='*60}")
        
        updates = []
        
        for crop_id, data in crop_dcri_data.items():
            crop_name = data.get('crop_name', 'Tomato')
            lat = data['latitude']
            lon = data['longitude']
            
            print(f"\nUpdating Crop ID {crop_id} ({crop_name})...")
            
            # Get fresh data
            weather_data = get_weather_data(lat, lon)
            soil_data = get_soil_data(lat, lon)
            
            # Simulate disease progression
            old_disease_pct = data.get('last_disease_pct', 0.3)
            disease_pct = np.clip(old_disease_pct + np.random.uniform(-0.05, 0.05), 0, 1)
            
            # Calculate new DCRI
            alpha_score = calculate_dcri(crop_name, disease_pct, weather_data, soil_data)
            
            updates.append({
                'cropId': crop_id,
                'alphaScore': alpha_score,
                'timestamp': datetime.now().isoformat()
            })
            
            crop_dcri_data[crop_id]['last_disease_pct'] = disease_pct
            crop_dcri_data[crop_id]['last_update'] = datetime.now().isoformat()
        
        # Save updated data
        with open('crop_dcri_data.json', 'w') as f:
            json.dump(crop_dcri_data, f)
        
        print(f"\n✅ Updated {len(updates)} crops")
        print(f"{'='*60}\n")
        
        return jsonify({'success': True, 'updates': updates})
        
    except Exception as e:
        print(f"\n❌ Daily update error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

# =============== Scheduler ===============

def scheduled_dcri_update():
    """Daily DCRI update job"""
    try:
        print(f"\n🕐 Running scheduled DCRI update at {datetime.now()}")
        with app.test_request_context():
            update_dcri_daily()
    except Exception as e:
        print(f"Scheduled update error: {e}")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=scheduled_dcri_update, trigger="cron", hour=0, minute=0)
scheduler.start()

# Load existing crop data
try:
    with open('crop_dcri_data.json', 'r') as f:
        crop_dcri_data = json.load(f)
    print(f"✅ Loaded {len(crop_dcri_data)} existing crops")
except FileNotFoundError:
    crop_dcri_data = {}
    print("⚠️ No existing crop data found")

# =============== Run App ===============

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("FarmFlow Enhanced Application")
    print("=" * 60)
    print(f"Disease % Model: {'✅ Available' if DISEASE_PCT_MODEL_AVAILABLE else '⚠️ Using Mock'}")
    print(f"DCRI Model: {'✅ Available' if DCRI_MODEL_AVAILABLE else '⚠️ Using Mock'}")
    print(f"Weather API: Open-Meteo (Free)")
    print(f"Soil API: ISRIC SoilGrids v2.0")
    print("=" * 60 + "\n")
    
    app.run(host="0.0.0.0", port=5000, debug=True)