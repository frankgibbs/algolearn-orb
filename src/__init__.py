import logging
import logging.config
import numpy as np
import os, time
import sys
logging.config.fileConfig("logging.conf")
logger = logging.getLogger(__name__)

from sqlalchemy.orm import declarative_base
Base = declarative_base()

os.environ['TZ'] = 'US/Pacific'
time.tzset()
import mplfinance as mpf

logger.info(time.strftime('%X %x %Z'))
logger.info(f"mplfinance: {mpf.__version__}")
logger.info(f"python: {sys.version}")

#try:
#    from ray.rllib.utils.framework import try_import_tf
#    tf1, tf, tfv = try_import_tf()
#    logger.info(f"numpy: {np.__version__} tensorflow: {tf.__version__}")
#except:
#    logger.info("tensorflow not found")
#    pass
