"""
The class used to manage the connection to SPARQL endpoint: send queries and
format results for notebook display.
"""

from __future__ import print_function

import sys
import io
import re
import json
import datetime
import logging
import os.path
import urllib
from operator import itemgetter

from IPython.utils.tokenutil import token_at_cursor, line_at_cursor
from traitlets import List

import SPARQLWrapper
from SPARQLWrapper.KeyCaseInsensitiveDict import KeyCaseInsensitiveDict
from SPARQLWrapper.SPARQLExceptions import SPARQLWrapperException
from SPARQLWrapper.Wrapper import _SPARQL_XML, _SPARQL_JSON
from rdflib import ConjunctiveGraph, Literal
from rdflib.parser import StringInputSource

from .constants import DEFAULT_TEXT_LANG
from .utils import is_collection, KrnlException, div, escape
from .drawgraph import draw_graph

# IPython.core.display.HTML

PY3 = sys.version_info[0] == 3
if PY3:
    unicode = str
    touc = str
else:
    touc = lambda x: str(x).decode('utf-8', 'replace')


# Valid mime types in the SPARQL response (depending on what we requested)
mime_type = {SPARQLWrapper.JSON:   set(_SPARQL_JSON),
             SPARQLWrapper.N3:     set(['text/rdf+n3', 'text/turtle', 
                                        'application/x-turtle',
                                        'application/rdf+xml']),
             SPARQLWrapper.RDF:    set(['text/rdf', 'application/rdf+xml']),
             SPARQLWrapper.TURTLE: set(['text/turtle', 'application/x-turtle']),
             SPARQLWrapper.XML:    set(_SPARQL_XML)
}

# ----------------------------------------------------------------------

def cleanhtml(raw_html, ctype):
    '''
    Rough cleanup of HTML code
    '''
    m = re.search(r'charset\s*=\s*(\S+)', ctype)
    charset = m.group(1) if m else 'utf-8'
    html = raw_html.decode(charset)
    html = re.sub(r'<style>.+</style>', '', html, flags=re.S)
    html = re.sub(r'<.*?>', '', html, flags=re.S)
    return re.sub(r'[\n]+', '\n', html, flags=re.S)


def html_elem(e, ct, withtype=False):
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
    if e[1] in ('uri', 'URIRef'):
        html = u'<{0} class=val><a href="{1}" target="_other">{2}</a></{0}>'.format(ct, e[0], escape(e[0]))
    else:
        html = u'<{0} class=val>{1}</{0}>'.format(ct, escape(e[0]))
    # Create the optional cell for the type
    if withtype:
        html += u'<{0} class=typ>{1}</{0}>'.format(ct, e[1])
    return html


def html_table(data, header=True, limit=None, withtype=False):
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
        html += '\n'.join((html_elem(c, ct, withtype) for c in row))
        html += u'</tr>'
        rc = 'even' if rc == 'odd' else 'odd'
        ct = 'td'
        if limit:
            limit -= 1
            if not limit:
                break
    return (0, '') if rn < 0 else (rn+1-header, html+u'</table>')


# ----------------------------------------------------------------------

def jtype(c):
    """
    Return the a string with the data type of a value, for JSON data
    """
    ct = c['type']
    return ct if ct != 'literal' else '{}, {}'.format(ct, c.get('xml:lang'))


def gtype(n):
    """
    Return the a string with the data type of a value, for Graph data
    """
    t = type(n).__name__
    return str(t) if t != 'Literal' else 'Literal, {}'.format(n.language)


def lang_match_json(row, hdr, accepted_languages):
    '''Find if the JSON row contains acceptable language data'''
    if not accepted_languages:
        return True
    languages = set([row[c].get('xml:lang') for c in hdr
                     if c in row and row[c]['type'] == 'literal'])
    return (not languages) or (languages & accepted_languages)


def lang_match_rdf(triple, accepted_languages):
    '''Find if the RDF triple contains acceptable language data'''
    if not accepted_languages:
        return True
    languages = set([n.language for n in triple if isinstance(n, Literal)])
    return (not languages) or (languages & accepted_languages)


XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'

