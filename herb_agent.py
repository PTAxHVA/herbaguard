import json
import os
from unittest import result
from dotenv import load_dotenv  # Import dotenv

# Load environment variables from .env file immediately
load_dotenv()

import unicodedata
import re
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from dotenv import load_dotenv
load_dotenv()
# Load the JSON data
# In a real app, this might be a database or loaded once at startup
DATA_FILE = "data.json"

def load_herbs():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

HERB_DB = load_herbs()

# Helper to normalize text (remove diacritics and lowercase)
def normalize_text(text: str) -> str:
    text = text.lower()
    # Normalize unicode characters
    text = unicodedata.normalize('NFC', text)
    return text

def remove_diacritics(text: str) -> str:
    # Decompose, filter non-spacing marks, recombine
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return unicodedata.normalize('NFC', text)

# Define Pydantic models
class HerbResult(BaseModel):
    herb_id: int = Field(description="The unique identifier of the identified herb")

# Define the Agent
# We use Gemini 1.5 Flash as it is fast and efficient for this task
model = GoogleModel("gemini-2.5-flash")
agent = Agent(
    model,
    output_type=HerbResult,
    system_prompt=(
        "You are a medical assistant specializing in extracting herb names from Vietnamese queries. "
        "Your task IS NOT to answer the medical question directly. "
        "Your task IS ONLY to identify the herb name mentioned in the user's question about drug interactions. "
        "Once you identify the herb name, you MUST use the `get_information_of_json` tool to look up its ID. "
        "If the tool returns a herb ID, return that as your final result. "
        "The herb name might be a common name or scientific name."
    ),
)

@agent.tool
def get_information_of_json(ctx: RunContext, herb_name: str) -> int | None:
    """
    Look up a herb by its name in the local database.
    Matches against aliases case-insensitively and handles diacritics.
    
    Args:
        herb_name: The name of the herb extracted from the question.
    """
    print(f"DEBUG: Tool called with herb_name='{herb_name}'")
    
    search_term = normalize_text(herb_name)
    search_term_no_accents = remove_diacritics(search_term)
    
    for herb in HERB_DB:
        for alias in herb.get("aliases", []):
            # 1. Exact match (case-insensitive)
            normalized_alias = normalize_text(alias)
            if search_term == normalized_alias:
                return herb["herb_id"]
            
            # 2. Match without diacritics (e.g. "hong sam" == "hồng sâm")
            if search_term_no_accents == remove_diacritics(normalized_alias):
                return herb["herb_id"]
                
    return None

import asyncio

async def main():
    # Example question
    question = "Cơ chế tương tác giữa hồng sâm và warfarin ảnh hưởng thế nào?"
    print(f"Question: {question}")
    
    try:
        # Run the agent
        result = await agent.run(question)
        print("\n--- Result ---")
        print(result.output)
        print(result.output.model_dump_json(indent=2))

        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Ensure API key is set
    if not os.getenv("GOOGLE_API_KEY"):
        print("Please set the GOOGLE_API_KEY environment variable.")
        # For demo purposes, you might uncomment the line below and set your key, 
        # but environment variables are safer.
        # os.environ["GOOGLE_API_KEY"] = "YOUR_GOOGLE_API_KEY"
    else:
        asyncio.run(main())
