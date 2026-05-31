import os
import sys
import random
import argparse
import networkx as nx
import matplotlib.pyplot as plt

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import get_db

def get_random_alert_by_pattern(session, pattern):
    """Fetches a random alert ID for a given pattern."""
    query = """
    MATCH (al:Alert {pattern: $pattern})
    RETURN al.alert_id
    """
    results = session.run(query, pattern=pattern)
    alert_ids = [record["al.alert_id"] for record in results]
    return random.choice(alert_ids) if alert_ids else None

def get_alert_subgraph(session, alert_id):
    """Fetches all accounts and transactions associated with a given alert."""
    query = """
    MATCH (al:Alert {alert_id: $alert_id})<-[:FLAGGED_IN]-(a:Account)
    WITH collect(a) AS accounts
    UNWIND accounts AS sender
    UNWIND accounts AS receiver
    MATCH (sender)-[r:TRANSFERRED_TO]->(receiver)
    RETURN sender.account_id AS sender_id, receiver.account_id AS receiver_id, r.amount AS amount
    """
    results = session.run(query, alert_id=alert_id)
    
    nodes = set()
    edges = []
    for record in results:
        sender = record["sender_id"]
        receiver = record["receiver_id"]
        nodes.add(sender)
        nodes.add(receiver)
        edges.append((sender, receiver, record["amount"]))
        
    return list(nodes), edges

def visualize_graph(nodes, edges, pattern, alert_id):
    """Draws and displays the graph using networkx and matplotlib."""
    G = nx.DiGraph()

    for node in nodes:
        G.add_node(node)

    for sender, receiver, amount in edges:
        G.add_edge(sender, receiver, weight=amount)

    pos = nx.spring_layout(G, k=1.5, iterations=50)
    
    plt.figure(figsize=(16, 12))
    
    nx.draw_networkx_nodes(G, pos, node_size=2000, node_color='lightblue', alpha=0.9)
    nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5, edge_color='gray', arrows=True, arrowstyle='->', arrowsize=20)
    
    labels = {node: f"\\n{node[-6:]}" for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, font_color='black')
    
    edge_labels = {(u, v): f"₹{d['weight']:,}" for u, v, d in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7, font_color='red')

    plt.title(f"Visualization for {pattern} Alert: {alert_id}", fontsize=16)
    plt.axis('off')
    plt.show()

def main():
    parser = argparse.ArgumentParser(description="Visualize fraud patterns from the Neo4j database.")
    parser.add_argument(
        "--pattern",
        type=str,
        required=True,
        choices=["LAYERING", "SMURFING", "DORMANCY"],
        help="The type of fraud pattern to visualize."
    )
    args = parser.parse_args()

    driver = get_db()
    with driver.session() as session:
        print(f"Searching for a random '{args.pattern}' alert to visualize...")
        alert_id = get_random_alert_by_pattern(session, args.pattern)

        if not alert_id:
            print(f"No alerts found for pattern '{args.pattern}'. Please generate data first.")
            return

        print(f"Found alert: {alert_id}. Fetching subgraph...")
        nodes, edges = get_alert_subgraph(session, alert_id)

        if not edges:
            print("Found alert, but it has no associated transactions to visualize.")
            return
            
        print(f"Visualizing graph with {len(nodes)} accounts and {len(edges)} transactions...")
        visualize_graph(nodes, edges, args.pattern, alert_id)

    driver.close()

if __name__ == "__main__":
    main()
