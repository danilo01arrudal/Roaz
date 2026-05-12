import yaml

with open("configs/expert_rules.yaml") as f:
    rules = yaml.safe_load(f)

def route(query: str) -> list[str]:
    query_lower = query.lower()
    active = []
    for expert, keywords in rules.items():
        if any(kw in query_lower for kw in keywords):
            active.append(expert)
    if not active:
        active = list(rules.keys())  # fallback: todos
    return active
