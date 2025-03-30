import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import requests
from werkzeug.utils import secure_filename
import google.generativeai as genai
import base64
import json
from datetime import datetime, timedelta
import threading
import time
from gtts import gTTS
import dotenv

# Configure the Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Google API Key not found. Set it as GEMINI_API_KEY in the Space settings.")

genai.configure(api_key=GEMINI_API_KEY)

# Setup the Gemini model
model = genai.GenerativeModel('gemini-1.5-flash')

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-default-secret-key-for-flash-messages")

# Configure upload folder
UPLOAD_FOLDER = 'static/uploads'
AUDIO_FOLDER = 'static/audio'  # <-- Add this line
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(AUDIO_FOLDER, exist_ok=True)
except PermissionError as e:
    raise RuntimeError(f"Failed to create required directories: {e}. Please check directory permissions!")

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_web_pesticide_info(disease, plant_type="Unknown"):
    """Fetch pesticide information from web sources for a specific disease and plant type"""
    query = f"site:agrowon.esakal.com {disease} in {plant_type}"
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": os.getenv("GOOGLE_API_KEY"),
        "cx": os.getenv("GOOGLE_CX"),
        "q": query,
        "num": 3
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "items" in data and len(data["items"]) > 0:
            item = data["items"][0]
            return {
                "title": item.get("title", "No title available"),
                "link": item.get("link", "#"),
                "snippet": item.get("snippet", "No snippet available"),
                "summary": item.get("snippet", "No snippet available")
            }
    except Exception as e:
        print(f"Error retrieving web pesticide info: {str(e)}")
    return None


def get_more_web_info(query):
    """Get more general web information based on a search query"""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": os.getenv("GOOGLE_API_KEY"),
        "cx": os.getenv("GOOGLE_CX"),
        "q": query,
        "num": 3
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        results = []
        if "items" in data:
            for item in data["items"]:
                results.append({
                    "title": item.get("title", "No title available"),
                    "link": item.get("link", "#"),
                    "snippet": item.get("snippet", "No snippet available")
                })
        return results
    except Exception as e:
        print(f"Error retrieving additional articles: {str(e)}")
    return []


def get_commercial_product_info(recommendation, disease_name):
    """Fetch commercial product information related to a pesticide recommendation.
    If no relevant products are found from web sources, return default products based on issue type:
    bacterial, fungicide (disease), or insecticide.
    """
    indiamart_query = f"site:indiamart.com pesticide '{disease_name}' '{recommendation}'"
    krishi_query = f"site:krishisevakendra.in/products pesticide '{disease_name}' '{recommendation}'"

    indiamart_results = get_more_web_info(indiamart_query)
    krishi_results = get_more_web_info(krishi_query)

    results = indiamart_results + krishi_results

    if not results:
        lower_disease = disease_name.lower()
        lower_recommendation = recommendation.lower()

        if ("bacteria" in lower_disease or "bacterial" in lower_disease or
                "bacteria" in lower_recommendation or "bacterial" in lower_recommendation):
            results = [
                {
                    "title": "UPL SAAF Carbendazin Mancozeb Bactericide",
                    "link": "https://www.amazon.in/UPL-SAAF-Carbendazinm12-Mancozeb63-Action/dp/B0DJLQRL44",
                    "snippet": "Bactericide for controlling bacterial infections."
                },
                {
                    "title": "Tropical Tagmycin Bactericide",
                    "link": "https://krushidukan.bharatagri.com/en/products/tropical-tagmycin-bactericide",
                    "snippet": "Bactericide for effective bacterial infection management."
                }
            ]
        elif ("fungus" in lower_disease or "fungicide" in lower_recommendation or
              "antibiotic" in lower_recommendation or "disease" in lower_disease):
            results = [
                {
                    "title": "Plantomycin Bio Organic Antibiotic Effective Disease",
                    "link": "https://www.amazon.in/Plantomycin-Bio-Organic-Antibiotic-Effective-Disease/dp/B0DRVVJKQ4",
                    "snippet": "Bio organic antibiotic for effective control of plant diseases."
                },
                {
                    "title": "WET-TREE Larvicide Thuringiensis Insecticide",
                    "link": "https://www.amazon.in/WET-TREE-Larvicide-Thuringiensis-Insecticide/dp/B0D6R72KHV",
                    "snippet": "Larvicide with thuringiensis for disease prevention."
                }
            ]
        elif ("insecticide" in lower_disease or "insect" in lower_disease or "pest" in lower_disease or
              "insecticide" in lower_recommendation or "insect" in lower_recommendation or "pest" in lower_recommendation):
            results = [
                {
                    "title": "Syngenta Actara Insecticide",
                    "link": "https://www.amazon.in/syngenta-Actara-Insect-Repellent-Insecticide/dp/B08W55XTHS",
                    "snippet": "Effective systemic insecticide for pest control."
                },
                {
                    "title": "Cyhalothrin Insecticide",
                    "link": "https://www.amazon.in/Cyhalothrin-Control-Eradication-Mosquitoes-Crawling/dp/B01N53VH1T",
                    "snippet": "Broad-spectrum insecticide for pest management."
                }
            ]
        else:
            results = [
                {
                    "title": "Syngenta Actara Insecticide",
                    "link": "https://www.amazon.in/syngenta-Actara-Insect-Repellent-Insecticide/dp/B08W55XTHS",
                    "snippet": "Effective systemic insecticide for pest control."
                },
                {
                    "title": "Cyhalothrin Insecticide",
                    "link": "https://www.amazon.in/Cyhalothrin-Control-Eradication-Mosquitoes-Crawling/dp/B01N53VH1T",
                    "snippet": "Broad-spectrum insecticide for pest management."
                }
            ]

    return results


