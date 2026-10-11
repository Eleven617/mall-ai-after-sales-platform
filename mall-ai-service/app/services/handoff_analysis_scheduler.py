"""Recoverable polling of Java leases; classification never gates case handling."""
import os
import threading

def start_worker():
    stop=threading.Event()
    def poll():
        from app.services.handoff_analysis_worker import run_once
        while not stop.wait(15):
            if os.getenv('MALL_RUNTIME_PROVIDER_MODE')!='live' or os.getenv('MALL_PROVIDER_LIVE_AUTH')!='1':
                continue
            try:
                run_once()
            except Exception:
                # Lease expiry permits recovery. Never log customer payloads.
                pass
    if os.getenv('MALL_HANDOFF_ANALYSIS_ENABLED','0')=='1':
        threading.Thread(target=poll,name='handoff-analysis',daemon=True).start()
    return stop
