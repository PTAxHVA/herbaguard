import json
import os
import unicodedata
import asyncio
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel


# Load environment variables
load_dotenv()

# Load the JSON data
DATA_FILE = "data_drug.json"

def load_drugs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    print("Warning: data_drug.json not found.")
    return []

DRUG_DB = load_drugs()

# --- Helper Functions ---
def normalize_text(text: str) -> str:
    """Normalize text to NFC and lowercase."""
    text = text.lower()
    return unicodedata.normalize('NFC', text)

def remove_diacritics(text: str) -> str:
    """Remove vietnamese accents/diacritics."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return unicodedata.normalize('NFC', text)

# --- Pydantic Models ---
class DrugResult(BaseModel):
    drug_id: int = Field(description="The unique identifier of the identified drug")

# --- Agent Definition ---
# Using Gemini 1.5 Flash as established in previous successful setups
model = GoogleModel("gemini-2.5-flash")

agent = Agent(
    model,
    output_type=DrugResult,
    system_prompt=(
        "You are a specialized medical assistant. Your ONLY job is to identify the western drug mentioned "
        "in a user's question about drug interactions. "
        "1. Extract the potential drug name from the question. "
        "2. Call the tool `get_drug_information_of_json` with this extracted name. "
        "3. If the tool returns a drug_id, return that id immediately. "
        "Do not answer the medical question itself."
    ),
)

# --- Tool Definition ---
@agent.tool
def get_drug_information_of_json(ctx: RunContext, drug_name: str) -> int | None:
    """
    Look up a drug by its name in the local database.
    Matches against aliases case-insensitively and handles diacritics.
    """
    print(f"DEBUG: Agent extracted drug name: '{drug_name}'")
    
    search_term = normalize_text(drug_name)
    search_term_no_accents = remove_diacritics(search_term)
    
    for drug in DRUG_DB:
        for alias in drug.get("aliases", []):
            normalized_alias = normalize_text(alias)
            
            # 1. Exact match (normalized)
            if search_term == normalized_alias:
                return drug["drug_id"]
            
            # 2. Fuzzy match (ignoring accents)
            if search_term_no_accents == remove_diacritics(normalized_alias):
                return drug["drug_id"]
                
    return None

# --- Main Execution ---
async def main():
    # Example question targeting a drug (warfarin)
    question = "Cơ chế tương tác giữa hồng sâm và warfarin ảnh hưởng thế nào?"
    print(f"User Query: {question}")
    
    try:
        result = await agent.run(question)
        print("\n--- Final Agent Response ---")
        print(f"Response Type: {type(result.output)}")
        print(f"Result JSON: {result.output.model_dump_json(indent=2)}")
    except Exception as e:
        print(f"Error running agent: {e}")

if __name__ == "__main__":
    if not os.getenv("GOOGLE_API_KEY"):
        print("Please set the GOOGLE_API_KEY environment variable.")
    else:
        asyncio.run(main())
