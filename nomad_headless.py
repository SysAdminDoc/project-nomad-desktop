"""
NOMAD Field Desk headless server.

Runs Flask on 0.0.0.0:8080 without the desktop shell.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler

LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger('nomad.headless')

# Set headless flag before imports
os.environ['NOMAD_HEADLESS'] = '1'

# Set data directory from environment
data_dir = os.environ.get('NOMAD_DATA_DIR', '')
if data_dir:
    os.makedirs(data_dir, exist_ok=True)
    # Write config to point to the data directory
    from config import save_config
    save_config({'data_dir': data_dir})

def _check_deps():
    """Verify required dependencies are installed. Log errors for missing ones."""
    if getattr(sys, 'frozen', False):
        return
    missing = []
    deps = {'flask': 'flask', 'requests': 'requests', 'PIL': 'pillow', 'psutil': 'psutil'}
    for module, package in deps.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print(f'ERROR: Missing required packages: {", ".join(missing)}')
        print(f'Install with: pip install {" ".join(missing)}')
        print(f'Or install all: pip install -r requirements.txt')
        sys.exit(1)

_check_deps()

from db import init_db, log_activity
from web.app import create_app

VERSION = '1.0.0'
PORT = int(os.environ.get('NOMAD_PORT', 8080))


def main():
    log.info(f'NOMAD Field Desk Headless Server v{VERSION}')
    log.info(f'Data directory: {os.environ.get("NOMAD_DATA_DIR", "default")}')
    log.info(f'Listening on 0.0.0.0:{PORT}')

    init_db()
    log_activity('headless_started', detail=f'v{VERSION} on port {PORT}')

    from web.app import set_version
    set_version(VERSION)
    app = create_app()

    # Run Flask directly (no pywebview, no tray)
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
