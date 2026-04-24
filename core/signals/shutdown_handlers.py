"""
Graceful shutdown handlers for production reliability
"""
import signal
import sys
import logging
from django.core.cache import cache
from django.db import connections

logger = logging.getLogger(__name__)

class GracefulShutdownHandler:
    """
    ✅ RELIABILITY: Handle graceful shutdown of the application
    Ensures data integrity during restarts and deployments
    """
    
    def __init__(self):
        self.shutdown_initiated = False
        self.setup_signal_handlers()
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)
        
        # For Windows compatibility
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, self.handle_shutdown)
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signal"""
        if self.shutdown_initiated:
            logger.warning("Shutdown already in progress, forcing exit...")
            sys.exit(1)
        
        self.shutdown_initiated = True
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        
        try:
            self.cleanup_resources()
            logger.info("Graceful shutdown completed successfully")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            sys.exit(1)
    
    def cleanup_resources(self):
        """Cleanup resources before shutdown"""
        logger.info("Starting resource cleanup...")
        
        # Close database connections
        try:
            for conn in connections.all():
                conn.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
        
        # Clear cache connections
        try:
            cache.close()
            logger.info("Cache connections closed")
        except Exception as e:
            logger.error(f"Error closing cache connections: {e}")
        
        # Add any other cleanup tasks here
        # - Close file handles
        # - Stop background tasks
        # - Save pending data
        
        logger.info("Resource cleanup completed")

# Initialize graceful shutdown handler
shutdown_handler = GracefulShutdownHandler()