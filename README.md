= SPARQL kernel

This module installs a Jupyter kernel for [SPARQL][]. It allows sending queries 
to an SPARQL endpoint and fetching & presenting the results in a notebook.


It is implemented as a [Jupyter wrapper kernel][], by using the Python 
[SPARQLWrapper][] & [rdflib][] packages

== Requirements

The kernel has only been tried with Python 2.7 and Jupyter 4.1. It might work 
with Python 2.6 (perhaps with some tiny changes); it is unlikely to work with 
Python 3 (most of the problems will come with unicode buffers, which is common 
in SPARQL responses).

The above mentioned [SPARQLWrapper][] & [rdflib][] are dependencies (they will 
be installed with the package). An optional dependency is [Graphviz][], needed 
to create diagrams of RDF result graphs (Graphviz's `dot` program must be 
available for that to work).

== Installation


== Syntax

The kernel implements the standard SPARQL primitives: SELECT, ASK, DESCRIBE, 
CONSTRUCT. Once the endpoint is defined (see magics below), just write a SPARQL
valid query in a cell and execute it; the query will be sent to the endpoint
and the results printed out.

The kernel features keyword autocompletion (TAB key), as well as contextual 
help (Shift-TAB). This is unfinished work: completion is done by isolated 
SPARQL keywords (no SPARQL syntax context is used) and only a few keywords 
have contextual help, as of now. 

It also installs menu entries in the HELP menu pointing to SPARQL documentation


== Output format

The query results are displayed in the notebook as cell results; there are a 
number of choices for the display format, controlled via magics (see below)


== Magics 

A number of line magics (lines starting with `%`) are defined to control the 
kernel behaviour. These magics must be placed at the start of the cell. 
Valid combinations are:
  * to include several line magics in a cell,
  * a cell consisting only of magics (or magics and comments), 
  * and a cell containing magics and a SPARQL query. 
But after the first SPARQL keyword the cell is assumed to be in SPARQL mode, 
and line magics will *not* be recognized as such.

Magics also feature autocompletion and contextual help. Furthermore, there is 
a spacial magic `%lsmagics`; when executed on a cell it will output the list 
of all currently available magics (the same info can be obtained by using 
contextual help i.e. Shift-TAB on a line containing only a percent sign).


=== `%endpoint`

This magic is special in the sense that is compulsory: there needs to be an 
endpoint defined _before_ the first SPARQL query is launched, otherwise the 
query will fail.

Its syntax is:

   %endpoint <url>

and it simply defines the SPARQL endpoint for al subsequent queries. 
It remains active until superceded by another `%endpoint` magic.



  [SPARQL]: https://www.w3.org/TR/sparql11-overview/
  [Jupyter wrapper Kernel]: http://jupyter-client.readthedocs.io/en/latest/wrapperkernels.html
  [SPARQLWrapper]: https://rdflib.github.io/sparqlwrapper/
  [rdflib]: https://github.com/RDFLib/rdflib
  [Graphviz]: http://www.graphviz.org/
