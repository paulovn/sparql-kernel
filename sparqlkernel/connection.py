"""
The class used to manage the connection to SPARQL endpoint: send queries and
format results for notebook display. Also process all the defined magics
"""
from __future__ import print_function

import sys
import io
import re
import json
import datetime
import logging
import pprint

from IPython.utils.tokenutil import token_at_cursor, line_at_cursor
from ipykernel.kernelbase import Kernel
from traitlets import List

import SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import SPARQLWrapperException
from rdflib import ConjunctiveGraph, URIRef, Literal
from rdflib.parser import StringInputSource

from .constants import __version__, LANGUAGE, DEFAULT_TEXT_LANG
from .utils import is_collection, KrnlException, div, escape
from .language import sparql_names, sparql_help
from .drawgraph import draw_graph

# IPython.core.display.HTML

PY3 = sys.version_info[0] == 3
if PY3:
    unicode = str
    touc = str
else:
    touc = lambda x : str(x).decode('utf-8','replace')


# Valid mime types in the SPARQL response (depending on what we requested)
mime_type = { SPARQLWrapper.JSON :  set(['application/sparql-results+json',
                                         'text/javascript']),
              SPARQLWrapper.N3 :    set(['text/rdf+n3', 'text/turtle', 
                                         'application/x-turtle',
                                         'application/rdf+xml']),
              SPARQLWrapper.RDF :   set(['text/rdf', 'application/rdf+xml']),
              SPARQLWrapper.TURTLE: set(['text/turtle', 'application/x-turtle']),
              SPARQLWrapper.XML :   set(['application/sparql-results+xml']),
}

# ----------------------------------------------------------------------

# The list of implemented magics with their help, as a pair [param,help-text]
magics = { 
    '%lsmagics' : [ '', 'list all magics'], 
    '%endpoint' : [ 'url', 'set SPARQL endpoint. REQUIRED.'],
    '%auth_type|user|password': ['authentication type, user and password', 'set authentication type (DIGEST or BASIC), user and password. OPTIONAL.'],
    '%prefix' :   [ 'uri', 'set a persistent URI prefix for all queries'], 
    '%graph' :    [ 'uri', 'set default graph for the queries' ],
    '%format' :   [ 'JSON | N3 | any | default', 'set requested result format' ],
    '%display' :  [ 'raw | table [withtypes] | diagram [svg|png] [withliterals]', 
                    'set display format' ],
    '%lang' :     [ '<lang> [...] | default | all',
                    'language(s) preferred for labels' ],
    '%show' :     [ '<n> | all',
                    'maximum number of shown results' ],
    '%outfile' :  [ '<filename> | NONE', 'save raw output to a file (use "%d" in name to add cell number, "NONE" to cancel saving)'],
    '%log' :      [ 'critical | error | warning | info | debug', 
                    'set logging level'],
}

# The full list of all magics
magic_help = ('Available magics:\n' + 
              '  '.join( sorted(magics.keys()) ) + 
              '\n\n' +
              '\n'.join( ('{0} {1} : {2}'.format(k,*magics[k]) 
                          for k in sorted(magics) ) ) )


# ----------------------------------------------------------------------


def html_elem( e, ct, withtype=False ):
    """
    Format a result element as an HTML table cell.
      @param e (list): a pair \c (value,type)
      @param ct (str): cell type (th or td)
      @param withtype (bool): add an additional cell with the element type
    """
    # Header cell
    if ct == 'th':
        return '<th>{0}</th><th>{1}</th>'.format(*e) if withtype else '<th>{}</th>'.format(e)
    # Content cell
    if e[1] in ('uri','URIRef'):
        html = u'<{0} class=val><a href="{1}" target="_other">{2}</a></{0}>'.format(ct,e[0],escape(e[0]))
    else:
        html = u'<{0} class=val>{1}</{0}>'.format(ct,escape(e[0]))
    # Create the optional cell for the type
    if withtype:
        html += u'<{0} class=typ>{1}</{0}>'.format(ct,e[1])
    return html


def html_table( data, header=True, limit=None, withtype=False ):
    """
    Return a double iterable as an HTML table
      @param data (iterable): the data to format
      @param header (bool): if the first row is a header row
      @param limit (int): maximum number of rows to render (excluding header)
      @param withtype (bool): if columns are to have an alternating CSS class
        (even/odd) or not.
      @return (int,string): a pair <number-of-rendered-rows>, <html-table>
    """
    if header and limit:
        limit += 1
    ct = 'th' if header else 'td'
    rc = 'hdr' if header else 'odd'

    # import codecs
    # import datetime
    # with codecs.open( '/tmp/dump', 'w', encoding='utf-8') as f:
    #     print( '************', datetime.datetime.now(), file=f )
    #     for n, row in enumerate(data):
    #         print( '-------', n,  file=f )
    #         for n, c in enumerate(row):
    #             print( type(c), repr(c), file=f )

    html = u'<table>'
    rn = -1
    for rn, row in enumerate(data):
        html += u'<tr class={}>'.format(rc)
        html += '\n'.join( (html_elem(c,ct,withtype) for c in row) )
        html += u'</tr>'
        rc = 'even' if rc == 'odd' else 'odd'
        ct = 'td'
        if limit:
            limit -= 1
            if not limit:
                break
    return (0, '') if rn<0 else (rn+1-header, html+u'</table>')