def lang_match_xml(row, accepted_languages):
    '''Find if the XML row contains acceptable language data'''
    if not accepted_languages:
        return True
    column_languages = set()
    for elem in row:
        lang = elem[0].attrib.get(XML_LANG, None)
        if lang:
            column_languages.add(lang)
    return (not column_languages) or (column_languages & accepted_languages)


def json_iterator(hdr, rowlist, lang, add_vtype=False):
    """
    Convert a JSON response into a double iterable, by rows and columns
    Optionally add element type, and filter triples by language (on literals)
    """
    # Return the header row
    yield hdr if not add_vtype else ((h, 'type') for h in hdr)
    # Now the data rows
    for row in rowlist:
        if lang and not lang_match_json(row, hdr, lang):
            continue
        yield ((row[c]['value'], jtype(row[c])) if c in row else ('', '')
               for c in hdr)


def rdf_iterator(graph, lang, add_vtype=False):
    """
    Convert a Graph response into a double iterable, by triples and elements.
    Optionally add element type, and filter triples by language (on literals)
    """
    # Return the header row
    hdr = ('subject', 'predicate', 'object')
    yield hdr if not add_vtype else ((h, 'type') for h in hdr)
    # Now the data rows
    for row in graph:
        if lang and not lang_match_rdf(row, lang):
            continue
        yield ((unicode(c), gtype(c)) for c in row)


def render_json(result, cfg, **kwargs):
    """
    Render to output a result in JSON format
    """
    result = json.loads(result.decode('utf-8'))
    head = result['head']
    if 'results' not in result:
        if 'boolean' in result:
            r = u'Result: {}'.format(result['boolean'])
        else:
            r = u'Unsupported result: \n' + unicode(result)
        return {'data': {'text/plain': r},
                'metadata': {}}

    vars = head['vars']
    nrow = len(result['results']['bindings'])
    if cfg.dis == 'table':
        j = json_iterator(vars, result['results']['bindings'], set(cfg.lan),
                          add_vtype=cfg.typ)
        n, data = html_table(j, limit=cfg.lmt, withtype=cfg.typ)
        data += div('Total: {}, Shown: {}', nrow, n, css="tinfo")
        data = {'text/html': div(data)}
    else:
        result = json.dumps(result,
                            ensure_ascii=False, indent=2, sort_keys=True)
        data = {'text/plain': unicode(result)}

    return {'data': data,
            'metadata': {}}


def xml_row(row, lang):
    '''
    Generator for an XML row
    '''
    for elem in row:
        name = elem.get('name')
        child = elem[0]
        ftype = re.sub(r'\{[^}]+\}', '', child.tag)
        if ftype == 'literal':
            ftype = '{}, {}'.format(ftype, child.attrib.get(XML_LANG, 'none'))
        yield (name, (child.text, ftype))


def xml_iterator(columns, rowlist, lang, add_vtype=False):
    """
    Convert an XML response into a double iterable, by rows and columns
    Options are: filter triples by language (on literals), add element type
    """
    # Return the header row
    yield columns if not add_vtype else ((h, 'type') for h in columns)
    # Now the data rows
    for row in rowlist:
        if not lang_match_xml(row, lang):
            continue
        rowdata = {nam: val for nam, val in xml_row(row, lang)}
        yield (rowdata.get(field, ('', '')) for field in columns)


def render_xml(result, cfg, **kwargs):
    """
    Render to output a result in XML format
    """
    # Raw mode
    if cfg.dis == 'raw':
        return {'data': {'text/plain': result.decode('utf-8')},
                'metadata': {}}
    # Table
    try:
        import xml.etree.cElementTree as ET
    except ImportError:
        import xml.etree.ElementTree as ET
    root = ET.fromstring(result)
    try:
        ns = {'ns': re.match(r'\{([^}]+)\}', root.tag).group(1)}
    except Exception:
        raise KrnlException('Invalid XML data: cannot get namespace')
    columns = [c.attrib['name'] for c in root.find('ns:head', ns)]
    results = root.find('ns:results', ns)
    nrow = len(results)
    j = xml_iterator(columns, results, set(cfg.lan), add_vtype=cfg.typ)
    n, data = html_table(j, limit=cfg.lmt, withtype=cfg.typ)
    data += div('Total: {}, Shown: {}', nrow, n, css="tinfo")
    return {'data': {'text/html': div(data)},
            'metadata': {}}


