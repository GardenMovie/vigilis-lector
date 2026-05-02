
import os
import json
from dotenv import load_dotenv

load_dotenv()

MISSED_DIR = "missed"

def main():
    if not os.path.isdir(MISSED_DIR):
        print(f"No '{MISSED_DIR}' directory found.")
        return
    files = sorted(f for f in os.listdir(MISSED_DIR) if f.endswith('.json'))
    if not files:
        print("No missed metric files found.")
        return
    for fname in files:
        path = os.path.join(MISSED_DIR, fname)
        print(f"\n--- {fname} ---")
        with open(path, 'r') as f:
            data = json.load(f)
            print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
