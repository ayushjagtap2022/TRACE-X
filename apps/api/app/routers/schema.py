from fastapi import APIRouter
from app.db.session import get_db

router = APIRouter()

@router.post("/schema/setup", tags=["schema"])
def setup_schema():
    """
    Set up Neo4j schema with constraints and indexes.
    This endpoint should be called once during initial setup.
    """
    driver = get_db()
    with driver.session() as session:
        # Account constraints
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE")
        
        # Transaction constraints
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (t:Transaction) REQUIRE t.txn_id IS UNIQUE")

        # Alert constraints
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (al:Alert) REQUIRE al.alert_id IS UNIQUE")

    return {"message": "Neo4j schema setup complete."}
