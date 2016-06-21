"""
The class used to manage the connection to SPARQL endpoint: send queries and
format results for notebook display. Also process all the defined magics
"""
from __future__ import print_function

from IPython.utils.tokenutil import token_at_cursor, line_at_cursor
from ipykernel.kernelbase import Kernel
from traitlets import List
from itertools import izip, chain
import logging
from logging.config import dictConfig
import json

import logging
import pprint
import codecs
import SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import SPARQLWrapperException
from rdflib import Graph, URIRef, Literal

from .constants import __version__, LANGUAGE, DEFAULT_TEXT_LANG
from .utils import is_collection, KrnlException, div, escape
from .language import sparql_names, sparql_help
from .drawgraph import draw_graph

# IPython.core.display.HTML


# Valid mime types (depending of what we want)
mime_type = { SPARQLWrapper.JSON :  ['application/sparql-results+json',
                                     'text/javascript'],
              SPARQLWrapper.N3 :    ['text/rdf+n3', 
                                     'text/turtle', 'application/x-turtle'],
              SPARQLWrapper.RDF :   ['text/rdf'],
              SPARQLWrapper.TURTLE: ['text/turtle', 'application/x-turtle'],
              SPARQLWrapper.XML :   ['application/sparql-results+xml'],
}

# ----------------------------------------------------------------------

# The list of implemented magics with their help, as a pair [param,help-text]
magics = { 
    '%lsmagics' : [ '', 'list all magics'], 
    '%endpoint' : [ 'url', 'set SPARQL endpoint. REQUIRED.'],
    '%prefix' :   [ 'uri', 'set a persistent URI prefix for all queries'], 
    '%graph' :    [ 'uri', 'set default graph for the queries' ],
    '%format' :   [ 'JSON | N3 | default', 'set requested result format' ],
    '%display' :  [ 'raw | table [withtypes] | diagram [svg|png]', 
                    'set display format' ],
    '%lang' :     [ '<lang> [...] | default | all',
                    'language(s) preferred for labels' ],
    '%show' :     [ '<n> | all',
                    'maximum number of shown results' ],
    '%outfile' :  [ 'filename', 'save raw output to a file'],
    '%log' :      [ 'level', 'set logging level'],
}

# The full list of all magics
magic_help = ('Available magics:\n' + 
              '  '.join( sorted(magics.keys()) ) + 
              '\n\n' +
              '\n'.join( ('{0} {1} : {2}'.format(k,*magics[k]) 
                          for k in sorted(magics) ) ) )


# ----------------------------------------------------------------------

def save_to_file( result, outname ):
    """
    Save data to an output file
    """
    with open(outname,'w') as f:
        f.write( result )


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
      @return (int,unicode): a pair number-of-rendered-rows, html-table
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
    languages = set( [ row[c].get('xml:lang') for c in hdr if
                       row[c]['type'] == 'literal' ] )
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
        yield ( (row[c]['value'], jtype(row[c])) for c in hdr )


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
    if cfg.out:
        save_to_file( json.dumps(result,encoding='utf-8'), cfg.out )

    head = result['head']
    if 'results' not in result:
        if 'boolean' in result:
            r = 'Result: {}'.format(result['boolean'])
        else:
            r = 'unsupported result: \n' + unicode(result)
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
        data = {'text/plain' : unicode(pprint.pformat(result)) }
    
    return { 'data': data ,
             'metadata' : {} }


def render_n3( result, cfg, **kwargs ):
    """
    Render for output a result in N3 format
    """
    g = Graph()
    g.parse( data=result, format='n3' )
    if cfg.out:
        save_to_file( g.serialize(format='nt',encoding='utf-8'), cfg.out )

    if cfg.dis in ('png','svg') :
        try:
            return { 'data' : draw_graph(g,fmt=cfg.dis,lang=cfg.lan), 
                     'metadata' : {}  }
        except Exception as e:
            raise KrnlException( 'Exception while drawing graph: {!r}', e )
    elif cfg.dis == 'table':
        it = rdf_iterator(g,add_vtype=cfg.typ, lang=cfg.lan)
        n, data = html_table(it,limit=cfg.lmt, withtype=cfg.typ)
        if cfg.lmt:
            data += div( 'Shown: {}, Total rows: {}', n, len(g), css="tinfo" )
        data = {'text/html' : div(data) }
    else:
        data = { 'text/plain' : g.serialize(format='nt').decode('utf-8') }

    return { 'data': data,
             'metadata' : {} }

        

