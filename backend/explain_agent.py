"""
Explainable AI: Google Gemini API to generate human-readable diagnosis.
"""

import os
from google import genai

def get_explanation(sensor_data: dict, prediction: str) -> str:
    """
    Send sensor values and ML prediction to Gemini; return one short sentence for a mechanic.
    sensor_data: e.g. {"vib": 12.5, "temp": 45.2, "amp": 2.1}
    prediction: "Faulty" or "Healthy"
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Explanation unavailable: GEMINI_API_KEY not set."
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "The motor sensors are: "
            f"Vibration={sensor_data.get('vib', 'N/A')}, "
            f"Temperature={sensor_data.get('temp', 'N/A')}°C. "
            f"The ML model predicts: {prediction}. "
            "Explain the technical condition in one short sentence for a mechanic."
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip() if response.text else "No explanation generated."
    except Exception as e:
        return f"Explanation error: {str(e)}"
