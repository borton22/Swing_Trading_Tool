import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector import init_db, update_universe
from config import UNIVERSE
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("=== Mise a jour quotidienne des donnees ===")
    init_db()
    results = update_universe(UNIVERSE, full_refresh=False)
    total = sum(results.values())
    logger.info(f"=== Termine: {total} lignes mises a jour ===")