# ----------------------------------------------------------------------

class CfgStruct:
    """
    A simple class containing a bunch of fields
    """
    def __init__(self, **entries): self.__dict__.update(entries)


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
                              grh=None, dis=None, typ=False, lan=[] )

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
                         'DEFAULT' : None }
            try:
                fmt = param.upper()
                self.cfg.fmt = fmt_list[fmt]
            except KeyError:
                raise KrnlException( 'unsupported format: {}\nSupported formats are: {!s}', param, fmt_list.keys() )
            return ['Return format: {}', fmt], 'magic'

        elif cmd == 'lang':

            self.cfg.lan = DEFAULT_TEXT_LANG if param == 'default' else [] if param=='all' else param.split()
            return ['Label preferred languages: {}', self.cfg.lan], 'magic'

        elif cmd in 'graph':

            self.cfg.grh = param if param else None
            return [ 'Default graph: {}', param if param else 'None' ], 'magic'

        elif cmd == 'display':

            v = param.lower().split(None, 1)            
            if len(v) == 0 or v[0] not in ('table','raw','graph','diagram'):
                raise KrnlException( 'invalid %display command: {}', param )

            msg_extra = ''
            if v[0] not in ('diagram','graph'):
                self.cfg.dis = v[0]
                self.cfg.typ = len(v)>1 and v[1].startswith('withtype')
                if self.cfg.typ and self.cfg.dis == 'table':
                    msg_extra = '\nShow Types: on'
            elif len(v) == 1:
                self.cfg.dis = 'svg'
            else:
                if v[1] not in ('png','svg'):
                    raise KrnlException( 'invalid graph format: {}', param )
                self.cfg.dis = v[1]
            return [ 'Display: {}{}', self.cfg.dis, msg_extra  ], 'magic'

        elif cmd == 'outfile':

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


    def query( self, query, silent=False ):
        """
        Launch an SPARQL query, process & convert results and return them
        """
        if self.srv is None:
            raise KrnlException( 'no endpoint defined')             

        if self.log.isEnabledFor(logging.DEBUG):
            self.log.debug( "%50s%s", query, '...' if len(query)>50 else '' )

        # Add to the query all predefined SPARQL prefixes
        if self.cfg.pfx:
            prefix = '\n'.join( ( 'PREFIX {} {}'.format(*v) 
                                  for v in self.cfg.pfx(iteritems) ) )
            query = prefix  + '\n' + code

        # Set the query
        self.srv.resetQuery()
        qup = query.upper()
        fmt = self.cfg.fmt if self.cfg.fmt else SPARQLWrapper.N3 if 'DESCRIBE' in qup or 'CONSTRUCT' in qup else SPARQLWrapper.JSON
        self.srv.setReturnFormat( fmt )
        if self.cfg.grh:
            self.srv.addParameter("default-graph-uri",self.cfg.grh)
        self.srv.setQuery( query )

        if not silent or self.cfg.out:
            try:
                # Launch query
                res = self.srv.query()
                # Check we received the MIME type we expect
                expected = set( mime_type[fmt] )
                info = res.info()
                self.log.debug( u"Response info: %s", info )
                got = info['content-type'].split(';')[0]
                if got not in expected:
                    raise KrnlException('Unexpected response format: {!s}',got)
                # Convert result
                res = res.convert()
            except KrnlException:
                raise
            except SPARQLWrapperException as e:
                raise KrnlException( u'SPARQL error: {!s}', e )
            except Exception as e:
                raise KrnlException( u'Query processing error: {!s}', e )

            # Render the result into the desired display format
            try:
                f = render_n3 if fmt == SPARQLWrapper.N3 else render_json
                r = f( res, self.cfg )
                if not silent:
                    return r
            except Exception as e:
                raise KrnlException( 'Response processing error: {!s}', e )

