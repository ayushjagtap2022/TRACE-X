import random
from datetime import datetime, timedelta
from faker import Faker
import os
import sys
from tqdm import tqdm

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import get_db

fake = Faker()

# --- Configuration ---
# Reduced scale for faster generation and snappy Neo4j Aura demo
NUM_ACCOUNTS = 1000
NUM_CLEAN_TRANSACTIONS = 5000
NUM_LAYERING_CHAINS = 20
NUM_SMURFING_CLUSTERS = 20
NUM_DORMANCY_ACTIVATIONS = 20
NUM_ROUND_TRIPS = 20
NUM_KYC_MISMATCHES = 20

def setup_schema(session):
    """Creates constraints and indexes for the graph schema."""
    print("Setting up schema constraints and indexes...")
    
    # Constraints ensure uniqueness
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (t:Transaction) REQUIRE t.txn_id IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (al:Alert) REQUIRE al.alert_id IS UNIQUE")

    # Indexes speed up lookups
    session.run("CREATE INDEX IF NOT EXISTS FOR (a:Account) ON (a.entity_id)")
    session.run("CREATE INDEX IF NOT EXISTS FOR (a:Account) ON (a.is_fraud)")
    session.run("CREATE INDEX IF NOT EXISTS FOR (t:Transaction) ON (t.sender_id)")
    session.run("CREATE INDEX IF NOT EXISTS FOR (t:Transaction) ON (t.receiver_id)")
    session.run("CREATE INDEX IF NOT EXISTS FOR (t:Transaction) ON (t.txn_ts)")
    
    print("Schema setup complete.")


def create_account(session, entity_id, risk_category, kyc_tier, is_fraud=False, status='ACTIVE', opened_on=None, declared_annual_income=None):
    """Creates a single account with specific characteristics."""
    account_id = f"ACC_{fake.uuid4().replace('-', '')[:12]}"
    
    query = """
    CREATE (a:Account {
        account_id: $account_id,
        entity_id: $entity_id,
        account_type: $account_type,
        kyc_tier: $kyc_tier,
        status: $status,
        opened_on: $opened_on,
        risk_category: $risk_category,
        is_fraud: $is_fraud,
        declared_annual_income: $declared_annual_income,
        
        // Initialize behavioral metrics
        txn_count_7d: 0,
        txn_count_30d: 0,
        volume_7d: 0.0,
        volume_30d: 0.0,
        avg_monthly_volume: 0.0,
        avg_monthly_count: 0.0,
        unique_counterparties_30d: 0,
        last_active_ts: null,
        dormancy_days: $dormancy_days,
        fraud_score: 0.0,
        last_scored_ts: null
    })
    RETURN a.account_id
    """
    
    open_date = opened_on if opened_on else fake.date_between(start_date="-5y", end_date="today")
    dormancy = (datetime.now().date() - open_date).days if status == 'ACTIVE' else 0
    
    # Default to a reasonable income if not provided
    if declared_annual_income is None:
        declared_annual_income = random.uniform(300000, 2000000)

    result = session.run(query, {
        "account_id": account_id,
        "entity_id": entity_id,
        "account_type": random.choice(["SAVINGS", "CURRENT", "WALLET"]),
        "kyc_tier": kyc_tier,
        "status": status,
        "opened_on": open_date,
        "risk_category": risk_category,
        "is_fraud": is_fraud,
        "dormancy_days": dormancy,
        "declared_annual_income": declared_annual_income
    })
    return result.single()[0]

