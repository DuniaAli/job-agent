import os
import sys

# Lets the tests import store.py, pipeline.py and so on from the project folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