def render_graph(result, cfg, **kwargs):
    """
    Render to output a result that can be parsed as an RDF graph
    """
    # Mapping from MIME types to formats accepted by RDFlib
    rdflib_formats = {'text/rdf+n3': 'n3',
                      'text/turtle': 'turtle',
                      'application/x-turtle': 'turtle',
                      'text/turtle': 'turtle',
                      'application/rdf+xml': 'xml',
                      'text/rdf': 'xml'
                      }


    try:
        got = kwargs.get('format', 'text/rdf+n3')
        fmt = rdflib_formats[got]
    except KeyError:
        raise KrnlException('Unsupported format for graph processing: {!s}', got)

    g = ConjunctiveGraph()
    g.load(StringInputSource(result), format=fmt)

    display = cfg.dis[0] if is_collection(cfg.dis) else cfg.dis
    if display in ('png', 'svg'):
        try:
            literal = len(cfg.dis) > 1 and cfg.dis[1].startswith('withlit')
            opt = {'lang': cfg.lan, 'literal': literal, 'graphviz': []}
            data, metadata = draw_graph(g, fmt=display, options=opt)
            return {'data': data,
                    'metadata': metadata}
        except Exception as e:
            raise KrnlException('Exception while drawing graph: {!r}', e)
    elif display == 'table':
        it = rdf_iterator(g, set(cfg.lan), add_vtype=cfg.typ)
        n, data = html_table(it, limit=cfg.lmt, withtype=cfg.typ)
        data += div('Shown: {}, Total rows: {}', n if cfg.lmt else 'all',
                    len(g), css="tinfo")
        data = {'text/html': div(data)}
    elif len(g) == 0:
        data = {'text/html': div(div('empty graph', css='krn-warn'))}
    else:
        data = {'text/plain': g.serialize(format='nt').decode('utf-8')}

    return {'data': data,
            'metadata': {}}



# ----------------------------------------------------------------------

class CfgStruct:
    """
    A simple class containing a bunch of fields. Equivalent to Python3
    SimpleNamespace
    """
    def __init__(self, **entries):
        self.__dict__.update(entries)

    def __repr__(self):
        return '<' + ' '.join('{}={!r}'.format(*kv)
                              for kv in self.__dict__.items()) + '>'


# ----------------------------------------------------------------------

