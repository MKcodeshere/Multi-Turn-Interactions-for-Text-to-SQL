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

        # Try multiple encodings to handle different file formats
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
        content_loaded = False

        for encoding in encodings:
            try:
                with open(csv_file, 'r', encoding=encoding) as f:
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
                content_loaded = True
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if not content_loaded:
            print(f"Warning: Could not load {csv_file} with any supported encoding")

    return COLUMN_DESCRIPTIONS
