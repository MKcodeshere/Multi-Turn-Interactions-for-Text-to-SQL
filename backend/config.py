"""
Configuration management for the application
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DESC_DIR = BASE_DIR / "database_description"

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    print("WARNING: OPENAI_API_KEY not set in .env file")

# Database Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "soccer.db"))

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

# Embedding Configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 3072))

# LLM Configuration
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.7))
MAX_INTERACTION_ROUNDS = int(os.getenv("MAX_INTERACTION_ROUNDS", 12))

# Schema metadata
COLUMN_DESCRIPTIONS = {}

def load_column_descriptions():
    """Load column descriptions from CSV files"""
    global COLUMN_DESCRIPTIONS

    for csv_file in DESC_DIR.glob("*.csv"):
        table_name = csv_file.stem
        COLUMN_DESCRIPTIONS[table_name] = {}

        with open(csv_file, 'r', encoding='utf-8') as f:
            import csv
            reader = csv.DictReader(f)
            for row in reader:
                column_name = row.get('column_name', '').strip()
                if column_name:
                    COLUMN_DESCRIPTIONS[table_name][column_name] = {
                        'description': row.get('column_description', ''),
                        'format': row.get('data_format', ''),
                        'value_description': row.get('value_description', '')
                    }

    return COLUMN_DESCRIPTIONS
