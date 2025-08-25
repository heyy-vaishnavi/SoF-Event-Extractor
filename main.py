import os
import streamlit as st
import pandas as pd
from datetime import datetime
from parser_utils import extract_events_enhanced, extract_document_metadata, parse_docx, parse_pdf_plumber, parse_pdf_fitz, normalize_text

st.set_page_config(page_title="SoF Event Extractor", layout="wide")
st.title("📄 SoF Event Extractor (Local UI)")

# Add file size limit
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

uploaded_file = st.file_uploader("Upload a PDF or DOCX file", type=["pdf", "docx"])

if uploaded_file is not None:
    # Check file size
    if uploaded_file.size > MAX_FILE_SIZE:
        st.error(f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.")
        st.stop()
    
    # Save temp file
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    tmp_path = os.path.join(".", f"_tmp{suffix}")
    with open(tmp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    try:
        text_pages = []
        if suffix == ".pdf":
            with st.spinner("Extracting text from PDF..."):
                text_pages = parse_pdf_plumber(tmp_path) 
                if not text_pages:
                    text_pages = parse_pdf_fitz(tmp_path)
        elif suffix == ".docx":
            with st.spinner("Extracting text from DOCX..."):
                text_pages = [parse_docx(tmp_path)]
        else:
            st.error("Unsupported file type")
            st.stop()

        if not text_pages or not any(text_pages):
            st.error("Unable to extract text. Try the FastAPI + Azure OCR flow.")
            st.stop()

        with st.spinner("Processing text and extracting events..."):
            all_text = normalize_text("\n".join(text_pages))
            
            # Extract metadata and events
            metadata = extract_document_metadata(all_text)
            events = extract_events_enhanced(all_text)
        
        # Display metadata
        if metadata:
            st.subheader("Document Metadata")
            metadata_df = pd.DataFrame(list(metadata.items()), columns=["Field", "Value"])
            st.dataframe(metadata_df, use_container_width=True, hide_index=True)
        
        # Display events
        if events:
            st.success(f"Found {len(events)} events")
            df = pd.DataFrame(events)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Download buttons
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "Download CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name=f"events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            with col2:
                st.download_button(
                    "Download JSON",
                    pd.Series({
                        "metadata": metadata, 
                        "events": events, 
                        "raw_text": all_text,
                        "summary": {
                            "total_events": len(events),
                            "event_types": list(set([e.get("event", "") for e in events])),
                            "extraction_date": datetime.now().isoformat()
                        }
                    }).to_json(indent=2).encode("utf-8"),
                    file_name=f"events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        else:
            st.warning("No events found.")
            
        # Show raw text
        with st.expander("View Raw Text (Truncated)"):
            truncated_text = all_text[:5000] + "..." if len(all_text) > 5000 else all_text
            st.text_area("Text", truncated_text, height=300)
            
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
    finally:
        try: 
            os.remove(tmp_path)
        except Exception: 
            pass
