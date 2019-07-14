
import os
import os.path
import io
from operator import itemgetter
import logging

import SPARQLWrapper

from .constants import DEFAULT_TEXT_LANG
from .utils import KrnlException, is_collection


# Maximum number of nestes magic files
MAX_RECURSE = 10


# The list of implemented magics with their help, as a pair [param,help-text]
MAGICS = {
    '%lsmagics': ['', 'list all magics'],
    '%load': ['<filename>', 'load a file with magic lines and process them'],
    '%endpoint': ['<url>', 'set SPARQL endpoint. **REQUIRED**'],
    '%auth':     ['(basic|digest|none) <username> <passwd>', 'send HTTP authentication (use env:<var> to get values from environment variables)'],
    '%qparam':   ['<name> [<value>]', 'add (or delete) a persistent custom parameter to all queries'],
    '%http_header':   ['<name> [<value>]', 'add (or delete) an arbitrary HTTP header to all queries'],
    '%prefix':   ['<name> [<uri>]', 'set (or delete) a persistent URI prefix for all queries'],
    '%header':   ['<string> | OFF', 'add a persistent SPARQL header line before all queries, or delete all defined headers'],
    '%graph':    ['<uri>', 'set default graph for the queries'],
    '%format':   ['JSON | N3 | XML | default | any | none', 'set requested result format'],
    '%display':  ['raw | table [withtypes] | diagram [svg|png] [withliterals]',
                  'set display format'],
    '%lang':     ['<lang> [...] | default | all',
                  'language(s) preferred for labels'],
    '%show':     ['<n> | all',
                  'maximum number of shown results'],
    '%outfile':  ['<filename> | off', 'save raw output to a file (use "%d" in name to add cell number, "off" to cancel saving)'],
    '%log':      ['critical | error | warning | info | debug',
                  'set logging level'],
    '%method':   ['get | post', 'set HTTP method'],
}


# The full list of all magics
MAGIC_HELP = ('Available magics:\n' +
              '  '.join(sorted(MAGICS.keys())) +
              '\n\n' +
              '\n'.join(('{0} {1} : {2}'.format(k, *v)
                         for k, v in sorted(MAGICS.items(), key=itemgetter(0)))))


# -----------------------------------------------------------------------------

def split_lines(buf):
    '''
    Split a buffer in lines, skipping emtpy lines and commend lines, and
    stripping whitespace at the beginning or end of lines
    '''
    return [line for line in map(lambda x: x.strip(), buf.split('\n'))
            if line and line[0] != '#']


