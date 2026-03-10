"""
Explainable AI: Google Gemini API to generate human-readable diagnosis.
"""

import os
from google import genai

def get_explanation(sensor_data: dict, prediction: str, threshold_breach: dict = None) -> str:
    """
    Send sensor values, ML prediction, and threshold breach info to Gemini for diagnosis.
    
    sensor_data: e.g. {"vib": 22.3, "temp": 75.5, "amp": 2.1}
    prediction: "Faulty" or "Healthy"  
    threshold_breach: e.g. {"vib_value": 22.3, "vib_danger": 15, "reason": "Vibration 22.3 exceeds danger threshold (15)"}
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Explanation unavailable: GEMINI_API_KEY not set."
    
    try:
        client = genai.Client(api_key=api_key)
        
        # Build a richer context-aware prompt
        sensor_context = (
            f"Vibration: {sensor_data.get('vib', 'N/A')} m/s² | "
            f"Temperature: {sensor_data.get('temp', 'N/A')}°C | "
            f"Amperage: {sensor_data.get('amp', 'N/A')} A"
        )
        
        threshold_context = ""
        if threshold_breach:
            threshold_context = (
                f"\n**THRESHOLD BREACH DETECTED**: {threshold_breach.get('reason', 'Unknown breach')}\n"
                f"The reading has exceeded industrial safety limits:"
            )
            if 'vib_value' in threshold_breach:
                threshold_context += f"\n  • Vibration: {threshold_breach['vib_value']} m/s² (danger limit: {threshold_breach.get('vib_danger', 15)} m/s²)"
            if 'temp_value' in threshold_breach:
                threshold_context += f"\n  • Temperature: {threshold_breach['temp_value']}°C (danger limit: {threshold_breach.get('temp_danger', 60)}°C)"
        
        prediction_context = f"ML Model Prediction: {prediction}"
        
        prompt = f"""You are an industrial motor maintenance expert. Analyze this motor condition:

**SENSOR READINGS:**
{sensor_context}

{threshold_context}

**MODEL PREDICTION:** {prediction_context}

**YOUR TASK:**
Provide a technical diagnosis for a maintenance technician. Consider:
1. If thresholds are exceeded, this is a CRITICAL issue regardless of ML prediction
2. Comment on the severity (e.g., "immediate shutdown required" vs "monitor closely")
3. Likely root causes (bearing wear, imbalance, thermal issue, etc.)
4. Recommended actions

Respond in 2-3 sentences maximum, technical but actionable."""
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip() if response.text else "No explanation generated."
    except Exception as e:
        return f"Explanation error: {str(e)}"
