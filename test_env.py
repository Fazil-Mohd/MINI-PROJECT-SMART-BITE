from decouple import config

try:
    key = config('SPOONACULAR_API_KEY')
    print("✅ Success! API Key =", key)
except Exception as e:
    print("❌ Error:", e)