import urllib.request
import os
import sys

urls = {
    'msgpack.whl': 'https://files.pythonhosted.org/packages/74/07/1ed8277f8653c40ebc65985180b007879f6a836c525b3885dcc6448ae6cb/msgpack-1.1.2-cp313-cp313-win_amd64.whl'
}

def download():
    success = True
    for name, url in urls.items():
        print(f"Downloading {name}...")
        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            
            urllib.request.urlretrieve(url, name)
            size = os.path.getsize(name)
            print(f"Downloaded {name}: {size} bytes")
            if size < 1000:
                 print(f"ERROR: {name} is too small ({size} bytes). Likely a download error.")
                 success = False
        except Exception as e:
            print(f"ERROR downloading {name}: {e}")
            success = False
    return success

if __name__ == "__main__":
    if download():
        print("All downloads successful.")
        sys.exit(0)
    else:
        print("Some downloads failed.")
        sys.exit(1)
