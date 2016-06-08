"""

Convert an RDF graph into an image for displaying in the notebook, via GraphViz
It has two parts:
  - conversion from rdf into dot language. Code based in rdflib.utils.rdf2dot
  - rendering of the dot graph into an image. Code based on 
    ipython-hierarchymagic, which in turn bases it from Sphinx
    See https://github.com/tkf/ipython-hierarchymagic


License for RDFLIB
------------------
Copyright (c) 2002-2015, RDFLib Team
See CONTRIBUTORS and http://github.com/RDFLib/rdflib
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

  * Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.

  * Redistributions in binary form must reproduce the above
copyright notice, this list of conditions and the following
disclaimer in the documentation and/or other materials provided
with the distribution.

  * Neither the name of Daniel Krech nor the names of its
contributors may be used to endorse or promote products derived
from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


License for ipython-hierarchymagic
----------------------------------
ipython-hierarchymagic is licensed under the term of the Simplified
BSD License (BSD 2-clause license), as follows:
Copyright (c) 2012 Takafumi Arakaki
All rights reserved.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:
Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.
Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


License for Sphinx
------------------
`run_dot` function and `HierarchyMagic._class_name` method in this
extension heavily based on Sphinx code `sphinx.ext.graphviz.render_dot`
and `InheritanceGraph.class_name`.
Copyright notice for Sphinx can be found below.
Copyright (c) 2007-2011 by the Sphinx team (see AUTHORS file).
All rights reserved.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:
* Redistributions of source code must retain the above copyright
  notice, this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright
  notice, this list of conditions and the following disclaimer in the
  documentation and/or other materials provided with the distribution.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import errno
import StringIO
import base64
import collections
import re

from IPython.core.display import display_png, display_svg
import rdflib.tools.rdf2dot as r2d
import rdflib

from .utils import escape

# ------------------------------------------------------------------------

LABEL_PROPERTIES = [
    rdflib.RDFS.label,
    rdflib.URIRef('http://schema.org/name'), 
    rdflib.URIRef('http://www.w3.org/2000/01/rdf-schema#label'),
    rdflib.URIRef('http://www.w3.org/2004/02/skos/core#prefLabel'),
    rdflib.URIRef("http://purl.org/dc/elements/1.1/title"),
    rdflib.URIRef("http://xmlns.com/foaf/0.1/name"),
    rdflib.URIRef("http://www.w3.org/2006/vcard/ns#fn"),
    rdflib.URIRef("http://www.w3.org/2006/vcard/ns#org"),
]




def label(x, gr, preferred_languages=None):
    """
    Return the best available label in the graph for the passed entity.
    If a set of preferred languages is given, try them in order. If none is
    found, an arbitrary language will be chosen
    """
    # Find all labels & their language
    labels = { l.language : l
               for labelProp in LABEL_PROPERTIES
               for l in gr.objects(x,labelProp) }
    if labels:
        #return '/'.join( u'{}:{}'.format(*i) for i in labels.iteritems() )
        if preferred_languages:
            for lang in preferred_languages:
                if lang in labels:
                    return labels[lang]
        return labels.itervalues().next()

    # No labels available. Try to generate a QNAME, or else, the string itself
    try:                                                                    
        return gr.namespace_manager.compute_qname(x)[2].replace('_',' ')
    except:
        # Attempt to extract the trailing part of an URI
        m = re.search( '([^/]+)$', x )
        return m.group(1).replace('_',' ') if m else x



def rdf2dot( g, stream, opts={} ):
    """
    Convert the RDF graph to DOT
    Write the dot output to the stream
    """

    lang = opts.get('lang')
    nodes = {}
    links = []

    def node(x):
        if x not in nodes:
            nodes[x] = "node%d" % len(nodes)
        return nodes[x]

    def qname(x, g):
        try:
            q = g.compute_qname(x)
            return q[0] + ":" + q[2]
        except:
            return x

    stream.write(u"digraph { \n node [ fontname=\"DejaVu Sans\" ] ; \n")

    # Write all edges. In the process make a list of all nodes
    for s, p, o in g:
        sn = node(s)
        if p == rdflib.RDFS.label:
            continue
        # If this triple is between two nodes, create a link
        if isinstance( o, (rdflib.URIRef,rdflib.BNode) ):
            on = node(o)
            opstr = u'\t%s -> %s [ arrowhead="open", color="#9FC9E5", fontsize=10, fontcolor="#204080", label="%s" ] ;\n'
            stream.write( opstr % (sn, on, qname(p,g)) )

    # Write all nodes
    for u, n in nodes.items():
        stream.write(u"# %s %s\n" % (u, n))
        if isinstance(u, rdflib.URIRef):
            opstr = u"%s [ shape=none, color=%s, href=\"%s\", fontsize=11, label=\"%s\" ] \n" % (n, r2d.NODECOLOR, u, escape(label(u,g,lang),True) )
        else:
            opstr = u"%s [ shape=none, color=%s, fontsize=11, label=\"%s\" ] \n" % (n, r2d.NODECOLOR, escape(label(u,g)) )
        stream.write(opstr)

    stream.write("}\n")



# ------------------------------------------------------------------------

EPIPE  = getattr(errno, 'EPIPE', 0)
EINVAL = getattr(errno, 'EINVAL', 0)


def run_dot( code, gv_options=[], **kwargs ):

    # mostly copied from sphinx.ext.graphviz.render_dot
    import os
    from subprocess import Popen, PIPE

    dot_args = [ kwargs.get('prg','dot') ] + gv_options + ['-T', kwargs.get('fmt','svg') ]
    if os.name == 'nt':
        # Avoid opening shell window.
        # * https://github.com/tkf/ipython-hierarchymagic/issues/1
        # * http://stackoverflow.com/a/2935727/727827
        p = Popen(dot_args, stdout=PIPE, stdin=PIPE, stderr=PIPE,
                  creationflags=0x08000000)
    else:
        p = Popen(dot_args, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    wentwrong = False
    try:
        # Graphviz may close standard input when an error occurs,
        # resulting in a broken pipe on communicate()
        stdout, stderr = p.communicate(code.encode('utf-8'))
    except OSError as err:
        if err.errno != EPIPE:
            raise
        wentwrong = True
    except IOError as err:
        if err.errno != EINVAL:
            raise
        wentwrong = True
    if wentwrong:
        # in this case, read the standard output and standard error streams
        # directly, to get the error message(s)
        stdout, stderr = p.stdout.read(), p.stderr.read()
        p.wait()
    if p.returncode != 0:
        raise RuntimeError(u'dot exited with error:\n[stderr]\n{0}'
                           .format(stderr.decode('utf-8')))
    return stdout


# ------------------------------------------------------------------------


def draw_graph( g, fmt='svg', prg='dot', lang=None, options=[] ):
    """
    Draw an RDF graph as an image
    """
    # Convert RDF to Graphviz
    buf = StringIO.StringIO()
    rdf2dot( g, buf, { 'lang' : lang } )

    #import codecs
    #with codecs.open('/tmp/sparqlkernel-img.dot','w',encoding='utf-8') as f:
    #    f.write( buf.getvalue() )
    
    # Now use Graphviz to generate the graph
    image = run_dot( buf.getvalue(), options=options, fmt=fmt, prg=prg )

    #with open('/tmp/sparqlkernel-img.'+fmt,'w') as f:
    #    f.write( image )

    # Return it
    if fmt == 'png':
        return { 'image/png' : base64.b64encode(image).decode('ascii') }
    elif fmt == 'svg':
        return { 'image/svg+xml' : image }

