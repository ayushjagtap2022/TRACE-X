from neo4j import GraphDatabase
from app.core.config import settings

class Neo4j:
    def __init__(self):
        self.driver = None

    def connect(self):
        try:
            self.driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            print("Successfully connected to Neo4j.")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")

    def close(self):
        if self.driver is not None:
            self.driver.close()
            print("Neo4j connection closed.")

db = Neo4j()

def get_db():
    if db.driver is None:
        db.connect()
    return db.driver