def create_transaction(session, sender_id, receiver_id, amount, channel, txn_ts, narration=""):
    """Creates a single transaction and updates account metrics."""
    txn_id = f"TXN_{fake.uuid4().replace('-', '')[:12]}"
    
    query = """
    // Find sender and receiver
    MATCH (sender:Account {account_id: $sender_id})
    MATCH (receiver:Account {account_id: $receiver_id})

    // Create the Transaction node
    CREATE (t:Transaction {
        txn_id: $txn_id,
        sender_id: $sender_id,
        receiver_id: $receiver_id,
        amount: $amount,
        channel: $channel,
        txn_ts: $txn_ts,
        status: 'SUCCESS',
        narration: $narration
    })

    // Create the SENT relationship (used by fraud_detector.py)
    CREATE (sender)-[r:SENT {
        txn_id: $txn_id,
        amount: $amount,
        channel: $channel,
        txn_ts: $txn_ts,
        status: 'SUCCESS'
    }]->(receiver)

    // Update metrics for both sender and receiver
    SET sender.last_active_ts = $txn_ts,
        receiver.last_active_ts = $txn_ts,
        sender.dormancy_days = 0,
        receiver.dormancy_days = 0,
        
        sender.txn_count_30d = sender.txn_count_30d + 1,
        sender.volume_30d = sender.volume_30d + $amount,
        sender.txn_count_7d = CASE WHEN $is_in_7d THEN sender.txn_count_7d + 1 ELSE sender.txn_count_7d END,
        sender.volume_7d = CASE WHEN $is_in_7d THEN sender.volume_7d + $amount ELSE sender.volume_7d END,

        receiver.txn_count_30d = receiver.txn_count_30d + 1,
        receiver.volume_30d = receiver.volume_30d + $amount,
        receiver.txn_count_7d = CASE WHEN $is_in_7d THEN receiver.txn_count_7d + 1 ELSE receiver.txn_count_7d END,
        receiver.volume_7d = CASE WHEN $is_in_7d THEN receiver.volume_7d + $amount ELSE receiver.volume_7d END
    """
    
    is_in_7d = (datetime.now() - txn_ts).days <= 7
    
    session.run(query, {
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "txn_id": txn_id,
        "amount": amount,
        "channel": channel,
        "txn_ts": txn_ts,
        "narration": narration,
        "is_in_7d": is_in_7d
    })

def create_alert(session, pattern, accounts, total_amount, hop_depth=0, time_window_hrs=0):
    """Creates a single alert linked to multiple accounts."""
    alert_id = f"ALT_{fake.uuid4().replace('-', '')[:12]}"
    
    # Create the Alert node
    alert_query = """
    CREATE (al:Alert {
        alert_id: $alert_id,
        alert_ts: $alert_ts,
        model: 'SYNTHETIC',
        pattern: $pattern,
        fraud_prob: 1.0,
        tier: 'CRITICAL',
        total_amount: $total_amount,
        hop_depth: $hop_depth,
        time_window_hrs: $time_window_hrs,
        status: 'NEW'
    })
    RETURN al.alert_id
    """
    session.run(alert_query, {
        "alert_id": alert_id,
        "alert_ts": datetime.now(),
        "pattern": pattern,
        "total_amount": total_amount,
        "hop_depth": hop_depth,
        "time_window_hrs": time_window_hrs
    })

    # Link the alert to all involved accounts
    link_query = """
    MATCH (a:Account) WHERE a.account_id IN $account_ids
    MATCH (al:Alert {alert_id: $alert_id})
    CREATE (a)-[:FLAGGED_IN {role: 'PARTICIPANT'}]->(al)
    """
    session.run(link_query, {"account_ids": accounts, "alert_id": alert_id})


def create_layering_chain(session, chain_length=5):
    """Creates a multi-hop layering chain."""
    entity_id = f"ENT_{fake.uuid4().replace('-', '')[:8]}"
    accounts = [create_account(session, entity_id, 'HIGH', 1, is_fraud=True) for _ in range(chain_length)]
    
    total_amount = 0
    start_amount = random.uniform(500000, 2000000)
    
    for i in range(chain_length - 1):
        sender = accounts[i]
        receiver = accounts[i+1]
        
        # Amount slightly decreases at each hop
        amount = start_amount * (1 - (i * 0.05)) 
        amount = round(amount, 2)
        total_amount += amount
        
        txn_ts = datetime.now() - timedelta(hours=chain_length - i)
        
        create_transaction(session, sender, receiver, amount, "NEFT", txn_ts, "Fund Transfer")

    create_alert(session, "LAYERING", accounts, total_amount, hop_depth=chain_length, time_window_hrs=chain_length)
    return accounts

