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
                  # loggers for sparqlkernel modules
                  'sparqlkernel.kernel' : { 'level' : 'INFO',
                                            'propagate' : False,
                                            'handlers' : ['default'] },

                  'sparqlkernel.connection' : { 'level' : 'INFO',
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
    If passed a filename, use it as the logfile, else use a default name
    """
    if logfilename is None:
        logdir = os.environ.get( 'LOGDIR', tempfile.gettempdir() )
        basename = __name__.split('.')[-2]
        logfilename = os.path.join( logdir, basename + '.log' )
    LOGCONFIG['handlers']['default']['filename'] = logfilename

    if level is not None:
        LOGCONFIG['loggers']['sparqlkernel.kernel']['level'] = level
        LOGCONFIG['loggers']['sparqlkernel.connection']['level'] = level

    dictConfig( LOGCONFIG )
