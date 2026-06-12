import os
import json
from pathlib import Path

def find_files():
    root = os.getcwd() # g:\Meu Drive\Em processamento\verificacao_edicao
    print(f"Searching in {root}...")
    
    found_debug = []
    found_analysis = []
    
    for r, d, f in os.walk(root):
        for file in f:
            if file == "debug_report_data.json":
                found_debug.append(os.path.join(r, file))
            elif file.endswith("_file_analysis.json"):
                found_analysis.append(os.path.join(r, file))
                
    print(f"\nFound {len(found_debug)} debug_report_data.json files:")
    for p in found_debug:
        print(f" - {p}")
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
                files = data.get('files', [])
                if files:
                    print(f"   Files in report: {len(files)}")
                    print(f"   First file: {files[0].get('filename')}")
                    fmt = files[0].get('analyses', {}).get('file_analysis', {}).get('metadata', {}).get('format', {})
                    print(f"   Format Keys: {list(fmt.keys())}")
        except Exception as e:
            print(f"   Error reading: {e}")

    print(f"\nFound {len(found_analysis)} file_analysis.json files (showing top 3 newest):")
    # Sort by mtime
    found_analysis.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    for p in found_analysis[:3]:
        print(f" - {p}")
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
                fmt = data.get('metadata', {}).get('format', {})
                print(f"   Format content present: {bool(fmt)}")
                print(f"   Duration: {fmt.get('duration')}")
        except Exception as e:
            print(f"   Error reading: {e}")

if __name__ == "__main__":
    find_files()
