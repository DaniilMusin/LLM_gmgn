import asyncio
import signal
import sys
from .engine import Orchestrator
from .utils.logging import logger

# BUG FIX #44: Add graceful shutdown handler
_orchestrator = None

def shutdown_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {sig}, shutting down gracefully...")
    if _orchestrator:
        try:
            # Save hype state before exit
            _orchestrator.hype.save_state()
            logger.info("Hype state saved successfully")
        except Exception as e:
            logger.error(f"Failed to save hype state on shutdown: {e}")

    logger.info("Shutdown complete")
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    _orchestrator = Orchestrator()
    try:
        asyncio.run(_orchestrator.run())
    except KeyboardInterrupt:
        shutdown_handler(signal.SIGINT, None)
