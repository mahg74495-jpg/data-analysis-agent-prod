#!/usr/bin/env python3
"""Start DAA Flask app with debug=False for background execution"""
import os, sys
sys.path.insert(0, '/Users/viton/Data-Analysis-Agent')
os.chdir('/Users/viton/Data-Analysis-Agent')
os.environ['LOG_DIR'] = 'outputs/Log'
os.environ['PYTHONUNBUFFERED'] = '1'

from log_setup import setup_logging
setup_logging(level=20)

from api import create_app
app = create_app()
print('DAA READY', flush=True)
app.run(host='0.0.0.0', port=5001, debug=False)
