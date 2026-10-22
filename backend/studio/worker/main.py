import logging
import signal
import time

from studio.config import get_settings
from studio.db import init_db
from studio.worker.pipeline import claim_next, recover_interrupted, run_workflow

log = logging.getLogger("studio.worker")


class Worker:
    """Takes queued workflows one at a time and runs the pipeline on them."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.stopping = False

    def stop(self, *_: object) -> None:
        log.info("stop requested, finishing current workflow first")
        self.stopping = True

    def run_once(self) -> bool:
        workflow_id = claim_next()
        if workflow_id is None:
            return False
        log.info("workflow %s started", workflow_id)
        status = run_workflow(self.settings, workflow_id)
        log.info("workflow %s finished: %s", workflow_id, status)
        return True

    def run_forever(self) -> None:
        recovered = recover_interrupted()
        if recovered:
            log.info("requeued %d interrupted workflow(s)", recovered)
        log.info("worker ready, data dir %s", self.settings.data_dir.resolve())
        while not self.stopping:
            if not self.run_once():
                time.sleep(self.settings.worker_poll_seconds)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    settings.ensure_dirs()
    init_db(settings.db_url)
    worker = Worker()
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    worker.run_forever()


if __name__ == "__main__":
    run()
