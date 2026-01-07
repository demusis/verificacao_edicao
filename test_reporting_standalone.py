import sys
import os
import json
from pathlib import Path

# Add project root
sys.path.append(os.getcwd())

from modules.reporting import ReportingModule

# Mock classes
class MockLogger:
    def log(self, event, data=None):
        pass # Silence logs

class MockCaseManager:
    def __init__(self, results_path):
        self.results_dir = results_path
        self.report_dir = results_path / "report"
        self.report_dir.mkdir(exist_ok=True)
        self.case_name = "Debug Case"
        
    def get_logger(self):
        return MockLogger()

def run_test():
    # 1. Setup paths
    base_dir = Path("debug_results")
    
    # 2. Create a fake batch_manifest.json to mimic the real execution
    manifest = [
        {
            "filename": "debug_movie.mov",
            "type": "video",
            "analysis_files": {
                "file_analysis": "debug_file_analysis.json"
            }
        }
    ]
    
    with open(base_dir / "batch_manifest.json", 'w', encoding='utf-8') as f:
        json.dump(manifest, f)
        
    # 3. Run Reporting
    cm = MockCaseManager(base_dir)
    reporter = ReportingModule(cm)
    
    # Generate data
    data = reporter._collect_data()
    print(f"Collected Data Keys for file 0: {data['files'][0]['analyses']['file_analysis'].keys()}")
    
    # Generate LaTeX
    latex = reporter._generate_latex_source(data)
    
    # 4. Inspect the LaTeX for the Format Table
    print("\n--- Inspecting LaTeX for Format Table ---")
    start_marker = r"\subsection{Metadados do Arquivo}"
    end_marker = r"\subsection{Fluxos de Mídia (Streams)}"
    
    if start_marker in latex:
        start_idx = latex.find(start_marker)
        end_idx = latex.find(end_marker)
        snippet = latex[start_idx:end_idx]
        print(snippet[:1000]) # Print first 1000 chars of the section
    else:
        print("SECTION NOT FOUND IN LATEX!")

if __name__ == "__main__":
    run_test()
