import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.db.session import get_db

d = get_db()
s = d.session()

# Check all alerts
q = "MATCH (a:Account)-[:FLAGGED_IN]->(al:Alert) RETURN al.pattern AS pattern, a.account_id AS acc, a.fraud_score AS fs, al.fraud_prob AS fp LIMIT 20"
r = s.run(q)
rows = [dict(x) for x in r]
print("Sample FLAGGED_IN rows:")
for row in rows:
    print(" ", row)

# Counts by pattern
q2 = "MATCH (a:Account)-[:FLAGGED_IN]->(al:Alert) RETURN al.pattern AS pattern, count(*) AS cnt"
r2 = s.run(q2)
print("\nCounts:")
for row in r2:
    print(" ", dict(row))