def create_smurfing_cluster(session, num_smurfs=10):
    """Creates a smurfing cluster converging on a hub account."""
    hub_entity = f"ENT_{fake.uuid4().replace('-', '')[:8]}"
    hub_account = create_account(session, hub_entity, 'HIGH', 1, is_fraud=True)
    
    smurf_accounts = []
    for _ in range(num_smurfs):
        smurf_entity = f"ENT_{fake.uuid4().replace('-', '')[:8]}"
        smurf_accounts.append(create_account(session, smurf_entity, 'MEDIUM', 1, is_fraud=True))
        
    total_amount = 0
    time_window_hrs = 24
    
    for smurf in smurf_accounts:
        # Multiple small transactions from each smurf
        for _ in range(random.randint(2, 5)):
            amount = random.uniform(10000, 49000) # Below reporting thresholds
            total_amount += amount
            txn_ts = datetime.now() - timedelta(hours=random.uniform(1, time_window_hrs))
            create_transaction(session, smurf, hub_account, amount, "IMPS", txn_ts, "Deposit")
            
    all_involved = smurf_accounts + [hub_account]
    create_alert(session, "SMURFING", all_involved, total_amount, time_window_hrs=time_window_hrs)
    return all_involved

def create_dormancy_activation(session):
    """Creates a dormant account that suddenly becomes active."""
    entity_id = f"ENT_{fake.uuid4().replace('-', '')[:8]}"
    dormant_account = create_account(
        session, entity_id, 'HIGH', 0, is_fraud=True, status='DORMANT',
        opened_on=fake.date_between(start_date="-3y", end_date="-2y")
    )
    
    # Create a destination account for the funds
    dest_account = create_account(session, f"ENT_{fake.uuid4().replace('-', '')[:8]}", 'LOW', 2)
    
    total_amount = 0
    time_window_hrs = 12
    
    # Sudden burst of activity
    for _ in range(random.randint(5, 10)):
        amount = random.uniform(100000, 500000)
        total_amount += amount
        txn_ts = datetime.now() - timedelta(minutes=random.uniform(1, time_window_hrs * 60))
        create_transaction(session, dormant_account, dest_account, amount, "RTGS", txn_ts, "Urgent Payout")
        
    all_involved = [dormant_account, dest_account]
    create_alert(session, "DORMANCY", all_involved, total_amount, time_window_hrs=time_window_hrs)
    return all_involved

def create_roundtrip(session, cycle_length=4):
    """Creates a circular flow of funds where money returns to the origin."""
    entity_id = f"ENT_{fake.uuid4().replace('-', '')[:8]}"
    accounts = [create_account(session, entity_id, 'HIGH', 1, is_fraud=True) for _ in range(cycle_length)]
    
    total_amount = 0
    start_amount = random.uniform(500000, 2000000)
    time_window_hrs = cycle_length
    
    for i in range(cycle_length):
        sender = accounts[i]
        # The last account sends back to the first
        receiver = accounts[(i + 1) % cycle_length]
        
        # Keep amount very similar to simulate exact roundtrip
        amount = start_amount * random.uniform(0.98, 1.0)
        amount = round(amount, 2)
        total_amount += amount
        
        txn_ts = datetime.now() - timedelta(hours=cycle_length - i)
        
        create_transaction(session, sender, receiver, amount, "RTGS", txn_ts, "Investment/Return")

    create_alert(session, "ROUND_TRIP", accounts, total_amount, hop_depth=cycle_length, time_window_hrs=time_window_hrs)
    return accounts

