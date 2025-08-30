import re
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
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
    
    # Vessel name - more specific pattern
    vessel_match = re.search(r"2\.\s*Vessel\s*Name\s*[:\-]?\s*([A-Za-z0-9\s]+?)(?=\d|\.|\n|$)", text, re.IGNORECASE)
    if not vessel_match:
        vessel_match = re.search(r"Vessel\s*Name\s*[:\-]?\s*([A-Za-z0-9\s]+?)(?=\d|\.|\n|$)", text, re.IGNORECASE)
    if vessel_match:
        metadata["vessel"] = vessel_match.group(1).strip()
    
    # Port of Loading (POL)
    pol_match = re.search(r"3\.\s*Port\s*[:\-]?\s*POL\s*([A-Za-z\s\-]+?)(?=\d|\.|\n|$)", text, re.IGNORECASE)
    if pol_match:
        metadata["voyage_from"] = pol_match.group(1).strip()
    
    # Port of Discharge (POD)
    pod_match = re.search(r"6\.\s*Port\s*[:\-]?\s*POD\s*([A-Za-z\s\-]+?)(?=\d|\.|\n|$)", text, re.IGNORECASE)
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
        date_str = re.sub(r'(st|nd|rd|th)', '', date_str.upper()).strip()
        
        # Extract day and month
        day_match = re.search(r'(\d{1,2})', date_str)
        if not day_match:
            return None
            
        day = int(day_match.group(1))
        month = None
        
        # Find month in date string
        for month_name, month_num in month_map.items():
            if month_name in date_str:
                month = month_num
                break
        
        if month is None:
            return None
        
        # Parse time
        if time_str:
            time_str = time_str.replace('@', '').strip()
            if ':' in time_str:
                try:
                    hours, minutes = map(int, time_str.split(':'))
                except ValueError:
                    return None
            else:
                # Handle times like "0700" instead of "07:00"
                if len(time_str) == 4 and time_str.isdigit():
                    hours, minutes = int(time_str[:2]), int(time_str[2:])
                else:
                    return None
            
            # Validate time values
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                return None
        else:
            hours, minutes = 0, 0
        
        return datetime(year, month, day, hours, minutes)
        
    except (ValueError, AttributeError):
        return None