# ----------------------------------------------------------------------

def jtype( c ):
    """
    Return the a string with the data type of a value, for JSON data
    """
    ct = c['type']
    return ct if ct != 'literal' else '{}, {}'.format(ct,c.get('xml:lang'))


def gtype( n ):
    """
    Return the a string with the data type of a value, for Graph data
    """
    t = type(n).__name__
    return str(t) if t != 'Literal' else 'Literal, {}'.format(n.language)


def lang_match_json( row, hdr, accepted_languages ):
    languages = set( [ row[c].get('xml:lang') for c in hdr
                       if c in row and row[c]['type'] == 'literal' ] )
    return (not languages) or (languages & accepted_languages)

def lang_match_rdf( triple, accepted_languages ):
    languages = set( [ n.language for n in triple if isinstance(n,Literal) ] )
    return (not languages) or (languages & accepted_languages)



def json_iterator( hdr, rowlist, add_vtype=False, lang=[] ):
    """
    Convert a JSON response into a double iterable, by rows and columns
    Optionally add element type, and filter triples by language (on literals)
    """
    if lang:
        lang = set(lang)
    # Return the header row
    yield hdr if not add_vtype else ( (h, 'type') for h in hdr )
    # Now the data rows
    for row in rowlist:
        if lang and not lang_match_json( row, hdr, lang ):
            continue
        yield ( (row[c]['value'], jtype(row[c])) if c in row else ('','')
                for c in hdr )


def rdf_iterator( graph, add_vtype=False, lang=[] ):
    """
    Convert a Graph response into a double iterable, by triples and elements.
    Optionally add element type, and filter triples by language (on literals)
    """
    if lang:
        lang = set(lang)
    # Return the header row
    hdr = ('subject','predicate','object')
    yield hdr if not add_vtype else ( (h, 'type') for h in hdr )
    # Now the data rows
    for row in graph:
        if lang and not lang_match_rdf( row, lang ):
            continue
        yield ( (unicode(c), gtype(c)) for c in row)


def render_json( result, cfg, **kwargs ):
    """
    Render for output a result in JSON format
    """
    result = json.loads( result.decode('utf-8') )
    head = result['head']
    if 'results' not in result:
        if 'boolean' in result:
            r = u'Result: {}'.format(result['boolean'])
        else:
            r = u'Unsupported result: \n' + unicode( result )
        return { 'data' : { 'text/plain' : r },
                 'metadata' : {} }

    vars = head['vars']
    nrow = len( result['results']['bindings'] )
    if cfg.dis == 'table':
        j = json_iterator( vars, result['results']['bindings'], 
                           add_vtype=cfg.typ, lang=cfg.lan )
        n, data = html_table( j, limit=cfg.lmt, withtype=cfg.typ )
        data += div( 'Total: {}, Shown: {}', nrow, n, css="tinfo" )
        data = {'text/html' : div(data) }
    else:
        data = {'text/plain' : unicode( pprint.pformat(result) ) }
    
    return { 'data': data ,
             'metadata' : {} }


def render_graph( result, cfg, **kwargs ):
    """
    Render for output a result that can be parsed as an RDF graph
    """

    # Mapping from MIME types to formats accepted by RDFlib
    rdflib_formats = { 'text/rdf+n3' : 'n3',
                       'text/turtle' : 'turtle',
                       'application/x-turtle' : 'turtle',
                       'text/turtle' : 'turtle',
                       'application/rdf+xml' : 'xml',
                       'text/rdf' : 'xml',
                       'application/rdf+xml' : 'xml',
    }

    try:
        got = kwargs.get('format','text/rdf+n3')
        fmt = rdflib_formats[got]
    except KeyError:
        raise KrnlException( 'Unsupported format for graph processing: {!s}', got )

    g = ConjunctiveGraph()
    g.load( StringInputSource(result), format=fmt )

    display = cfg.dis[0] if is_collection(cfg.dis) else cfg.dis
    if display in ('png','svg') :
        try:
            literal = len(cfg.dis) > 1 and cfg.dis[1].startswith('withlit')
            opt = { 'lang' : cfg.lan, 'literal' : literal, 'graphviz' : [] }
            data, metadata = draw_graph(g,fmt=display,options=opt)
            return { 'data' : data,
                     'metadata' : metadata  }
        except Exception as e:
            raise KrnlException( 'Exception while drawing graph: {!r}', e )
    elif display == 'table':
        it = rdf_iterator(g,add_vtype=cfg.typ, lang=cfg.lan)
        n, data = html_table(it,limit=cfg.lmt, withtype=cfg.typ)
        data += div( 'Shown: {}, Total rows: {}', n if cfg.lmt else 'all',
                     len(g), css="tinfo" )
        data = {'text/html' : div(data) }
    elif len(g) == 0:
        data = { 'text/html' : div( div('empty graph',css='krn-warn') ) }
    else:
        data = { 'text/plain' : g.serialize(format='nt').decode('utf-8') }

    return { 'data': data,
             'metadata' : {} }

        

