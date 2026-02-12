from google import genai
import os
from dotenv import load_dotenv
load_dotenv()
print("API KEY =", os.getenv("GOOGLE_API_KEY"))

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

for m in client.models.list():
    print(m.name)
