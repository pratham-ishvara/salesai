# backend/core/ai_sql_generator.py
import pyodbc # Keep using pyodbc
import openai
from typing import Tuple, Optional, List, Dict, Any
import traceback

# Import config and the updated connection string helper
from .config import settings, get_mssql_connection_string

# --- Database Schema Fetching Logic ---

def _get_db_schema_context(db_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Connects directly to fetch schema context for a given MSSQL DB using
    connection settings from config (handles Windows Auth or SQL Auth).
    Returns (schema_string|None, error_message|None)
    """
    conn = None
    cursor = None
    try:
        # Get the connection string (handles Win Auth vs SQL Auth automatically)
        connection_string = get_mssql_connection_string(db_name=db_name)
        print(f"Attempting connection to DB '{db_name}'...") # Log connection attempt

        # Establish a direct connection using pyodbc
        # Autocommit True often simpler for read-only ops
        conn = pyodbc.connect(connection_string, autocommit=True)
        cursor = conn.cursor()
        print(f"Connection to DB '{db_name}' successful.") # Log success

        # Get tables (using INFORMATION_SCHEMA for MSSQL)
        table_query = """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_CATALOG = ?
            ORDER BY TABLE_NAME;
        """
        cursor.execute(table_query, db_name)
        tables_result = cursor.fetchall()

        if not tables_result:
            # Check if the database exists but is empty vs. database doesn't exist
            # Try connecting without specifying the database to check server reachability
            try:
                # Use 'master' or omit db_name depending on server setup for existence check
                master_conn_str = get_mssql_connection_string(db_name=None) # Connect without specific DB
                temp_conn = pyodbc.connect(master_conn_str, autocommit=True)
                temp_cursor = temp_conn.cursor()
                # Check if the specific DB exists
                temp_cursor.execute("SELECT name FROM sys.databases WHERE name = ?", db_name)
                db_exists = temp_cursor.fetchone()
                temp_cursor.close()
                temp_conn.close()
                if db_exists:
                     return None, f"Database '{db_name}' exists but contains no tables."
                else:
                     # Should be caught by initial connection error, but double-check.
                     return None, f"Database '{db_name}' not found."
            except pyodbc.Error as check_err:
                 print(f"Error checking DB existence (may be expected if initial connect failed): {check_err}")
                 # Fall through to return the original error from connecting to db_name
            # Default if existence check fails or logic doesn't catch specific case
            return None, f"No tables found in database '{db_name}' or database inaccessible."


        tables = [row.TABLE_NAME for row in tables_result] # Access column by name

        # Get columns for each table (using INFORMATION_SCHEMA for MSSQL)
        schema_context = f"Database: [{db_name}]\n\nTables Schema:\n"
        table_schemas = []
        all_retrieved = True

        column_query = """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_CATALOG = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION;
        """

        for table_name in tables:
            try:
                # Use parameter binding for safety
                cursor.execute(column_query, db_name, table_name)
                columns = cursor.fetchall()
                col_details = []
                for col in columns:
                    # Construct details, using [] for quoting
                    detail = f"  - [{col.COLUMN_NAME}] ({col.DATA_TYPE}"
                    if col.IS_NULLABLE == 'NO':
                        detail += " NOT NULL"
                    if col.COLUMN_DEFAULT is not None:
                        detail += f" DEFAULT {col.COLUMN_DEFAULT}"
                    detail += ")"
                    col_details.append(detail)

                table_schemas.append(f"Table: [{table_name}]\nColumns:\n" + "\n".join(col_details))
            except pyodbc.Error as desc_err:
                print(f"Error describing table {db_name}.{table_name}: {desc_err}")
                table_schemas.append(f"Table: [{table_name}]\n  - Error: Could not retrieve schema details.\n")
                all_retrieved = False

        if not all_retrieved:
             schema_context += "***Warning: Failed schema retrieval for some tables.***\n\n"
        schema_context += "\n\n".join(table_schemas)
        return schema_context.strip(), None # Success

    except pyodbc.Error as err:
        # pyodbc errors often have SQLSTATE and native error codes
        sqlstate = getattr(err, 'sqlstate', 'N/A')
        # Error message often contains useful details like [Microsoft][ODBC Driver...]
        error_msg_detail = str(err)
        error_msg = f"Database connection/query error for '{db_name}' (SQLSTATE: {sqlstate}): {error_msg_detail}"

        # Specific checks for common MSSQL connection/access errors
        # 08001: Connectivity issues (server down, firewall, network)
        # 28000: Login failed (SQL Auth specific usually, but can indicate Windows user mapping issues)
        # 42000/42S02: Permissions, object not found (DB, Table), bad syntax
        if sqlstate in ('08001', 'HYT00') or 'Login timeout expired' in error_msg_detail or 'Communication link failure' in error_msg_detail or 'TCP Provider' in error_msg_detail or 'Named Pipes Provider' in error_msg_detail:
             # Added HYT00 for timeout
             error_msg = f"Network error connecting to SQL Server '{settings.DB_HOST}'. Check server status, firewall, and network configuration."
        elif sqlstate == '28000' or 'Login failed' in error_msg_detail:
             # This might indicate the Windows user lacks login rights on the SQL Server instance itself, or SQL Auth was attempted incorrectly.
             auth_type = "Windows user" if settings.DB_USE_WINDOWS_AUTH else f"SQL user '{settings.DB_USER}'"
             error_msg = f"Authentication error connecting to SQL Server '{settings.DB_HOST}'. Verify the {auth_type} has login permissions on the server."
        elif sqlstate in ('42000', '42S02') or 'Cannot open database' in error_msg_detail or 'Invalid object name' in error_msg_detail:
             # Could be DB doesn't exist, user lacks permission on DB/Table, or table name is wrong.
             auth_type = "Windows user running the application" if settings.DB_USE_WINDOWS_AUTH else f"SQL user '{settings.DB_USER}'"
             error_msg = f"Database '{db_name}' not found, inaccessible, or the {auth_type} lacks permissions. Check DB name and permissions."

        print(f"ERROR during DB schema fetch: {error_msg}") # Log concise error
        print(f"Full pyodbc error details: {traceback.format_exc()}") # Log full traceback for debugging
        return None, error_msg # Return the concise, user-friendlier message
    except Exception as e:
        error_msg = f"Unexpected error fetching schema: {e}"
        print(error_msg)
        print(traceback.format_exc())
        return None, error_msg
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            print(f"Connection to DB '{db_name}' closed.") # Log close

# --- OpenAI SQL Generation Logic ---

def generate_sql_from_prompt_logic(db_name: str, prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Orchestrates schema fetching (using configured auth) and OpenAI call.
    Returns: (generated_sql|None, error_message|None)
    """
    if not settings.OPENAI_API_KEY:
        return None, "OpenAI API key not configured on the server."

    # 1. Get Schema Context (uses the updated _get_db_schema_context)
    print(f"Fetching schema for database: {db_name}")
    schema_context, schema_error = _get_db_schema_context(db_name)
    if schema_error:
        print(f"Schema fetching failed for {db_name}: {schema_error}")
        return None, schema_error # Return schema fetching error
    if not schema_context:
         print(f"Schema context empty for {db_name} after attempting retrieval.")
         return None, f"Failed to retrieve schema context for database '{db_name}'. It might be empty or inaccessible."
    print(f"Schema retrieved successfully for {db_name}.")

    # 2. Call OpenAI
    try:
        print(f"Calling OpenAI API for prompt: '{prompt}'")
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        system_prompt = f"""You are an expert SQL assistant translating natural language to Microsoft SQL Server (T-SQL) queries.
Given the database schema below, generate a *single*, valid T-SQL query that accurately answers the user's request.
Output *only* the SQL query, with no explanations, comments, markdown formatting, or introductory text.
Use square brackets ([]) around table and column names if they contain spaces or reserved keywords, otherwise they are optional but recommended for clarity.
Pay close attention to data types in the schema for proper quoting (use single quotes ' for strings/dates) in WHERE clauses. If schema info is missing/incomplete, state that.

Database Schema Context:
---
{schema_context}
---
User Request:"""
        model = "gpt-3.5-turbo" # Or "gpt-4" etc.

        response = client.chat.completions.create(
            model=model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=700, top_p=1.0
        )
        generated_sql = response.choices[0].message.content.strip()
        print("OpenAI response received.")

        # Clean and basic validate
        cleaned_sql = generated_sql
        if cleaned_sql.startswith("```sql"): cleaned_sql = cleaned_sql[6:].strip()
        elif cleaned_sql.startswith("```"): cleaned_sql = cleaned_sql[3:].strip()
        if cleaned_sql.endswith("```"): cleaned_sql = cleaned_sql[:-3].strip()
        cleaned_sql = cleaned_sql.rstrip(';') # Remove trailing semicolon if present

        # Check if the generated output looks like SQL
        sql_starts = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "EXEC", "DECLARE"]
        if not any(cleaned_sql.upper().startswith(start) for start in sql_starts):
             if "cannot generate" in cleaned_sql.lower() or "missing schema" in cleaned_sql.lower() or "error retrieving schema" in cleaned_sql.lower():
                 # Return the AI's explanation as the "error"
                 print(f"AI indicated generation issue: {cleaned_sql}")
                 return None, f"AI Assistant: {cleaned_sql}"
             else:
                 print(f"Warning: AI returned content not starting with expected keywords: {cleaned_sql}")
                 # Pass through for now, but log it.

        print(f"Generated SQL: {cleaned_sql}")
        return cleaned_sql, None # Success

    # Handle OpenAI specific errors
    except openai.AuthenticationError: error_msg = "OpenAI Authentication Error (Server Side)"
    except openai.RateLimitError: error_msg = "OpenAI Rate Limit Error (Server Side)"
    except openai.APIConnectionError as e: error_msg = f"OpenAI Connection Error: {e}"
    except openai.APITimeoutError: error_msg = "OpenAI Timeout Error"
    except openai.APIError as e: error_msg = f"OpenAI API Error: {e}"
    # Handle other potential errors
    except Exception as e: error_msg = f"Unexpected error during AI call: {e}"; print(traceback.format_exc())

    print(f"SQL Generation Error: {error_msg}") # Log server-side
    return None, error_msg