class SparqlConnection(object):

    def __init__(self, logger=None):
        """
        Initialize an empty configuration
        """
        self.log = logger or logging.getLogger(__name__)
        self.srv = None
        self.log.info("START")
        self.cfg = CfgStruct(hdr=[], pfx={}, lmt=20, fmt=None, out=None, aut=None,
                             grh=None, dis='table', typ=False, lan=[], par={},
                             mth='GET', hhr=KeyCaseInsensitiveDict(), ept=None)


    def query(self, query, num=0, silent=False):
        """
        Launch an SPARQL query, process & convert results and return them
        """
        self.log.debug("CONFIG: %s", self.cfg)
        # Create server object, if needed
        if self.cfg.ept is None:
            raise KrnlException('no endpoint defined')
        elif self.srv is None or self.srv.endpoint != self.cfg.ept:
            self.srv = SPARQLWrapper.SPARQLWrapper(self.cfg.ept)

        # Add to the query all predefined SPARQL prefixes
        if self.cfg.pfx:
            prefix = '\n'.join(('PREFIX {} {}'.format(*v)
                                for v in self.cfg.pfx.items()))
            query = prefix + '\n' + query

        # Prepend to the query all predefined Header entries
        # The header should be before the prefix and other sparql commands
        if self.cfg.hdr:
            query = '\n'.join(self.cfg.hdr) + '\n' + query

        if self.log.isEnabledFor(logging.DEBUG):
            self.log.debug("\n%50s%s", query, '...' if len(query) > 50 else '')

        # Select requested format
        self.srv.setOnlyConneg(self.cfg.fmt is None)
        if self.cfg.fmt in (False, None):
            fmt_req = False
        elif self.cfg.fmt is not True:
            fmt_req = self.cfg.fmt
        elif re.search(r'\bselect\b', query, re.I):
            fmt_req = SPARQLWrapper.JSON
        elif re.search(r'\b(?:describe|construct)\b', query, re.I):
            fmt_req = SPARQLWrapper.N3
        else:
            fmt_req = False

        # Set the query
        self.srv.resetQuery()
        self.srv.setMethod(self.cfg.mth)
        self.log.debug(u'method=%s', self.cfg.mth)
        if self.cfg.aut:
            self.srv.setHTTPAuth(self.cfg.aut[0])
            self.srv.setCredentials(*self.cfg.aut[1:])
        else:
            self.srv.setCredentials(None, None)
        self.log.debug(u'request-format=%s  display=%s', fmt_req, self.cfg.dis)
        if fmt_req:
            self.srv.setReturnFormat(fmt_req)
        if self.cfg.grh:
            self.srv.addParameter("default-graph-uri", self.cfg.grh)
        for p in self.cfg.par.items():
            self.log.debug(u'qparameter=%s', p)
            self.srv.addParameter(*p)
        for n, v in self.cfg.hhr.items():
            self.log.debug(u'HTTP Header: %s=%s', n, v)
            self.srv.addCustomHttpHeader(n, v)

        self.srv.setQuery(query)

        if not silent or self.cfg.out:
            try:
                # Launch query
                start = datetime.datetime.utcnow()
                res = self.srv.query()
                now = datetime.datetime.utcnow()
                self.log.debug(u'response elapsed=%s', now-start)
                start = now

                # See what we got
                info = res.info()
                self.log.debug(u'response info: %s', info)
                fmt_got = info['content-type'].split(';')[0] if 'content-type' in info else None

                # Check we received a MIME type according to what we requested
                if fmt_req not in (True, False, None) and fmt_got not in mime_type[fmt_req]:
                    raise KrnlException(u'Unexpected response format: {} (requested: {})', fmt_got, fmt_req)

                # Get the result
                data = b''.join((line for line in res))

            except KrnlException:
                raise
            except SPARQLWrapperException as e:
                raise KrnlException(u'SPARQL error: {}', touc(e))
            except urllib.error.HTTPError as e:
                msg = e.read()
                ctype = e.headers.get('Content-Type', 'text/plain')
                if ctype.startswith('text/html'):
                    msg = cleanhtml(msg, ctype)
                raise KrnlException(u'HTTP error: {} {}: {}', e.code, e.reason,
                                    msg)
            except Exception as e:
                raise KrnlException(u'Query processing error: {!s}', e)

            # Write the raw result to a file
            if self.cfg.out:
                try:
                    outname = self.cfg.out % num
                except TypeError:
                    outname = self.cfg.out
                with io.open(outname, 'wb') as f:
                    f.write(data)

            # Render the result into the desired display format
            try:
                # Data format we will render
                fmt = (fmt_req if fmt_req else
                       SPARQLWrapper.JSON if fmt_got in mime_type[SPARQLWrapper.JSON] else
                       SPARQLWrapper.N3 if fmt_got in mime_type[SPARQLWrapper.N3] else
                       SPARQLWrapper.XML if fmt_got in mime_type[SPARQLWrapper.XML] else
                       'text/plain' if self.cfg.dis == 'raw' else
                       fmt_got if fmt_got in ('text/plain', 'text/html') else
                       'text/plain')
                #self.log.debug(u'format: req=%s got=%s rend=%s',fmt_req,fmt_got,fmt)

                # Can't process? Just write the data as is
                if fmt in ('text/plain', 'text/html'):
                    out = data.decode('utf-8') if isinstance(data, bytes) else data
                    r = {'data': {fmt: out}, 'metadata': {}}
                else:
                    f = render_json if fmt == SPARQLWrapper.JSON else render_xml if fmt == SPARQLWrapper.XML else render_graph
                    r = f(data, self.cfg, format=fmt_got)
                    now = datetime.datetime.utcnow()
                    self.log.debug(u'response formatted=%s', now-start)
                if not silent:
                    return r

            except Exception as e:
                raise KrnlException(u'Response processing error: {}', touc(e))
