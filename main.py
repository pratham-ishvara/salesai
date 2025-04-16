# backend/main.py
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Union
import traceback # For detailed logging

# Import schemas and the generator logic function
from models import schemas
from core import ai_sql_generator, config # config needed for health check

app = FastAPI(
    title="AI SQL Generator API (MSSQL)",
    description="API to generate T-SQL queries from natural language using Microsoft SQL Server database schema context. Supports Windows or SQL Authentication.",
    version="1.2.0" # Incremented version
)

# --- CORS Middleware ---
origins = ["*"] # Allow all origins for simplicity, restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoint ---

@app.post("/generate-sql",
          response_model=Union[schemas.GeneratedSqlResponse, schemas.ErrorResponse],
          summary="Generate SQL from natural language (MSSQL)")
async def generate_sql_endpoint(request: schemas.GenerateSqlRequest = Body(...)):
    """
    Takes a natural language prompt and target **MSSQL** database name.

    Fetches the database schema (using connection configured via environment
    variables - Windows Auth or SQL Auth), calls OpenAI to generate T-SQL,
    and returns the generated SQL query.

    **Ensure the service account running this API has appropriate permissions
    on the target database if using Windows Authentication.**
    """
    try:
        # Call the main logic function from ai_sql_generator
        generated_sql, error_message = ai_sql_generator.generate_sql_from_prompt_logic(
            db_name=request.db_name,
            prompt=request.prompt
        )

        if error_message:
             # Determine appropriate status code based on error type
             status_code = 500 # Default to internal server error
             lower_error = error_message.lower()

             # Refine status codes based on common connection/permission errors
             if "not found" in lower_error or "inaccessible" in lower_error or "invalid object name" in lower_error:
                 # Covers DB not found, or potentially table not found if schema fetch failed partially
                 status_code = 404
             elif "permissions" in lower_error or "cannot open database" in lower_error:
                 # Covers lack of permission on DB or specific objects for the connecting user (Windows or SQL)
                 status_code = 403 # Forbidden
             elif "authentication error" in lower_error or "login failed" in lower_error:
                 # Covers SQL Auth failure OR Windows user not having server login rights
                 status_code = 401 # Unauthorized
             elif "network error" in lower_error or "communication link failure" in lower_error or "timeout expired" in lower_error:
                 # Covers inability to reach the server
                 status_code = 504 # Gateway Timeout (or Service Unavailable 503 might fit too)
             elif "openai" in lower_error or "ai assistant" in lower_error or "ai returned" in lower_error:
                 # Covers issues with the prompt or the OpenAI service itself
                 status_code = 400 # Bad request (if prompt issue) or 503 (if OpenAI service issue)
                 if "openai" in lower_error and ("error" in lower_error or "timeout" in lower_error or "limit" in lower_error):
                     status_code = 503 # Service unavailable
             elif "no tables found" in lower_error:
                 # DB exists but is empty
                 status_code = 404 # Treat as 'Not Found' in terms of usable schema data

             print(f"Returning HTTP {status_code} due to error: {error_message}")
             raise HTTPException(status_code=status_code, detail=error_message)

        elif generated_sql:
            # Success case
            print(f"Successfully generated SQL for DB '{request.db_name}'.")
            return schemas.GeneratedSqlResponse(generated_sql=generated_sql)
        else:
             # Fallback for unknown failure within the logic function
             print(f"Unknown failure in generate_sql_from_prompt_logic for DB '{request.db_name}' after schema retrieval (SQL was None, Error was None).")
             raise HTTPException(status_code=500, detail="SQL generation failed for an unknown reason after schema retrieval.")

    except HTTPException as http_exc:
         # Re-raise HTTPException to let FastAPI handle it
         raise http_exc
    except Exception as e:
        # Catch any unexpected errors during request processing
        print(f"Unexpected error in /generate-sql endpoint: {e}")
        print(traceback.format_exc()) # Log the full traceback
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "AI SQL Generator API (MSSQL) is running. Use the /generate-sql endpoint."}

# Optional simplified health check
@app.get("/health", tags=["Utilities"], status_code=200)
async def health_check():
    """Checks if the API configuration is loaded."""
    # Basic check: Does the config object exist and have essential keys?
    try:
        # Check for essential config independent of auth method
        if config.settings and config.settings.OPENAI_API_KEY and config.settings.DB_HOST:
             auth_method = "Windows Authentication" if config.settings.DB_USE_WINDOWS_AUTH else "SQL Authentication"
             return {"status": "ok", "message": f"Configuration loaded. Auth Method: {auth_method}."}
        else:
             # Raise exception if basic config seems missing
             raise HTTPException(status_code=503, detail="Health check failed: Essential configuration keys missing (DB_HOST, OPENAI_API_KEY).")
    except Exception as e:
        # Catch potential errors accessing config
        print(f"Health check configuration access error: {e}")
        raise HTTPException(status_code=503, detail=f"Health check failed: Configuration error - {e}")