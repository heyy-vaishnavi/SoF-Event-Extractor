📌 SOF Event Extractor

The SOF Event Extractor is a simple and efficient web-based tool designed to process and extract structured event details from uploaded files (such as PDFs or text documents). It helps you quickly convert raw event data into a clean and readable format.

This project is built with Flask (Python) for the backend and a clean HTML interface for uploading and viewing results. The main purpose is to automate the parsing of event-related files and provide results in a user-friendly way.


🚀 Features:

📂 Upload event files easily through the web interface.
⚡ Automatically processes the uploaded data and extracts key details.
🗂️ Stores uploaded files in the uploads/ folder and processed outputs in the processed/ folder.
🌐 Generates clean HTML reports that can be viewed directly in the browser (outputs/index.html).
🔧 Minimal dependencies and lightweight architecture.



PROJECT STRUCTURE:


SOF EVENT EXTRACTOR HARSHIT/
│── main.py          # Entry point of the application  
│── server.py        # Flask server for handling routes  
│── parser_utils.py  # Core logic for parsing and extracting events  
│── public/          # Static files (CSS, JS if needed)  
│── uploads/         # Uploaded files are stored here  
│── processed/       # Intermediate processed data  
│── outputs/         # Final results (HTML reports)  
│── index.html       # Main interface for uploading and viewing results  
│── requirements.txt # Python dependencies  
│── README.md        # Project documentation  


HOW TO RUN:

Clone this repository and install dependencies:
    pip install -r requirements.txt

Start the Flask server
    python server.py

Open your browser and go to:
    http://127.0.0.1:8000
    
Upload your file → Process → View the extracted event details!

