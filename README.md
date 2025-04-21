# Natural Language to SQL Query Generator API

A simple backend API service that takes a natural language prompt and a target database name, and attempts to generate the corresponding SQL query.

## Overview

This project provides a backend API endpoint designed to translate natural language questions or commands related to database information into executable SQL queries. 

**Example Use Case:** Given the prompt "show the schema of dbo.spt_fallback_db table" for the "master" database, the API might return a query like `SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'spt_fallback_db'`.

## Features

*   Accepts natural language prompts via a JSON API.
*   Requires specifying the target database name.
*   Returns the generated SQL query in a JSON response.
*   Simple to integrate with frontend applications or testing tools like Postman.

## Usage

1.  **Run the API Server:**
    *(Replace `python app.py` with the actual command to start your server, e.g., `flask run`, `uvicorn main:app --reload`)*
    ```bash
    python app.py
    ```
    or run it using
    ```bash
    uvicorn main:app --reload
    ```

    The server should now be running, typically on `http://127.0.0.1:8000` or `http://127.0.0.1:5000`. Check the console output.

1.  **Send Requests to the API:**
    Use a tool like `curl` or Postman to send `POST` requests to the `/generate-sql` endpoint (or your actual endpoint path).

    *   **Endpoint:** `POST /generate-sql`
    *   **Headers:** `Content-Type: application/json`
    *   **Request Body (raw JSON):**
        ```json
        {
          "db_name": "your_database_name",
          "prompt": "your natural language prompt about the database"
        }
        ```

    *   **Example using `curl`:**
        ```bash
        curl -X POST http://127.0.0.1:8000/generate-sql \
        -H "Content-Type: application/json" \
        -d '{
              "db_name": "master",
              "prompt": "show the schema of dbo.spt_fallback_db table"
            }'
        ```

    *   **Example Success Response (JSON):**
        ```json
        {
          "generated_sql": "SELECT COLUMN_NAME, DATA_TYPE\nFROM INFORMATION_SCHEMA.COLUMNS\nWHERE TABLE_NAME = 'spt_fallback_db'"
        }
        ```
        *(Note: The response formatting, like including `\n`, depends on your API implementation.)*

    *   **Example Error Response (JSON):**
        ```json
        {
          "error": "Description of the error that occurred"
        }
        ```

## Important Considerations / Disclaimer

*   **Accuracy:** The generated SQL is based on the interpretation of the natural language prompt and the underlying model/logic. **Always review generated SQL queries** for correctness and potential side effects before executing them against a database, especially in production environments.
*   **Security:** Be extremely cautious about executing generated SQL, especially if the prompts can be influenced by untrusted user input. Generated queries might be syntactically valid but functionally harmful (e.g., unintended data modifications or deletions). Implement safeguards and validation.
*   **Formatting:** As seen in the examples, the API might return SQL with formatting characters like `\n`. Ensure your client application handles or cleans these appropriately before execution or display.

## Technology Stack (Example)

*   **Backend Framework:** [e.g., Flask, FastAPI, Django]
*   **Language:** Python
*   **Core Logic:** [e.g., OpenAI API, Custom NLP Model, LangChain, Specific Libraries]
  


