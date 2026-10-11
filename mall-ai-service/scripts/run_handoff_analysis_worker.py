"""Run one bounded analysis lease using the same worker as the service."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.handoff_analysis_worker import run_once

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.parse_args()
    try:
        sys.exit(run_once())
    except Exception:
        print('analysis_worker_failed')
        sys.exit(1)
