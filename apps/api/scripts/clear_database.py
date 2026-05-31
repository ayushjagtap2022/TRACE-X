import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import get_db

def clear_database():
    """
    Connects to the Neo4j database and deletes all nodes and relationships.
    """
    driver = None
    try:
        driver = get_db()
        with driver.session() as session:
            print("Connecting to the database to clear all data...")
            # The DETACH DELETE clause deletes nodes and any relationships connected to them
            session.run("MATCH (n) DETACH DELETE n")
            print("Successfully cleared all data from the database.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if driver is not None:
            driver.close()
            print("Database connection closed.")

if __name__ == "__main__":
    clear_database()
