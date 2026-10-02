"""
Scheduler for automated daily pipeline execution.
Uses the 'schedule' library for simple cron-like scheduling.
"""

import schedule
import time
import threading
from datetime import datetime, timezone

from utils.logger import get_logger

log = get_logger(__name__)


class PipelineScheduler:
    """
    Schedule daily training pipeline runs.

    Usage:
        scheduler = PipelineScheduler()
        scheduler.start()  # blocks forever, or
        scheduler.start_background()  # runs in a background thread
    """

    def __init__(self, run_time: str = "02:00"):
        """
        Args:
            run_time: Time to run daily training (24h format, e.g. "02:00")
        """
        self._run_time = run_time
        self._thread = None
        self._running = False

    def start(self):
        """Start the scheduler (blocking)."""
        self._setup_jobs()
        log.info(f"Scheduler started -- daily training at {self._run_time} UTC")
        self._running = True
        while self._running:
            schedule.run_pending()
            time.sleep(60)

    def start_background(self):
        """Start the scheduler in a background thread."""
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()
        log.info("Scheduler running in background.")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        schedule.clear()
        log.info("Scheduler stopped.")

    def run_now(self):
        """Manually trigger a pipeline run immediately."""
        self._daily_job()

    # ──────────────────────────────────────────────
    def _setup_jobs(self):
        schedule.every().day.at(self._run_time).do(self._daily_job)

    def _daily_job(self):
        """Execute a fresh training run using UTC scheduling."""
        log.info(f"Daily job triggered at {datetime.now(timezone.utc).isoformat()}")
        try:
            from pipeline.trainer import TrainingPipeline
            pipeline = TrainingPipeline()
            metrics = pipeline.run_daily()
            log.info(f"Daily training complete -- metrics: {metrics}")
        except Exception as e:
            log.error(f"Daily pipeline failed: {e}", exc_info=True)
