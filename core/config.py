# backend/core/config.py
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field, validator
import warnings

# --- Environment Loading ---
# Determine the project root based on this file's location
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
dotenv_path = os.path.join(project_root, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, verbose=True)
    print(f".env file explicitly loaded from: {dotenv_path}")
else:
    print(f"Warning: .env file not found at {dotenv_path}. Relying on system environment variables.")
    # Attempt loading from current working directory as a fallback
    if os.path.exists(".env"):
        load_dotenv(verbose=True)
        print("Loaded .env from current working directory as fallback.")


# --- Settings Model ---
class Settings(BaseSettings):
    # Core DB connection details
    DB_HOST: str = Field(..., validation_alias='DB_HOST')
    # --- Authentication ---
    # Set DB_USE_WINDOWS_AUTH to True in .env for Windows Authentication
    DB_USE_WINDOWS_AUTH: bool = Field(False, validation_alias='DB_USE_WINDOWS_AUTH')
    # User/Password are optional ONLY if DB_USE_WINDOWS_AUTH is True
    DB_USER: str | None = Field(None, validation_alias='DB_USER')
    DB_PASSWORD: str | None = Field(None, validation_alias='DB_PASSWORD')

    # OpenAI API Key
    OPENAI_API_KEY: str = Field(..., validation_alias='OPENAI_API_KEY')

    # --- MSSQL Specific ---
    DB_DRIVER: str | None = Field(None, validation_alias='DB_DRIVER') # Optional: Specify ODBC driver like {ODBC Driver 17 for SQL Server}

    @validator('DB_PASSWORD')
    def check_credentials_if_not_windows_auth(cls, v, values):
        """Ensure User/Password are set if not using Windows Auth"""
        if not values.get('DB_USE_WINDOWS_AUTH'):
            db_user = values.get('DB_USER')
            if not db_user:
                 raise ValueError('DB_USER must be set if DB_USE_WINDOWS_AUTH is False.')
            if not v: # v is the DB_PASSWORD being validated
                 raise ValueError('DB_PASSWORD must be set if DB_USE_WINDOWS_AUTH is False.')
        elif v: # Password provided but Windows Auth is True
            warnings.warn("DB_PASSWORD is set in environment, but DB_USE_WINDOWS_AUTH is True. Password will be ignored.", stacklevel=2)
        return v


    class Config:
        case_sensitive = False
        extra = 'ignore'
        # env_file = dotenv_path # Redundant with manual load_dotenv above

# --- Initialize Settings ---
try:
    settings = Settings()
    auth_method = "Windows Authentication" if settings.DB_USE_WINDOWS_AUTH else f"SQL User ('{settings.DB_USER}')"
    print(f"Settings loaded: DB_HOST='{settings.DB_HOST}', AuthMethod='{auth_method}', DB_DRIVER='{settings.DB_DRIVER or 'Default'}'")
    if not settings.OPENAI_API_KEY:
        print("Warning: OPENAI_API_KEY missing or empty.")
except ValueError as e:
    # Provide more context on failure, especially validation errors
    print(f"CRITICAL ERROR: Failed to initialize settings from environment variables or '{dotenv_path}'.")
    print(f"Check required variables (DB_HOST, OPENAI_API_KEY) and authentication settings (DB_USE_WINDOWS_AUTH, DB_USER, DB_PASSWORD).")
    print(f"Error details: {e}")
    raise ValueError(f"Configuration loading failed: {e}") from e
except Exception as e:
    print(f"CRITICAL ERROR: An unexpected error occurred during settings initialization.")
    print(f"Error details: {e}")
    raise ValueError(f"Configuration loading failed: {e}") from e

# --- Connection String Builder ---
# Helper function to build the pyodbc connection string
def get_mssql_connection_string(db_name: str | None = None) -> str:
    """Builds the pyodbc connection string for MSSQL, supporting Windows Auth."""
    driver_part = f"DRIVER={settings.DB_DRIVER};" if settings.DB_DRIVER else ""
    server_part = f"SERVER={settings.DB_HOST};"
    database_part = f"DATABASE={db_name};" if db_name else "" # Allow connecting without specific DB initially

    auth_part: str
    if settings.DB_USE_WINDOWS_AUTH:
        auth_part = "Trusted_Connection=yes;"
        print("Debug: Using Windows Authentication (Trusted_Connection=yes)") # Debug print
    else:
        # Validation in Settings model ensures these exist if needed
        uid_part = f"UID={settings.DB_USER};"
        pwd_part = f"PWD={settings.DB_PASSWORD};"
        auth_part = f"{uid_part}{pwd_part}"
        print(f"Debug: Using SQL Authentication (User: {settings.DB_USER})") # Debug print


    # Common options: Adjust encryption/cert based on your server setup
    # TrustServerCertificate=yes is less secure, use only if necessary (e.g., self-signed certs)
    # For production, aim for Encrypt=yes;TrustServerCertificate=no; and ensure the client trusts the server's certificate.
    options = "Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=30;"

    connection_string = f"{driver_part}{server_part}{database_part}{auth_part}{options}"

    # Debug print connection string (redacting password if SQL auth used)
    # debug_conn_string = connection_string
    # if not settings.DB_USE_WINDOWS_AUTH and settings.DB_PASSWORD:
    #     debug_conn_string = connection_string.replace(f"PWD={settings.DB_PASSWORD}", "PWD=***")
    # print(f"Debug: Generated Connection String: {debug_conn_string}")

    return connection_string