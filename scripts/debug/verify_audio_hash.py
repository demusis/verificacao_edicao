
import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.audio_forensics import AudioForensicsModule
from core.case_manager import CaseManager
import numpy as np

# Mock config
class MockConfig:
    audio_segment_duration = 1
    audio_random_segments = 0
    audio_noise_window = 0.5
    audio_silence_threshold = -60

# Create dummy audio file (since we might not have one handy, let's try to use an existing one or just mock reading it if possible, 
# but AudioForensicsModule uses ffmpeg and librosa which expect real files.
# Let's see if we can find a test file or create a dummy WAV)

def create_dummy_wav(filename):
    import wave
    import struct
    import math

    sampleRate = 44100.0 # hertz
    duration = 1.0       # seconds
    frequency = 440.0    # hertz

    obj = wave.open(filename, 'w')
    obj.setnchannels(1) # mono
    obj.setsampwidth(2) # 2 bytes
    obj.setframerate(sampleRate)

    for i in range(int(duration * sampleRate)):
       value = int(32767.0*math.cos(frequency*math.pi*float(i)/float(sampleRate)))
       data = struct.pack('<h', value)
       obj.writeframesraw( data )
    obj.close()
    return Path(filename)

def verify():
    print("Starting verification...")
    
    # 1. Setup
    cm = CaseManager("test_case_audio_hash", base_dir=Path("./test_output"))
    cm.setup()
    
    dummy_wav = create_dummy_wav("test_audio.wav")
    print(f"Created dummy audio: {dummy_wav}")
    
    # 2. Run Audio Forensics
    print("Running AudioForensicsModule...")
    try:
        mod = AudioForensicsModule(cm, config=MockConfig())
        print("calling mod.run()")
        result = mod.run(dummy_wav, output_filename="audio_test.json")
        print("mod.run() finished")
        
        # 3. Check for Hash
        file_hash = result.get("file_hash")
        print(f"Hash found: {file_hash}")
        
        if file_hash and len(file_hash) == 128: # SHA-512 hex string length
            print("SUCCESS: File hash is present and looks like SHA-512.")
        else:
            print(f"FAILURE: File hash missing or invalid. Got: {file_hash}")
            return False

        # 4. Check Reporting Logic (Simulated)
        # We can't easily run full ReportingModule because it requires Latex. 
        # But we can verify the data structure matches what ReportingModule expects.
        
        print("Verifying Reporting Module logic integration...")
        audio_data = result
        
        if 'file_hash' in audio_data:
             print(f"SUCCESS: 'file_hash' key is available for ReportingModule: {audio_data['file_hash']}")
        else:
             print("FAILURE: 'file_hash' key missing for ReportingModule.")
             return False
        
        # 5. Check Error Handling logic in code (by manual inspection or logic here)
        # If 'status' was error, 'error' key should exist.
        if audio_data['status'] == 'error':
             print(f"Note: Analysis returned error: {audio_data.get('error')}")
             # This counts as success for verification of the FIX (since we want to see the error, not crash)
             # But if we expected success (dummy file), then it is a failure of logic.
             # Librosa is installed now, so we expect SUCCESS.
             print("FAILURE: Expected success but got error.")
             return False
             
    except Exception as e:
        print(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists("test_audio.wav"):
            try:
                os.remove("test_audio.wav")
            except Exception as cleanup_error:
                print(f"Warning: Could not remove test_audio.wav: {cleanup_error}")
            
    return True

if __name__ == "__main__":
    if verify():
        print("VERIFICATION PASSED")
        sys.exit(0)
    else:
        print("VERIFICATION FAILED")
        sys.exit(1)
