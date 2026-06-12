import re
from pathlib import Path

VERSION_FILE = Path("app/version.py")

def get_version():
    if not VERSION_FILE.exists():
        print("1.4.0")
        return

    content = VERSION_FILE.read_text(encoding="utf-8")
    version_match = re.search(r'VERSION = "(\d+)\.(\d+)\.(\d+)"', content)
    if version_match:
        print(f"{version_match.group(1)}.{version_match.group(2)}.{version_match.group(3)}")
    else:
        print("1.4.0")

if __name__ == "__main__":
    get_version()
