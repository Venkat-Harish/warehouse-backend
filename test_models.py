import google.generativeai as genai
from core.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)

models_to_test = ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemini-3.5-flash', 'gemini-2.5-flash-lite', 'gemini-3.1-flash-lite']

for m in models_to_test:
    print(f"Testing {m}...")
    try:
        model = genai.GenerativeModel(m)
        response = model.generate_content("hi")
        print(f"Success for {m}: {response.text[:20]}")
        break # stop on first success
    except Exception as e:
        print(f"Error for {m}: {str(e)[:150]}")
