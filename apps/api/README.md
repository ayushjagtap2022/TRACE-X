# TRACE-X Platform API

This directory contains the backend for the TRACE-X platform, built with FastAPI.

## Development Setup

### Prerequisites

- Python 3.9+
- An active Neo4j instance (AuraDB or local)

### Installation

1.  **Create a virtual environment:**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

2.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure environment variables:**

    Create a `.env` file in the `apps/api` directory and add the following, replacing the placeholder values with your Neo4j credentials:

    ```env
    NEO4J_URI="neo4j+s://your-aura-instance.databases.neo4j.io"
    NEO4J_USER="neo4j"
    NEO4J_PASSWORD="your_aura_password"
    ```

### Running the Application

1.  **Start the FastAPI server:**

    To start the FastAPI server, run the following command from the `apps/api` directory:

    ```bash
    uvicorn app.main:app --reload
    ```

    The API will be available at `http://127.0.0.1:8000`, and the interactive documentation can be accessed at `http://127.0.0.1:8000/docs`.

2.  **Set up the database schema:**

    Once the server is running, you need to set up the database schema. This only needs to be done once.

    -   Open your browser and go to the API documentation at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
    -   Find the `/api/v1/schema/setup` endpoint, expand it, and click "Try it out".
    -   Click "Execute". This will create the necessary constraints and indexes in your Neo4j database.

3.  **Generate synthetic data (Optional):**

    To populate your database with sample data for development, run the data generation script.

    -   Stop the `uvicorn` server (if it's running) by pressing `Ctrl+C`.
    -   Run the script from the `apps/api` directory (make sure your virtual environment is active):

    ```bash
    python scripts/generate_data.py
    ```

4.  **Clear the database (Optional):**

    To delete all data from your database, you can run the `clear_database.py` script.

    ```bash
    python scripts/clear_database.py
    ```
    
    -   After the script finishes, you can restart the server.

## Project Structure

-   `app/`: Main application folder.
-   `routers/`: API endpoint definitions (routers).
    -   `core/`: Application configuration and settings.
    -   `db/`: Database connection and session management.
-   Shared schemas live in `packages/py-schemas` as `trace_x_schemas`.
-   `main.py`: FastAPI application entry point.
-   `requirements.txt`: Python dependencies.
-   `scripts/`: Standalone scripts (e.g., for data generation).