# ----------------------------------------------------------------------

class CfgStruct:
    """
    A simple class containing a bunch of fields
    """
    def __init__(self, **entries): 
        self.__dict__.update(entries)


# ----------------------------------------------------------------------

class SparqlConnection( object ):

    def __init__( self, logger=None ):
        """
        Initialize an empty configuration
        """
        self.log = logger or logging.getLogger(__name__)
        self.srv = None
        self.log.info( "START" )
        self.cfg = CfgStruct( pfx={}, lmt=20, fmt=None, out=None,
                              grh=None, dis='table', typ=False, lan=[] )

    def magic( self, line ):
        """
        Read and process magics
          @param line (str): the full line containing a magic
          @return (list): a tuple (output-message,css-class), where
            the output message can be a single string or a list (containing
            a Python format string and its arguments)
        """
        # The %lsmagic has no parameters
        if line.startswith( '%lsmagic' ):
            return magic_help, 'magic-help'

        # Split line into command & parameters
        try:
            cmd, param = line.split(None,1)
        except ValueError:
            raise KrnlException( "invalid magic: {}", line )
        cmd = cmd[1:].lower()

        # Process each magic
        if cmd == 'endpoint':

            self.srv = SPARQLWrapper.SPARQLWrapper( param )

            return ['Endpoint set to: {}', param], 'magic'

        elif cmd == 'auth_type|user|password':

            p = param.split('|')
            self.srv.setHTTPAuth(p[0])
            self.srv.setCredentials(p[1], p[2])

            return ['Endpoint set to: {}', param], 'magic'

        elif cmd == 'prefix':

            v = param.split(None, 1)
            if len(v) == 0:
                raise KrnlException( "missing %prefix value" )
            elif len(v) == 1:
                self.cfg.pfx.pop(v[0],None)
                return ['Prefix deleted: {}', v[0]]
            else:
                self.cfg.pfx[prefix] = uri
                return ['Prefix set: {} {}'] + v, 'magic' 

        elif cmd == 'show':

            if param == 'all':
                self.cfg.lmt = None
            else:
                try:
                    self.cfg.lmt = int(param)
                except ValueError as e:
                    raise KrnlException( "invalid result limit: {}", e )
            l = self.cfg.lmt if self.cfg.lmt is not None else 'unlimited'
            return ['Result maximum size: {}', l], 'magic'

        elif cmd == 'format':

            fmt_list = { 'JSON' : SPARQLWrapper.JSON, 
                         'N3' :  SPARQLWrapper.N3,
                         'DEFAULT' : None,
                         'ANY' : False }
            try:
                fmt = param.upper()
                self.cfg.fmt = fmt_list[fmt]
            except KeyError:
                raise KrnlException( 'unsupported format: {}\nSupported formats are: {!s}', param, list(fmt_list.keys()) )
            return ['Return format: {}', fmt], 'magic'

        elif cmd == 'lang':

            self.cfg.lan = DEFAULT_TEXT_LANG if param == 'default' else [] if param=='all' else param.split()
            return ['Label preferred languages: {}', self.cfg.lan], 'magic'

        elif cmd in 'graph':

            self.cfg.grh = param if param else None
            return [ 'Default graph: {}', param if param else 'None' ], 'magic'

        elif cmd == 'display':

            v = param.lower().split(None, 2)            
            if len(v) == 0 or v[0] not in ('table','raw','graph','diagram'):
                raise KrnlException( 'invalid %display command: {}', param )

            msg_extra = ''
            if v[0] not in ('diagram','graph'):
                self.cfg.dis = v[0]
                self.cfg.typ = len(v)>1 and v[1].startswith('withtype')
                if self.cfg.typ and self.cfg.dis == 'table':
                    msg_extra = '\nShow Types: on'
            elif len(v) == 1:   # graph format, defaults
                self.cfg.dis = ['svg']
            else:               # graph format, with options 
                if v[1] not in ('png','svg'):
                    raise KrnlException( 'invalid graph format: {}', param )
                if len(v) > 2:
                    if not v[2].startswith('withlit'):
                        raise KrnlException( 'invalid graph option: {}',param)
                    msg_extra = '\nShow literals: on'
                self.cfg.dis = v[1:3]

            display = self.cfg.dis[0] if is_collection(self.cfg.dis) else self.cfg.dis
            return [ 'Display: {}{}', display, msg_extra ], 'magic'

        elif cmd == 'outfile':

            if param == 'NONE':
                self.cfg.out = None
                return [ 'no output file' ], 'magic'
            else:
                self.cfg.out = param
                return [ 'Output file: {}', param ], 'magic'

        elif cmd == 'log':

            if not param:
                raise KrnlException( 'missing log level' )
            try:
                l = param.upper()
                parent_logger = logging.getLogger( __name__.rsplit('.',1)[0] )
                #parent_logger.error( '[%s][%s]', __name__,  __name__.rsplit('.',1)[0] )
                parent_logger.setLevel( l )
                return ("Logging set to {}", l), 'magic'
            except ValueError:
                raise KrnlException( 'unknown log level: {}', param )

        else:
            raise KrnlException( "magic not found: {}", cmd )


    def query( self, query, num=0, silent=False ):
        """
        Launch an SPARQL query, process & convert results and return them
        """
        if self.srv is None:
            raise KrnlException('no endpoint defined')             

        # Add to the query all predefined SPARQL prefixes
        if self.cfg.pfx:
            prefix = '\n'.join( ( 'PREFIX {} {}'.format(*v) 
                                  for v in self.cfg.pfx(iteritems) ) )
            query = prefix  + '\n' + code

        if self.log.isEnabledFor(logging.DEBUG):
            self.log.debug( "\n%50s%s", query, '...' if len(query)>50 else '' )

        # Select requested format
        if self.cfg.fmt is not None:
            fmt_req = self.cfg.fmt
        elif re.search(r'\bselect\b',query,re.I):
            fmt_req = SPARQLWrapper.JSON
        elif re.search(r'\b(?:describe|construct)\b',query,re.I):
            fmt_req = SPARQLWrapper.N3
        else:
            fmt_req = False

        # Set the query
        self.srv.resetQuery()
        self.log.debug(u'request format: %s  display: %s', fmt_req, self.cfg.dis)
        if fmt_req:
            self.srv.setReturnFormat( fmt_req )
        if self.cfg.grh:
            self.srv.addParameter("default-graph-uri",self.cfg.grh)
        self.srv.setQuery( query )

        if not silent or self.cfg.out:
            try:
                # Launch query
                start = datetime.datetime.utcnow()
                res = self.srv.query()
                now = datetime.datetime.utcnow()
                self.log.debug( u'response elapsed=%s', now-start )
                start = now

                # See what we got
                info = res.info()
                self.log.debug( u'response info: %s', info )
                fmt_got = info['content-type'].split(';')[0] if 'content-type' in info else None

                # Check we received a MIME type according to what we requested
                if fmt_req and fmt_got not in mime_type[fmt_req]:
                    raise KrnlException(u'Unexpected response format: {}',fmt_got)

                # Get the result
                data = b''.join( (line for line in res) )

            except KrnlException:
                raise
            except SPARQLWrapperException as e:
                raise KrnlException( u'SPARQL error: {}', touc(e) )
            except Exception as e:
                raise KrnlException( u'Query processing error: {!s}', e )

            # Write the raw result to a file
            if self.cfg.out:
                try:
                    outname = self.cfg.out % num
                except TypeError:
                    outname = self.cfg.out
                with io.open(outname,'wb') as f:
                    f.write( data )

            # Render the result into the desired display format
            try:
                # Data format we will render
                fmt = (fmt_req if fmt_req else
                       SPARQLWrapper.JSON if fmt_got in mime_type[SPARQLWrapper.JSON] else
                       SPARQLWrapper.N3 if fmt_got in mime_type[SPARQLWrapper.N3] else
                       'text/plain' if self.cfg.dis == 'raw' else
                       fmt_got if fmt_got in ('text/plain','text/html') else
                       'text/plain')
                #self.log.debug(u'format: req=%s got=%s rend=%s',fmt_req,fmt_got,fmt)

                # Can't process? Just write the data as is
                if fmt in ('text/plain','text/html'):
                    r = { 'data': { fmt : data }, 'metadata' : {} }
                else:
                    f = render_json if fmt == SPARQLWrapper.JSON else render_graph
                    r = f( data, self.cfg, format=fmt_got )
                    now = datetime.datetime.utcnow()
                    self.log.debug( u'response formatted=%s', now-start )
                if not silent:
                    return r

            except Exception as e:
                raise KrnlException( u'Response processing error: {}', touc(e) )

