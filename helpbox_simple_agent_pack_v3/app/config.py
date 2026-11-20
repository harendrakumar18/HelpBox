import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Instance & Port config
HELPBOX_INSTANCE_NAME = os.getenv("HELPBOX_INSTANCE_NAME", "helpbox")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Configurable trials directory (default: ./data/trials relative to agent pack root)
raw_trials_dir = os.getenv("TRIALS_DIR", "./data/trials")
TRIALS_DIR = (BASE_DIR / raw_trials_dir).resolve() if not os.path.isabs(raw_trials_dir) else Path(raw_trials_dir).resolve()

# Database config
raw_db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://helpbox:change_this_local_dev_password@localhost:5432/helpbox"
)

# Normalize URL for SQLAlchemy + psycopg 3 driver
if raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif raw_db_url.startswith("postgresql://") and not raw_db_url.startswith("postgresql+"):
    DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    DATABASE_URL = raw_db_url

# Embedding config (Primary: NeuML/bioclinical-modernbert-base-embeddings, 768 dims)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "NeuML/bioclinical-modernbert-base-embeddings")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))

# Generation Provider: 'ollama' (Default local) | 'gemini' (Optional cloud) | 'openai_compatible' (Private company endpoint)
GENERATION_PROVIDER = os.getenv("GENERATION_PROVIDER", "ollama")

# Ollama settings (Local development default)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:2b-q4_K_M")
OLLAMA_CONTEXT_WINDOW = int(os.getenv("OLLAMA_CONTEXT_WINDOW", "4096"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "196"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "60m")

# Gemini API config (Optional cloud fallback - configured by user)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Private Company Endpoint (Zero paid OpenAI account or billing)
OPENAI_COMPATIBLE_BASE_URL = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "")
OPENAI_COMPATIBLE_MODEL = os.getenv("OPENAI_COMPATIBLE_MODEL", "qwen3.5:2b-q4_K_M")
OPENAI_COMPATIBLE_API_KEY = os.getenv("OPENAI_COMPATIBLE_API_KEY", "not-needed")

# Phase 6: Continuous Background Synchronization
SYNC_ENABLED = os.getenv("SYNC_ENABLED", os.getenv("BACKGROUND_SYNC_ENABLED", "true")).lower() in ("true", "1", "yes")
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", os.getenv("BACKGROUND_SYNC_INTERVAL_SECONDS", "120")))
BACKGROUND_SYNC_ENABLED = SYNC_ENABLED
BACKGROUND_SYNC_INTERVAL_SECONDS = SYNC_INTERVAL_SECONDS

# Ingestion & Chunking settings
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "4"))
CHUNK_TOKEN_SIZE = int(os.getenv("CHUNK_TOKEN_SIZE", "800"))
CHUNK_TOKEN_OVERLAP = int(os.getenv("CHUNK_TOKEN_OVERLAP", "100"))
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() in ("true", "1", "yes")
TABLE_EXTRACTION_ENABLED = os.getenv("TABLE_EXTRACTION_ENABLED", "true").lower() in ("true", "1", "yes")