def get_relevant_feedback(plant_name):
    """Retrieve feedback entries relevant to the given plant name from feedback.json."""
    feedback_file = "feedback.json"
    if os.path.exists(feedback_file):
        try:
            with open(feedback_file, "r") as f:
                all_feedback = json.load(f)
            relevant = [entry.get("feedback") for entry in all_feedback if
                        entry.get("plant_name", "").lower() == plant_name.lower()]
            if relevant:
                return " ".join(relevant[:3])
        except Exception as e:
            print(f"Error reading feedback for reinforcement: {e}")
    return ""


def generate_audio(text, language, filename):
    """Generate an MP3 file from text using gTTS."""
    try:
        tts = gTTS(text=text, lang=language, slow=False)
        tts.save(filename)
    except Exception as e:
        print(f"Error generating audio: {e}")


def analyze_plant_image(image_path, plant_name, language):
    try:
        # Load the image
        image_parts = [
            {
                "mime_type": "image/jpeg",
                "data": encode_image(image_path)
            }
        ]

        # Load relevant feedback (reinforcement data) for this plant
        feedback_context = get_relevant_feedback(plant_name)
        feedback_instruction = f" Please consider the following user feedback from similar cases: {feedback_context}" if feedback_context else ""

        # Create prompt for Gemini API with language instruction and feedback reinforcement if available
        prompt = f"""
        Analyze this image of a {plant_name} plant and prioritize determining if it's healthy or has a disease or pest infestation.
        If a disease or pest is detected, provide the following information in JSON format:
        {{"results": [{{"type": "disease/pest", "name": "Name of disease or pest", "probability": "Probability as a percentage", "symptoms": "Describe the visible symptoms", "causes": "Main causes of the disease or pest", "severity": "Low/Medium/High", "spreading": "How it spreads", "treatment": "Treatment options", "prevention": "Preventive measures"}},{{}},{{}}], "is_healthy": boolean indicating if the plant appears healthy, "confidence": "Overall confidence in the analysis as a percentage"}}
        Only return the JSON data and nothing else. Ensure the JSON is valid and properly formatted.
        If the plant appears completely healthy, set is_healthy to true and include an empty results array.
        Additionally, provide the response in {language} language.
        and at end show which all data from feedback was taken into consideration and if no data was taken so no data.
        Addition mostly the user Will be an Indian so the Crop images will also be from india so do the predictions accordingly.
        """

        # Send request to Gemini API
        response = model.generate_content([prompt] + image_parts)

        # Extract the JSON response
        response_text = response.text

        # Find JSON within response text if needed
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1

        if json_start >= 0 and json_end > 0:
            json_str = response_text[json_start:json_end]
            analysis_result = json.loads(json_str)
        else:
            return {
                "error": "Failed to parse the API response",
                "raw_response": response_text
            }

        # ---- Added audio generation feature ----
        # Create a summary text based on the analysis including Spreading, Treatment, and Prevention
        if analysis_result.get('is_healthy', False):
            summary_text = f"Your {plant_name} plant appears to be healthy. Continue with your current care practices."
        elif 'results' in analysis_result and analysis_result['results']:
            summary_text = "Detected issues: "
            for result in analysis_result['results']:
                summary_text += (f"{result.get('name', 'Unknown')}. Symptoms: {result.get('symptoms', '')}. "
                                 f"Causes: {result.get('causes', '')}. Spreading: {result.get('spreading', '')}. "
                                 f"Treatment: {result.get('treatment', '')}. Prevention: {result.get('prevention', '')}. ")
        else:
            summary_text = "Analysis inconclusive."

        # Map language name to gTTS language code
        lang_mapping = {"English": "en", "Hindi": "hi", "Bengali": "bn", "Telugu": "te", "Marathi": "mr", "Tamil": "ta",
                        "Gujarati": "gu", "Urdu": "ur", "Kannada": "kn", "Odia": "or", "Malayalam": "ml"}
        gtts_lang = lang_mapping.get(language, 'en')

        # Generate unique audio filename
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        audio_filename = f"audio_result.mp3"
        audio_path = os.path.join(AUDIO_FOLDER, audio_filename)
        generate_audio(summary_text, gtts_lang, audio_path)

        # Wait until the audio file is created and has nonzero size (up to 5 seconds)
        wait_time = 0
        while (not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0) and wait_time < 5:
            time.sleep(0.5)
            wait_time += 0.5

        # Add relative audio file path for template rendering
        analysis_result['audio_file'] = os.path.join('audio', audio_filename)
        # -----------------------------------------

        return analysis_result

    except Exception as e:
        return {
            "error": str(e),
            "is_healthy": None,
            "results": []
        }


