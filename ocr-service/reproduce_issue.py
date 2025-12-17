
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.services.extraction_service import extraction_service

# User provided example
# "Property Address: 25126 N Jack Tone Rd | City: Acampo | State: CA | Zip Code: 95220"

def test_extraction():
    # Simulate the text block that OCR might produce
    # Note: The OCR often produces lines. The user said:
    # "in appridal report the address is given this way Property Address: 25126 N Jack Tone Rd | City: Acampo | State: CA | Zip Code: 95220"
    
    ocr_text = """
    Uniform Residential Appraisal Report
    File No. 123456
    
    Property Address: 25126 N Jack Tone Rd | City: Acampo | State: CA | Zip Code: 95220
    
    Borrower: John Doe
    Owner of Public Record: John Doe
    County: San Joaquin
    """
    
    print("--- Testing Extraction ---")
    print(f"Input Text Snippet:\n{ocr_text}\n")
    
    subject = extraction_service.extract_subject_section(ocr_text)
    
    print("\n--- Extracted Results ---")
    print(f"Property Address: '{subject.property_address}'")
    print(f"City:             '{subject.city}'")
    print(f"State:            '{subject.state}'")
    print(f"Zip Code:         '{subject.zip_code}'")
    
    # Check for the reported failure
    if subject.property_address == "City":
        print("\n[FAILURE] Address extracted as 'City'!")
        sys.exit(1)
        
    if "Acampo" not in str(subject.city):
         print(f"\n[FAILURE] City not extracted correctly. Got '{subject.city}'")
         
    if "25126 N Jack Tone Rd" not in str(subject.property_address):
         print(f"\n[FAILURE] Street address mismatch. Got '{subject.property_address}'")
         sys.exit(1)

    print("\n[SUCCESS] Extraction looks correct.")

if __name__ == "__main__":
    test_extraction()