def process_magic(line, cfg, _recurse=0):
    """
    Read and process magics
      @param line (str): the full line containing a magic
      @param obj
      @return (list): a tuple (output-message,css-class), where
        the output message can be a single string or a list (containing
        a Python format string and its arguments)
    """
    if _recurse > MAX_RECURSE:
        raise KrnlException('maximum magic file recursion level exceeded')

    # The %lsmagic has no parameters
    if line.startswith('%lsmagic'):
        return MAGIC_HELP, 'magic-help'

    # Split line into command & parameters
    try:
        cmd, param = line.split(None, 1)
    except ValueError:
        raise KrnlException("invalid magic line: {}", line)
    cmd = cmd[1:].lower()

    # Process each magic
    if cmd == 'load':

        try:
            with io.open(param, 'rt', encoding='utf-8') as f:
                buf = f.read()
        except Exception as e:
            raise KrnlException("cannot read magics file '{}': {}", param, e)
        for line in split_lines(buf):
            if line[0] != '%':
                raise KrnlException("error in file '{}': non-magic line found: {}",
                                    param, line)
            process_magic(line, cfg, _recurse+1)

    elif cmd == 'endpoint':

        cfg.ept = param
        return ['Endpoint set to: {}', param], 'magic'

    elif cmd == 'auth':

        auth_data = param.split(None, 2)
        if auth_data[0].lower() == 'none':
            cfg.aut = None
            return ['HTTP authentication: None'], 'magic'
        if auth_data and len(auth_data) != 3:
            raise KrnlException("invalid %auth magic")
        try:
            auth_data = [os.environ[v[4:]] if v.startswith(('env:', 'ENV:')) else v
                         for v in auth_data]
        except KeyError as e:
            raise KrnlException("cannot find environment variable: {}", e)
        cfg.aut = auth_data
        return ['HTTP authentication: method={}, user={}, passwd set',
                auth_data[0], auth_data[1]], 'magic'

    elif cmd == 'qparam':

        v = param.split(None, 1)
        if len(v) == 0:
            raise KrnlException("missing %qparam name")
        elif len(v) == 1:
            cfg.par.pop(v[0], None)
            return ['Param deleted: {}', v[0]], 'magic'
        else:
            cfg.par[v[0]] = v[1]
            return ['Param set: {} = {}'] + v, 'magic'

    elif cmd == 'http_header':

        v = param.split(None, 1)
        if len(v) == 0:
            raise KrnlException("missing %http_header name")
        elif len(v) == 1:
            try:
                del cfg.hhr[v[0]]
                return ['HTTP header deleted: {}', v[0]], 'magic'
            except KeyError:
                return ['Not-existing HTTP header: {}', v[0]], 'magic'
        else:
            cfg.hhr[v[0]] = v[1]
            return ['HTTP header set: {} = {}'] + v, 'magic'

    elif cmd == 'prefix':

        v = param.split(None, 1)
        if len(v) == 0:
            raise KrnlException("missing %prefix value")
        elif len(v) == 1:
            cfg.pfx.pop(v[0], None)
            return ['Prefix deleted: {}', v[0]], 'magic'
        else:
            cfg.pfx[v[0]] = v[1]
            return ['Prefix set: {} = {}'] + v, 'magic'

    elif cmd == 'show':

        if param == 'all':
            cfg.lmt = None
        else:
            try:
                cfg.lmt = int(param)
            except ValueError as e:
                raise KrnlException("invalid result limit: {}", e)
        sz = cfg.lmt if cfg.lmt is not None else 'unlimited'
        return ['Result maximum size: {}', sz], 'magic'

    elif cmd == 'format':

        fmt_list = {'JSON': SPARQLWrapper.JSON,
                    'N3': SPARQLWrapper.N3,
                    'XML': SPARQLWrapper.XML,
                    'RDF': SPARQLWrapper.RDF,
                    'NONE': None,
                    'DEFAULT': True,
                    'ANY': False}
        try:
            fmt = param.upper()
            cfg.fmt = fmt_list[fmt]
        except KeyError:
            raise KrnlException('unsupported format: {}\nSupported formats are: {!s}', param, list(fmt_list.keys()))
        return ['Request format: {}', fmt], 'magic'

    elif cmd == 'lang':

        cfg.lan = DEFAULT_TEXT_LANG if param == 'default' else [] if param == 'all' else param.split()
        return ['Label preferred languages: {}', cfg.lan], 'magic'

    elif cmd in 'graph':

        cfg.grh = param if param else None
        return ['Default graph: {}', param if param else 'None'], 'magic'

    elif cmd == 'display':

        v = param.lower().split(None, 2)
        if len(v) == 0 or v[0] not in ('table', 'raw', 'graph', 'diagram'):
            raise KrnlException('invalid %display command: {}', param)

        msg_extra = ''
        if v[0] not in ('diagram', 'graph'):
            cfg.dis = v[0]
            cfg.typ = len(v) > 1 and v[1].startswith('withtype')
            if cfg.typ and cfg.dis == 'table':
                msg_extra = '\nShow Types: on'
        elif len(v) == 1:   # graph format, defaults
            cfg.dis = ['svg']
        else:               # graph format, with options
            if v[1] not in ('png', 'svg'):
                raise KrnlException('invalid graph format: {}', param)
            if len(v) > 2:
                if not v[2].startswith('withlit'):
                    raise KrnlException('invalid graph option: {}', param)
                msg_extra = '\nShow literals: on'
            cfg.dis = v[1:3]

        display = cfg.dis[0] if is_collection(cfg.dis) else cfg.dis
        return ['Display: {}{}', display, msg_extra], 'magic'

    elif cmd == 'outfile':

        if param in ('NONE', 'OFF'):
            cfg.out = None
            return ['no output file'], 'magic'
        else:
            cfg.out = param
            return ['Output file: {}', os.path.abspath(param)], 'magic'

    elif cmd == 'log':

        if not param:
            raise KrnlException('missing log level')
        try:
            lev = param.upper()
            parent_logger = logging.getLogger(__name__.rsplit('.', 1)[0])
            parent_logger.setLevel(lev)
            return ("Logging set to {}", lev), 'magic'
        except ValueError:
            raise KrnlException('unknown log level: {}', param)

    elif cmd == 'header':

        if param.upper() == 'OFF':
            num = len(cfg.hdr)
            cfg.hdr = []
            return ['All headers deleted ({})', num], 'magic'
        else:
            if param in cfg.hdr:
                return ['Header skipped (repeated)'], 'magic'
            cfg.hdr.append(param)
            return ['Header added: {}', param], 'magic'

    elif cmd == 'method':

        method = param.upper()
        if method not in ('GET', 'POST'):
            raise KrnlException('invalid HTTP method: {}', param)
        cfg.mth = method
        return ['HTTP method: {}', method], 'magic'

    else:
        raise KrnlException("magic not found: {}", cmd)
