import re
from datetime import datetime
from pathlib import Path

VERSION_FILE = Path("app/version.py")

def update_version():
    if not VERSION_FILE.exists():
        print("1.0.0")
        return

    content = VERSION_FILE.read_text(encoding="utf-8")
    
    # Extract version
    version_match = re.search(r'VERSION = "(\d+)\.(\d+)\.(\d+)"', content)
    if not version_match:
        print("1.0.0")
        return
        
    major, minor, patch = map(int, version_match.groups())
    
    # Increment patch version
    new_version = f"{major}.{minor}.{patch + 1}"
    new_date = datetime.now().strftime("%Y-%m-%d")
    
    # Update file content
    new_content = re.sub(
        r'VERSION = ".*"',
        f'VERSION = "{new_version}"',
        content
    )
    new_content = re.sub(
        r'BUILD_DATE = ".*"',
        f'BUILD_DATE = "{new_date}"',
        new_content
    )
    
    VERSION_FILE.write_text(new_content, encoding="utf-8")
    
    # Print new version for batch script
    print(new_version)

if __name__ == "__main__":
    update_version()
