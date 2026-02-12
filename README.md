# HerbGuard AI Agents

This project contains AI agents built with `pydantic-ai` and Google's Gemini API to extract medical entities (herbs and drugs) from Vietnamese questions and map them to local JSON databases.

## Project Structure

- **herb_agent.py**: Extracts herb names from questions and maps them to IDs in `data.json`.
- **drug_agent.py**: Extracts western drug names from questions and maps them to IDs in `data_drug.json`.
- **data.json**: Database of herbs and their aliases.
- **data_drug.json**: Database of drugs and their aliases.
- **.env**: Stores sensitive environment variables (API keys).

## Prerequisites

- Python 3.9+
- A Google Gemini API Key (Get one from [Google AI Studio](https://aistudio.google.com/))

## Setup

1. **Install Dependencies**
   ```bash
   pip install "pydantic-ai[google]" 
   pip install python-dotenv
   ```

2. **Configure Environment Variables**
   Create a `.env` file in the root directory (if it doesn't exist) and add your API key:
   ```env
   GOOGLE_API_KEY=your_actual_api_key_here
   ```

## Usage    

### Running the Herb Agent
This agent identifies herbs like "nhân sâm" or "bạch quả".
```bash
python herb_agent.py
```

### Running the Drug Agent
This agent identifies drugs like "warfarin" or "metformin".
```bash
python drug_agent.py
```

## How It Works

1. The agent receives a natural language query (e.g., "Cơ chế tương tác giữa hồng sâm và warfarin?").
2. It uses the LLM (Gemini 2.5 Flash) to identify potential entity names.
3. It calls a specific ID lookup tool (`get_information_of_json` or `get_drug_information_of_json`).
4. The tool performs a fuzzy search (case-insensitive, ignores diacritics) against the local JSON files.
5. The agent returns a structured JSON result containing the `herb_id` or `drug_id`.
