import sys, os
sys.path.insert(0, r'D:\git\AINews\AINews')
from services.lip_sync.musetalk_engine import MuseTalkEngine
e = MuseTalkEngine()
reason = e.availability_reason()
if reason:
    print('NOT AVAILABLE:', reason)
else:
    print('AVAILABLE - engine ready')
