import os
from google import genai

def test_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    print(f"API Key present: {bool(api_key)}")
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set!")
        return
        
    try:
        print("Initializing GenAI Client...")
        client = genai.Client(api_key=api_key)
        
        print("Sending test prompt to gemini-2.5-flash...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="Explain why a motor might be vibrating excessively in one sentence.",
        )
        print("\nSUCCESS! Response received:")
        print(response.text)
    except Exception as e:
        import traceback
        print("\nERROR testing Gemini:")
        traceback.print_exc()

if __name__ == "__main__":
    test_gemini()
