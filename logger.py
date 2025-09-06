import logging, sys

logger = logging.getLogger("TruthTableWSGI")
if not logger.handlers:  # avoid duplicate handlers on module reloads
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stderr)  # goes to Apache error log
    h.setFormatter(logging.Formatter(
        '%(asctime)s %(process)d %(levelname)s %(name)s: %(message)s'
    ))
    logger.addHandler(h)
