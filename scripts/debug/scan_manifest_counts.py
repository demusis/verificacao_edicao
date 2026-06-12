import os
from pathlib import Path
import json

root = Path(r"G:\Meu Drive\Em processamento")
results = []

for m_path in root.rglob("batch_manifest.json"):
    try:
        with open(m_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        count = len(manifest)
        results.append((count, str(m_path)))
    except:
        pass

# Sort by count (descending)
results.sort(key=lambda x: x[0], reverse=True)

for count, path in results[:10]:
    print(f"COUNT {count}: {path}")
