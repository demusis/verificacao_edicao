import sys
import os
from pathlib import Path
import json

# Add project root to path
sys.path.append(os.getcwd())

from core.case_manager import CaseManager
from modules.file_analysis import FileAnalysisModule

def test_run():
    # Helper to mock CaseManager setup
    class MockLogger:
        def log(self, event, data=None):
            print(f"[LOG] {event}: {data}")

    class MockCaseManager:
        def __init__(self):
            self.results_dir = Path("debug_results")
            self.results_dir.mkdir(exist_ok=True)
            self.case_name = "debug_case"
        
        def get_logger(self):
            return MockLogger()

    cm = MockCaseManager()
    
    # Path provided by user
    input_file = Path(r"C:\Users\54538351172\Videos\Mídia\7c02f27fb66d644856e97a33561c292a1450414f6b3f905591473de77752e780-1724274784722.mov")
    
    print(f"Testing FileAnalysisModule on: {input_file}")
    
    try:
        module = FileAnalysisModule(cm)
        result = module.run(input_file, output_filename="debug_file_analysis.json")
        
        # Read back the file
        out_path = cm.results_dir / "debug_file_analysis.json"
        with open(out_path, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
            
        print("\n--- JSON Result (Format Keys) ---")
        fmt = saved_data.get('metadata', {}).get('format', {})
        print(f"Keys in format: {list(fmt.keys())}")
        print(f"Format Name: {fmt.get('format_name')}")
        print(f"Duration: {fmt.get('duration')}")
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_run()
