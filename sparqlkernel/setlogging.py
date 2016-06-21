"""
Install a logging configuration for kernel modules
"""


from logging.config import dictConfig
import tempfile
import os.path


# ----------------------------------------------------------------------

LOGCONFIG = {
    'version' : 1,
    'formatters' : {
        'default' : { 'format': 
                      '%(asctime)s %(levelname)s %(module)s.%(funcName)s: %(message)s' }
        },

    'handlers' : {
        'default' : { 'level' : 'DEBUG',
                      'class' : 'logging.handlers.RotatingFileHandler',
                      'formatter': 'default',
                      'filename': None,
                      'maxBytes': 1000000,
                      'backupCount': 3 }
        },

    'loggers' : { 
                  # the parent logger for sparqlkernel modules
                  'sparqlkernel' : { 'level' : 'INFO',
                                     'propagate' : False,
                                     'handlers' : ['default'] },

                  # This is the logger for the base kernel app
                  'IPKernelApp' : { 'level' : 'INFO',
                                    'propagate' : False,
                                    'handlers' : ['default'] },
              },

    # root logger
    'root' : { 'level': 'WARN',
               'handlers' : [ 'default' ]
        },
}


# ----------------------------------------------------------------------

def set_logging( logfilename=None, level=None ):
    """
    Set a logging configuration, with a rolling file appender.
    If passed a filename, use it as the logfile, else use a default name.

    The default logfile is \c sparqlkernel.log, placed in the directory given
    by (in that order) the \c LOGDIR environment variable, the logdir
    specified upon kernel installation or the default temporal directory.
    """
    if logfilename is None:
        # Find the logging diectory
        logdir = os.environ.get( 'LOGDIR' )
        if logdir is None:
            logdir = os.environ.get( 'LOGDIR_DEFAULT', tempfile.gettempdir() )
        # Define the log filename
        basename = __name__.split('.')[-2]
        logfilename = os.path.join( logdir, basename + '.log' )
    LOGCONFIG['handlers']['default']['filename'] = logfilename

    if level is not None:
        LOGCONFIG['loggers']['sparqlkernel']['level'] = level

    dictConfig( LOGCONFIG )
