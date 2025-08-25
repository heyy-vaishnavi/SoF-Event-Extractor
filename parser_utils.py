import re
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import docx
import fitz
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

def normalize_text(text: str) -> str:
    """Clean and normalize OCR text."""
    # Replace common OCR errors
    replacements = {
        r'\s+': ' ',
        r'\b(?:@|at|\$)\s*': ' ',  # Clean up time indicators
        r'\b(?:NOVMBER|Novemebr)\b': 'NOVEMBER',
        r'\b(?:JANUARY|JAN)\b': 'JAN',
        r'\b(?:FEBRUARY|FEB)\b': 'FEB',
        r'\b(?:MARCH|MAR)\b': 'MAR',
        r'\b(?:APRIL|APR)\b': 'APR',
        r'\b(?:MAY)\b': 'MAY',
        r'\b(?:JUNE|JUN)\b': 'JUN',
        r'\b(?:JULY|JUL)\b': 'JUL',
        r'\b(?:AUGUST|AUG)\b': 'AUG',
        r'\b(?:SEPTEMBER|SEP)\b': 'SEP',
        r'\b(?:OCTOBER|OCT)\b': 'OCT',
        r'\b(?:NOVEMBER|NOV)\b': 'NOV',
        r'\b(?:DECEMBER|DEC)\b': 'DEC',
        r'\b(?:st|nd|rd|th)\b': '',  # Remove ordinal suffixes
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    text = text.strip()
    return text

def parse_docx(file_path: str) -> str:
    """Extract text from DOCX file."""
    try:
        doc = docx.Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        raise Exception(f"Error parsing DOCX: {str(e)}")

def parse_pdf_plumber(file_path: str) -> List[str]:
    """Extract text from PDF using pdfplumber."""
    if pdfplumber is None:
        raise ImportError("pdfplumber is not installed. Please install it with 'pip install pdfplumber'")
    
    try:
        text_pages = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_pages.append(text)
        return text_pages
    except Exception as e:
        raise Exception(f"Error parsing PDF with pdfplumber: {str(e)}")

def parse_pdf_fitz(file_path: str) -> List[str]:
    """Extract text from PDF using fitz (PyMuPDF)."""
    try:
        text_pages = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text:
                    text_pages.append(text)
        return text_pages
    except Exception as e:
        raise Exception(f"Error parsing PDF with fitz: {str(e)}")

def extract_document_metadata(text: str) -> Dict[str, str]:
    """Extract metadata from SoF text."""
    metadata = {}
    
    # Vessel name
    vessel_match = re.search(r"2\.\s*Vessel Name\s*[:\-]?\s*([^\n]+)", text, re.IGNORECASE)
    if not vessel_match:
        vessel_match = re.search(r"Vessel Name\s*[:\-]?\s*([^\n]+)", text, re.IGNORECASE)
    if vessel_match:
        metadata["vessel"] = vessel_match.group(1).strip()
    
    # Port of Loading (POL)
    pol_match = re.search(r"3\.\s*Port\s*[:\-]?\s*POL\s*([^\n\-]+)", text, re.IGNORECASE)
    if pol_match:
        metadata["voyage_from"] = pol_match.group(1).strip()
    
    # Port of Discharge (POD)
    pod_match = re.search(r"6\.\s*Port\s*[:\-]?\s*POD\s*([^\n\-]+)", text, re.IGNORECASE)
    if pod_match:
        metadata["voyage_to"] = pod_match.group(1).strip()
    
    return metadata

def parse_date_time(date_str: str, time_str: str, year: int) -> Optional[datetime]:
    """Parse date and time strings into a datetime object."""
    try:
        # Parse month
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        
        # Clean date string
        date_str = re.sub(r'(st|nd|rd|th)', '', date_str.upper())
        month = None
        
        # Find month in date string
        for month_name, month_num in month_map.items():
            if month_name in date_str:
                month = month_num
                # Extract day number
                day_match = re.search(r'(\d{1,2})', date_str)
                if day_match:
                    day = int(day_match.group(1))
                    break
        
        if month is None:
            return None
        
        # Parse time
        if time_str:
            time_str = time_str.replace('@', '').strip()
            if ':' in time_str:
                hours, minutes = map(int, time_str.split(':'))
            else:
                # Handle times like "0700" instead of "07:00"
                if len(time_str) == 4:
                    hours, minutes = int(time_str[:2]), int(time_str[2:])
                else:
                    return None
        else:
            hours, minutes = 0, 0
        
        return datetime(year, month, day, hours, minutes)
        
    except (ValueError, AttributeError):
        return None

def extract_events_enhanced(text: str) -> List[Dict[str, str]]:
    """Extract events from SoF text with proper date-time handling."""
    events = []
    
    # Extract year from text
    year_match = re.search(r'\b(20\d{2})\b', text)
    current_year = int(year_match.group(1)) if year_match else datetime.now().year
    
    # Define event patterns with their corresponding search patterns
    event_patterns = [
        # Loading events
        (r'loading commenced', 'LOADING COMMENCED'),
        (r'loading completed', 'LOADING COMPLETED'),
        (r'load.*commence', 'LOADING COMMENCED'),
        (r'load.*complete', 'LOADING COMPLETED'),
        
        # Discharging events
        (r'discharging commenced', 'DISCHARGING COMMENCED'),
        (r'discharging completed', 'DISCHARGING COMPLETED'),
        (r'discharge.*commence', 'DISCHARGING COMMENCED'),
        (r'discharge.*complete', 'DISCHARGING COMPLETED'),
        
        # Vessel movement events
        (r'vessel sailed', 'VESSEL SAILED'),
        (r'vessel arrived', 'VESSEL ARRIVED'),
        (r'vessel anchor', 'VESSEL ANCHORED'),
        (r'vessel.*sail', 'VESSEL SAILED'),
        (r'vessel.*arrive', 'VESSEL ARRIVED'),
        
        # Port operations
        (r'berth', 'BERTHED'),
        (r'quarantine', 'QUARANTINE'),
        (r'immigration', 'IMMIGRATION'),
        (r'notice of readiness', 'NOTICE OF READINESS'),
        (r'cargo document', 'CARGO DOCUMENT ON BOARD'),
        (r'document.*board', 'CARGO DOCUMENT ON BOARD'),
    ]
    
    # First, find all date patterns in the text
    date_pattern = r'(\d{1,2}(?:st|nd|rd|th)?\s*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Za-z]*)'
    time_pattern = r'(@?\s*\d{1,2}:\d{2}|@?\s*\d{3,4})'
    
    # Find all date-time combinations
    date_time_matches = re.finditer(fr'{date_pattern}\s*{time_pattern}', text, re.IGNORECASE)

    
    for match in date_time_matches:
        date_str = match.group(1).strip()
        time_str = match.group(2).replace('@', '').strip()
        
        # Parse the date and time
        event_datetime = parse_date_time(date_str, time_str, current_year)
        if not event_datetime:
            continue
        
        # Get the context around this date-time (50 characters before and after)
        start_idx = max(0, match.start() - 50)
        end_idx = min(len(text), match.end() + 50)
        context = text[start_idx:end_idx]
        
        # Determine what event this date-time is associated with
        event_type = "UNKNOWN EVENT"
        for pattern, event_name in event_patterns:
            if re.search(pattern, context, re.IGNORECASE):
                event_type = event_name
                break
        
        events.append({
            "event": event_type,
            "start": event_datetime.isoformat(),
            "end": event_datetime.isoformat(),
            "remarks": context.strip()
        })
    
    # Also look for specific event patterns that might not have been captured
    for pattern, event_name in event_patterns:
        event_matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in event_matches:
            # Check if this event is already captured
            context = text[max(0, match.start()-30):min(len(text), match.end()+30)]
            already_captured = any(
                event_name == e["event"] and context in e["remarks"] 
                for e in events
            )
            
            if not already_captured:
                # Try to find a date near this event
                date_nearby = re.search(
                    fr'{date_pattern}\s*{time_pattern}',
                    text[max(0, match.start()-100):min(len(text), match.end()+100)],
                    re.IGNORECASE
                )
                
                if date_nearby:
                    date_str = date_nearby.group(1).strip()
                    time_str = date_nearby.group(2).replace('@', '').strip()
                    event_datetime = parse_date_time(date_str, time_str, current_year)
                    
                    events.append({
                        "event": event_name,
                        "start": event_datetime.isoformat() if event_datetime else "",
                        "end": event_datetime.isoformat() if event_datetime else "",
                        "remarks": context.strip()
                    })
                else:
                    events.append({
                        "event": event_name,
                        "start": "",
                        "end": "",
                        "remarks": context.strip()
                    })
    
    return events

# For backward compatibility
def extract_events(text: str) -> List[Dict[str, str]]:
    return extract_events_enhanced(text)
