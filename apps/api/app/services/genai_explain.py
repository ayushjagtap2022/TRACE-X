import os
import json
import google.generativeai as genai
from typing import Dict
from fraud_detector import score_account

# Configure Gemini
API_KEY = os.getenv("GEMINI_API_KEY", "")
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("Warning: GEMINI_API_KEY not set. Narratives will fail.")

def generate_narrative(account_id: str) -> Dict:
    """Generate a human-readable explanation of fraud using Gemini AI."""
    if not API_KEY:
        return {"error": "GEMINI_API_KEY not configured"}
        
    try:
        # Get the full context
        score_data = score_account(account_id)
        
        # Build prompt
        prompt = f"""
        You are a seasoned Anti-Money Laundering (AML) compliance officer writing the 'Suspicious Activity Description' section of an STR for FIU-IND.
        
        Analyze the following fraud detection data for Account {account_id}:
        {json.dumps(score_data, indent=2)}
        
        Write 1 to 3 paragraphs explaining WHY this account is suspicious based ONLY on the detected patterns and confidence scores. 
        Focus heavily on the patterns marked as 'detected': true.
        Do not invent new facts or transactions. Use clear, objective AML terminology (e.g., 'layering', 'smurfing', 'velocity', 'typologies').
        Do NOT include any section headers, introductory greetings, or boilerplate. Just the pure analytical narrative paragraphs.
        """
        
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        
        return {"account_id": account_id, "narrative": response.text.strip()}
    except Exception as e:
        print(f"Gemini error: {e}")
        return {"error": str(e)}
