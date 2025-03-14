import os
import re
import fitz  # PyMuPDF for PDF processing
import nltk
from nltk.corpus import stopwords
from transformers import pipeline
import google.generativeai as genai
from flask import Flask, request, render_template, flash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import logging
import string

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY is not set in .env")
    exit(1)  # Exit the program if the API key is missing

# Configure Google Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# Download NLTK stopwords
nltk.download('stopwords')

# Flask App Setup
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load the Hugging Face summarization pipeline
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Function to validate PDF content
def is_valid_pdf(file_path):
    try:
        doc = fitz.open(file_path)
        if len(doc) == 0:  # Check if the PDF has pages
            return False
        return True
    except:
        return False

# Extract text from PDF
def extract_text_from_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text("text")
        if not text.strip():
            raise Exception("No text extracted from the PDF.")
        return text.strip()
    except Exception as e:
        return f"Error extracting text: {e}"

# Clean text by removing stopwords and punctuation
def clean_text(text):
    text = re.sub(r'\s+', ' ', text)  # Remove extra spaces
    text = text.translate(str.maketrans('', '', string.punctuation))  # Remove punctuation
    words = text.split()
    words = [word for word in words if word.lower() not in stopwords.words('english')]
    return ' '.join(words)

# Function to summarize text (handling long documents)
def summarize_text(text, max_length=150):
    if len(text) < 50:
        return "Text is too short to summarize."

    text_chunks = [text[i:i+1024] for i in range(0, len(text), 1024)]
    
    summaries = []
    for chunk in text_chunks:
        try:
            summary = summarizer(chunk, max_length=max_length, min_length=50, do_sample=False)[0]['summary_text']
            summaries.append(summary)
        except Exception as e:
            return f"Error in summarization: {e}"

    return " ".join(summaries)

# Function to generate policies using Google Gemini
def generate_policy(prompt):
    try:
        # Use a supported model (e.g., "gemini-pro")
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        return response.text if response.text else "No policy generated."
    except Exception as e:
        logging.error(f"Error generating policy: {e}")
        return f"Error generating policy: {str(e)}"

# Route for home page
@app.route('/')
def home():
    return render_template('index.html', summary=None, generated_policy=None)

# Route for PDF upload and summarization
@app.route('/upload', methods=['POST'])
def upload_file():
    logging.debug("Uploading file...")
    if 'policy_pdf' not in request.files:
        flash("No file part")
        return render_template('index.html')

    file = request.files['policy_pdf']
    
    if file.filename == '':
        flash("No selected file")
        return render_template('index.html')

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        if not is_valid_pdf(file_path):
            flash("Invalid PDF file. Please upload a valid PDF.")
            os.remove(file_path)  # Clean up the invalid file
            return render_template('index.html')

        # Extract and summarize text
        extracted_text = extract_text_from_pdf(file_path)
        if extracted_text.startswith("Error"):
            flash(extracted_text)
            os.remove(file_path)  # Clean up the file
            return render_template('index.html')

        cleaned_text = clean_text(extracted_text)
        summary = summarize_text(cleaned_text)

        os.remove(file_path)  # Clean up the file after processing
        return render_template('index.html', summary=summary, generated_policy=None)

    flash("Invalid file type. Only PDFs are allowed.")
    return render_template('index.html')

# Route for policy generation
@app.route('/generate_policy', methods=['POST'])
def generate_policy_api():
    scenario = request.form.get("user_scenario", "")
    logging.debug(f"Generating policy for scenario: {scenario}")
    if not scenario:
        flash("Please enter a scenario.")
        return render_template('index.html')

    policy = generate_policy(scenario)
    return render_template('index.html', summary=None, generated_policy=policy)

if __name__ == '__main__':
    app.run(debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")