def create_kyc_mismatch(session):
    """Creates an account with massive volume but very low declared income."""
    entity_id = f"ENT_{fake.uuid4().replace('-', '')[:8]}"
    
    # Very low declared income (e.g. student or low-income)
    declared_income = random.uniform(100_000, 300_000)
    
    mismatch_account = create_account(
        session, entity_id, 'HIGH', 1, is_fraud=True, 
        declared_annual_income=declared_income
    )
    
    # 30-day volume is over 10x the monthly expected income
    expected_monthly = declared_income / 12
    target_volume = expected_monthly * random.uniform(15, 30)
    
    total_amount = 0
    # Simulate high volume over the last 30 days
    dest_accounts = [create_account(session, f"ENT_{fake.uuid4().replace('-','')[:8]}", 'LOW', 2) for _ in range(3)]
    
    while total_amount < target_volume:
        amount = random.uniform(50000, 200000)
        total_amount += amount
        txn_ts = datetime.now() - timedelta(days=random.uniform(1, 28))
        receiver = random.choice(dest_accounts)
        create_transaction(session, mismatch_account, receiver, amount, "IMPS", txn_ts, "Business Transfer")
        
    create_alert(session, "KYC_MISMATCH", [mismatch_account], total_amount, time_window_hrs=24*30)
    return [mismatch_account]

def main():
    driver = get_db()
    with driver.session() as session:
        # 1. Clear existing data and set up schema
        print("Clearing existing data...")
        session.run("MATCH (n) DETACH DELETE n")
        setup_schema(session)

        # 2. Create personas: clean and fraudulent accounts
        print("Creating account personas...")
        clean_accounts = []
        fraud_accounts = []
        
        # Create a base of clean accounts
        for _ in tqdm(range(NUM_ACCOUNTS), desc="Creating Clean Accounts"):
            entity_id = f"ENT_{fake.uuid4().replace('-', '')[:8]}"
            risk = random.choice(['LOW'] * 7 + ['MEDIUM'] * 3) # 70% low, 30% medium
            kyc = random.choice([1, 2, 2, 2])
            clean_accounts.append(create_account(session, entity_id, risk, kyc))

        # 3. Generate structured fraud patterns
        print("\nGenerating structured fraud patterns...")
        for _ in tqdm(range(NUM_LAYERING_CHAINS), desc="Generating Layering Chains"):
            fraud_accounts.extend(create_layering_chain(session, random.randint(4, 8)))
            
        for _ in tqdm(range(NUM_SMURFING_CLUSTERS), desc="Generating Smurfing Clusters"):
            fraud_accounts.extend(create_smurfing_cluster(session, random.randint(8, 15)))

        for _ in tqdm(range(NUM_DORMANCY_ACTIVATIONS), desc="Generating Dormancy Activations"):
            fraud_accounts.extend(create_dormancy_activation(session))
            
        for _ in tqdm(range(NUM_ROUND_TRIPS), desc="Generating Round Trips"):
            fraud_accounts.extend(create_roundtrip(session, random.randint(3, 6)))
            
        for _ in tqdm(range(NUM_KYC_MISMATCHES), desc="Generating KYC Mismatches"):
            fraud_accounts.extend(create_kyc_mismatch(session))
            
        # 4. Generate clean, non-fraudulent transactions
        print("\nGenerating clean background transactions...")
        for _ in tqdm(range(NUM_CLEAN_TRANSACTIONS), desc="Generating Clean Transactions"):
            sender, receiver = random.sample(clean_accounts, 2)
            amount = random.uniform(100, 50000)
            channel = random.choice(["UPI", "IMPS", "NEFT"])
            txn_ts = datetime.now() - timedelta(days=random.randint(0, 365))
            create_transaction(session, sender, receiver, amount, channel, txn_ts, fake.sentence())

        # 5. Final summary
        print("\n--- Data Generation Summary ---")
        total_accounts = session.run("MATCH (a:Account) RETURN count(a) AS count").single()['count']
        total_txns = session.run("MATCH ()-[r:SENT]->() RETURN count(r) AS count").single()['count']
        total_alerts = session.run("MATCH (al:Alert) RETURN count(al) AS count").single()['count']
        
        print(f"Total Accounts Created: {total_accounts}")
        print(f"  - Clean Accounts: {len(clean_accounts)}")
        print(f"  - Fraud Accounts: {len(set(fraud_accounts))}")
        print(f"Total Transactions Created: {total_txns}")
        print(f"Total Alerts Created: {total_alerts}")
        print("\nSynthetic data generation complete.")

    driver.close()

if __name__ == "__main__":
    main()