def cleanup_old_files(directory, max_age_hours=1):  # Reduced to 1 hour for Hugging Face
    """Remove files older than the specified age from the directory"""
    while True:
        now = datetime.now()
        for filename in os.listdir(directory):
            if filename == '.gitkeep':  # Skip the .gitkeep file
                continue
            file_path = os.path.join(directory, filename)
            file_age = now - datetime.fromtimestamp(os.path.getctime(file_path))
            if file_age > timedelta(hours=max_age_hours):
                try:
                    os.remove(file_path)
                    print(f"Removed old file: {file_path}")
                except Exception as e:
                    print(f"Error removing {file_path}: {e}")
        time.sleep(300)  # 5 minutes


@app.route('/', methods=['GET'])
def index():
    # GET request - show the upload form
    return render_template('index.html', show_results=False)


@app.route('/feedback', methods=['POST'])
def feedback():
    # Get feedback from form submission
    feedback_text = request.form.get("feedback")
    plant_name = request.form.get("plant_name", "Unknown")
    if not feedback_text:
        flash("Please provide your feedback before submitting.")
        return redirect(url_for('index'))
    feedback_data = {
        "plant_name": plant_name,
        "feedback": feedback_text,
        "timestamp": datetime.now().isoformat()
    }
    feedback_file = "feedback.json"
    if os.path.exists(feedback_file):
        try:
            with open(feedback_file, "r") as f:
                existing_feedback = json.load(f)
        except Exception as e:
            print(f"Error reading feedback file: {e}")
            existing_feedback = []
    else:
        existing_feedback = []
    existing_feedback.append(feedback_data)
    try:
        with open(feedback_file, "w") as f:
            json.dump(existing_feedback, f, indent=4)
    except Exception as e:
        flash(f"Error saving your feedback: {str(e)}")
        return redirect(url_for('index'))
    flash("Thank you for your feedback!")
    return redirect(url_for('index'))


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'plant_image' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))

    file = request.files['plant_image']
    plant_name = request.form.get('plant_name', 'unknown')
    language = request.form.get('language', 'English')

    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))

    if file and allowed_file(file.filename):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        original_filename = secure_filename(file.filename)
        filename = f"{timestamp}_{original_filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        try:
            analysis_result = analyze_plant_image(file_path, plant_name, language)
            if 'error' in analysis_result:
                flash(f"Error analyzing image: {analysis_result['error']}")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return redirect(url_for('index'))
            web_info = {}
            product_info = {}
            if not analysis_result.get('is_healthy', False) and 'results' in analysis_result:
                for result in analysis_result['results']:
                    disease_name = result.get('name', '')
                    if disease_name:
                        web_info[disease_name] = get_web_pesticide_info(disease_name, plant_name)
                        treatment = result.get('treatment', '')
                        if treatment:
                            product_info[disease_name] = get_commercial_product_info(treatment, disease_name)
            response = render_template(
                'results.html',
                results=analysis_result,
                plant_name=plant_name,
                image_path=file_path.replace('static/', '', 1),
                web_info=web_info,
                product_info=product_info
            )

            def delete_file_after_delay(path, delay=30):
                time.sleep(delay)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"Deleted analyzed file: {path}")
                    except Exception as e:
                        print(f"Error deleting {path}: {e}")

            threading.Thread(
                target=delete_file_after_delay,
                args=(file_path,),
                daemon=True
            ).start()

            return response

        except Exception as e:
            flash(f"An error occurred: {str(e)}")
            if os.path.exists(file_path):
                os.remove(file_path)
            return redirect(url_for('index'))

    flash('Invalid file type. Please upload an image (png, jpg, jpeg, gif).')
    return redirect(url_for('index'))


if __name__ == '__main__':
    cleanup_thread = threading.Thread(target=cleanup_old_files, args=(app.config['UPLOAD_FOLDER'],), daemon=True)
    cleanup_thread.start()
    port = int(os.environ.get("PORT", 7860))
    app.run(host='0.0.0.0', port=port)
