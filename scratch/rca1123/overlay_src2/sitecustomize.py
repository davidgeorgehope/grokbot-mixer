"""Put this overlay first so mix_simple subprocesses import our finephase.py.
Only active when PYTHONPATH includes this directory. Does not change src2 on disk.
"""
import sys
sys.path.insert(0, '/tmp/rca1123/overlay_src2')
