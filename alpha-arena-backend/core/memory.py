import json, os
LOG = "db/thoughts.json"

def load_thoughts():
    if not os.path.exists(LOG):
        return {}
    with open(LOG, "r") as f:
        return json.load(f)

def save_thought(symbol, thought):
    data = load_thoughts()
    data[symbol] = thought
    with open(LOG, "w") as f:
        json.dump(data, f, indent=2)

# New function to get recent decision for a symbol
def get_recent_decision(symbol):
    """Get the most recent decision for a symbol"""
    thoughts = load_thoughts()
    return thoughts.get(symbol, {})