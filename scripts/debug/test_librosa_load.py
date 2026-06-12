import librosa
import numpy as np
import wave
import struct
import math
import os

def create_dummy_wav(filename):
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
    return filename

fname = create_dummy_wav("test_iso.wav")
print(f"Created {fname}")

try:
    print("Loading with librosa...")
    y, sr = librosa.load(fname, sr=None)
    print(f"Loaded: sr={sr}, shape={y.shape}")
except Exception as e:
    print(f"Error: {e}")
finally:
    if os.path.exists(fname):
        os.remove(fname)