def extract_events_enhanced(text: str) -> List[Dict[str, str]]:
    """Extract events from SoF text by focusing on numbered events."""
    events = []
    
    # Extract year from text
    year_match = re.search(r'\b(20\d{2})\b', text)
    current_year = int(year_match.group(1)) if year_match else datetime.now().year
    
    # Define event patterns with their corresponding search patterns
    event_patterns = [
        # Loading events
        (r'loading\s+commenced', 'LOADING COMMENCED'),
        (r'loading\s+completed', 'LOADING COMPLETED'),
        
        # Discharging events
        (r'discharging\s+commenced', 'DISCHARGING COMMENCED'),
        (r'discharging\s+completed', 'DISCHARGING COMPLETED'),
        
        # Vessel movement events
        (r'vessel\s+sailed', 'VESSEL SAILED'),
        (r'vessel\s+arrived', 'VESSEL ARRIVED'),
        (r'vessel\s+anchor', 'VESSEL ANCHORED'),
        
        # Port operations
        (r'\bberth\b', 'BERTHED'),
        (r'\bquarantine\b', 'QUARANTINE'),
        (r'\bimmigration\b', 'IMMIGRATION'),
        (r'notice\s+of\s+readiness', 'NOTICE OF READINESS'),
        (r'cargo\s+document', 'CARGO DOCUMENT ON BOARD'),
    ]
    
    # Focus on numbered events in the SoF format
    numbered_events = [
        (6, 'loading commenced'),
        (7, 'loading completed'),
        (9, 'discharging commenced'),
        (10, 'discharging completed'),
        (11, 'cargo document on board'),
        (12, 'vessel sailed'),
    ]
    
    # Pattern to extract numbered events with dates and times
    event_pattern = r'(\d+)\.\s*([A-Za-z\s]+)[:\-]?\s*(\d{1,2}(?:st|nd|rd|th)?\s*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[a-z]*)\s*@?\s*(\d{1,2}:\d{2}|\d{3,4})?'
    
    matches = list(re.finditer(event_pattern, text, re.IGNORECASE))
    for match in matches:
        event_number = int(match.group(1))
        event_text = match.group(2).strip().lower()
        date_str = match.group(3).strip() if match.group(3) else ""
        time_str = match.group(4).strip() if match.group(4) else ""
        
        # Determine event type based on text
        event_type = "UNKNOWN EVENT"
        for pattern, pattern_event_type in event_patterns:
            if re.search(pattern, event_text, re.IGNORECASE):
                event_type = pattern_event_type
                break
        
        # Parse date and time if available
        event_datetime = None
        if date_str and time_str:
            event_datetime = parse_date_time(date_str, time_str, current_year)
        
        # Add the event
        events.append({
            "event": event_type,
            "start": event_datetime.isoformat() if event_datetime else "",
            "end": event_datetime.isoformat() if event_datetime else "",
            "remarks": f"{event_number}. {event_text}"
        })
    
    # Also extract non-numbered events that are important
    non_numbered_events = [
        (r'vessel\s+arrive', 'VESSEL ARRIVED'),
        (r'vessel\s+anchor', 'VESSEL ANCHORED'),
        (r'berth', 'BERTHED'),
        (r'quarantine', 'QUARANTINE'),
        (r'immigration', 'IMMIGRATION'),
        (r'notice\s+of\s+readiness', 'NOTICE OF READINESS'),
    ]
    
    # Pattern to find dates and times
    date_pattern = r'(\d{1,2}(?:st|nd|rd|th)?)\s*(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)'
    time_pattern = r'(@?\s*(\d{1,2}:\d{2}|\d{3,4}))'
    
    # Find all date-time patterns in the text
    date_time_matches = list(re.finditer(f'{date_pattern}\\s*{time_pattern}', text, re.IGNORECASE))
    
    for match in date_time_matches:
        date_str = f"{match.group(1)} {match.group(2)}"
        time_str = match.group(4)
        
        # Parse the date and time
        event_datetime = parse_date_time(date_str, time_str, current_year)
        if not event_datetime:
            continue
        
        # Get context around this date-time
        context_start = max(0, match.start() - 50)
        context_end = min(len(text), match.end() + 50)
        context = text[context_start:context_end]
        
        # Determine what event this date-time is associated with
        event_type = "UNKNOWN EVENT"
        for pattern, pattern_event_type in non_numbered_events:
            if re.search(pattern, context, re.IGNORECASE):
                event_type = pattern_event_type
                break
        
        # Add the event if it's not unknown
        if event_type != "UNKNOWN EVENT":
            events.append({
                "event": event_type,
                "start": event_datetime.isoformat(),
                "end": event_datetime.isoformat(),
                "remarks": context.strip()
            })
    
    # Remove duplicates by event type and timestamp
    unique_events = []
    seen_events = set()
    
    for event in events:
        event_key = f"{event['event']}_{event['start']}"
        if event_key not in seen_events:
            unique_events.append(event)
            seen_events.add(event_key)
    
    # Filter out UNKNOWN events
    unique_events = [event for event in unique_events if event['event'] != 'UNKNOWN EVENT']
    
    # Sort events by datetime
    def get_sort_key(event):
        if event["start"]:
            try:
                return datetime.fromisoformat(event["start"])
            except:
                return datetime.max
        return datetime.max
    
    unique_events.sort(key=get_sort_key)
    
    return unique_events

# For backward compatibility
def extract_events(text: str) -> List[Dict[str, str]]:
    return extract_events_enhanced(text)
