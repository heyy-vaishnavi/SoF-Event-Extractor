import os, io, csv, json, time, tempfile, uuid
import logging
from typing import List, Dict
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime

import pdfplumber, fitz, docx
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential

from parser_utils import extract_events_enhanced, extract_document_metadata, parse_docx, normalize_text, parse_pdf_plumber, parse_pdf_fitz

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------
# Config & dirs
# --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
OUT_DIR = os.path.join(PUBLIC_DIR, "outputs")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(PUBLIC_DIR, exist_ok=True)

# SECURITY: Never hardcode credentials!
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
AZURE_KEY = os.getenv("AZURE_KEY")

azure_client = None
if AZURE_ENDPOINT and AZURE_KEY:
    try:
        azure_client = DocumentAnalysisClient(
            endpoint=AZURE_ENDPOINT,
            credential=AzureKeyCredential(AZURE_KEY)
        )
        logger.info("Azure Form Recognizer client initialized successfully")
    except Exception as e:
        azure_client = None
        logger.error(f"Azure client initialization failed: {e}")
else:
    logger.warning("Azure credentials not configured - OCR fallback disabled")

# --------------------------
# App setup
# --------------------------
app = FastAPI(title="SoF Event Extractor", version="1.0.0")
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static")

# Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Serve index.html if present
INDEX_PATH = os.path.join(PUBLIC_DIR, "index.html")
if os.path.exists(INDEX_PATH):
    @app.get("/", response_class=HTMLResponse)
    def root():
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return f.read()
else:
    @app.get("/")
    def root():
        return {"message": "SoF Event Extractor API", "version": "1.0.0"}

# --------------------------
# PDF parsing helper
# --------------------------
def parse_pdf_to_text(path: str) -> List[str]:
    pages_text: List[str] = []

    # 1) pdfplumber
    try:
        with pdfplumber.open(path) as pdf:
            for p in pdf.pages:
                t = p.extract_text() or ""
                t = t.strip()
                if t:
                    pages_text.append(t)
    except Exception as e:
        logger.error(f"pdfplumber failed: {e}")

    # 2) fitz
    if not pages_text:
        try:
            doc = fitz.open(path)
            for page in doc:
                t = page.get_text("text").strip()
                if t:
                    pages_text.append(t)
        except Exception as e:
            logger.error(f"fitz failed: {e}")

    # 3) Azure layout fallback
    if not pages_text and azure_client:
        try:
            with open(path, "rb") as f:
                poller = azure_client.begin_analyze_document("prebuilt-layout", document=f)
                result = poller.result()

            for page in result.pages:
                lines = [ln.content for ln in (page.lines or []) if getattr(ln, "content", None)]
                t = " ".join(lines).strip()
                if t:
                    pages_text.append(t)
        except Exception as e:
            logger.error(f"Azure OCR failed: {e}")

    return pages_text

def save_outputs(base: str, events: List[Dict], raw_text: str, metadata: Dict):
    json_path = os.path.join(OUT_DIR, f"{base}.json")
    csv_path = os.path.join(OUT_DIR, f"{base}.csv")

    # Enhanced JSON output with metadata
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": metadata,
            "events": events, 
            "raw_text": raw_text,
            "summary": {
                "total_events": len(events),
                "event_types": list(set([e.get("event", "") for e in events])),
                "extraction_date": datetime.now().isoformat()
            }
        }, f, ensure_ascii=False, indent=2)

    # ---------- MINIMAL FIX START ----------
    # CSV output keys now match the event objects produced by parser_utils:
    # event, start, end, remarks (line_number kept if present)
    fieldnames = ["event", "start", "end", "remarks", "line_number"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in events:
            writer.writerow({
                "event": e.get("event", ""),
                "start": e.get("start", ""),
                "end": e.get("end", ""),
                "remarks": e.get("remarks", ""),
                "line_number": e.get("line_number", "")
            })
    # ---------- MINIMAL FIX END ----------

    return json_path, csv_path

# --------------------------
# API Endpoints
# --------------------------
@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in ['.pdf', '.docx']:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please use PDF or DOCX")
    
    # Read file content with size check
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_FILE_SIZE//1024//1024}MB")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Extract raw text according to type
        if suffix == ".docx":
            raw = parse_docx(tmp_path)
        elif suffix == ".pdf":
            pages = parse_pdf_to_text(tmp_path)
            raw = normalize_text("\n".join(pages))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        if not raw or not raw.strip():
            raise HTTPException(status_code=422, detail="Could not extract text from file")

        # Extract metadata and events
        metadata = extract_document_metadata(raw)
        events = extract_events_enhanced(raw)
        
        # Generate unique filename
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = f"sof_{stamp}_{uuid.uuid4().hex[:8]}"

        json_path, csv_path = save_outputs(base, events, raw, metadata)

        links = {
            "json": f"/static/outputs/{os.path.basename(json_path)}",
            "csv": f"/static/outputs/{os.path.basename(csv_path)}"
        }
        
        return {
            "filename": file.filename,
            "events_count": len(events),
            "metadata": metadata,
            "links": links
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/outputs/{filename}")
def download_file(filename: str):
    file_path = os.path.join(OUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    raise HTTPException(status_code=404, detail="File not found")

# Clean up old files periodically
import threading
import schedule

def cleanup_old_files():
    """Remove files older than 24 hours"""
    try:
        now = time.time()
        for filename in os.listdir(OUT_DIR):
            file_path = os.path.join(OUT_DIR, filename)
            if os.path.isfile(file_path) and (now - os.path.getmtime(file_path)) > 86400:  # 24 hours
                os.remove(file_path)
                logger.info(f"Cleaned up old file: {filename}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def run_scheduler():
    schedule.every(6).hours.do(cleanup_old_files)
    while True:
        schedule.run_pending()
        time.sleep(3600)  # Check every hour

# Start cleanup thread
cleanup_thread = threading.Thread(target=run_scheduler, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
