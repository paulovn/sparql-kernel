SPARQL kernel magics
********************

A number of line magics (lines starting with ``%``) can be used to control the 
kernel behaviour. These line magics must be placed at the start of the cell, 
and there can be more than one per cell.
Valid combinations are thus:

* a cell with only a SPARQL query,
* a cell consisting only of magics,
* and a cell containing both magics and then a SPARQL query (but after the 
  first SPARQL keyword the cell is assumed to be in SPARQL mode, and line 
  magics will *not* be recognized as such).

Comment lines (lines starting with ``#``) can be freely interspersed between 
line magics or SPARQL queries.

Magics also feature autocompletion and contextual help. Furthermore, there is 
a special magic ``%lsmagics``; when executed on a cell it will output the list 
of all currently available magics. The same info can be obtained by requesting
contextual help (i.e. Shift-TAB) on a line containing only a percent sign.

Magics are explained in the following sections (the most up-to-date set is
always available inside the notebook, by using the help or autocompletion
features). In the format specification, a string inside angle brackets,
e.g. ``<string>`` refers to an arbitrary string; all else are literal strings
that must be written as is.

A magic sets persistent behaviour: once the cell containing the magic is
executed, it is active for all subsequent SPARQL executions.


1. General
==========
  
``%endpoint``
-------------

This magic is special in the sense that it is compulsory: there needs to be an 
endpoint defined *before* the first SPARQL query is launched, otherwise the 
query will fail.

Its syntax is::

    %endpoint <url>

and it simply defines the SPARQL endpoint for all subsequent queries. 
It remains active until superseded by another ``%endpoint`` magic.



``%lsmagics``
-------------

List all available magics with its syntax and a short description



``%log``
--------

Set logging level. Available levels are: *critical*, *error*,  *warning*,
*info*, *debug*.


2. Request creation
===================


``%format``
-----------

Sets the data format requested to the SPARQL endpoint::

    %format JSON | XML | N3  | any | default | none

where:

* ``JSON`` requests JSON format (*application/sparql-results+json* or equivalent)
* ``XML`` requests XML format (*application/sparql-results+xml*)
* ``N3`` requests the endpoint to provide results in *text/rdf+n3* format
* ``any`` lets the endpoint return any format it pleases, by sending multiple
  accepted formats (note that if the returned format is not JSON, SPARQL-XML
  or N3, it will be rendered as raw text)
* ``default`` selects a default format depending on the requested SPARQL
  operation (N3 for ``DESCRIBE`` and ``CONSTRUCT``, JSON for ``SELECT``, *any*
  for the rest)
* ``none`` removes any format indication from the query parameters, leaving it
  all to content negotiation.    

Note that format specification for SPARQL endpoints is tricky, since there is
no real standard for it. This is resolved via `SPARQLWrapper`_, which does two
things simultaneously:

* sends three query parameters ``format``, ``output`` and ``results`` with the
  desired format
* adds an HTTP *Accept* header with the accepted MIME type(s) for the requested
  format


Manual control
..............

The set of possible requested formats that can be used is limited by the
validation code in SPARQLWrapper, so there might be an endpoint that demands
a combination that cannot be set with the ``%format`` magic.

As a workaround, if a particular endpoint needs a custom format specification,
it might be solved by

* setting ``%format`` to ``none`` (which will suppress the automatic format request
  in the query parameters)
* adding a manual ``%qparam <name> <format>`` magic with the needed format
  specification, as requested by the endpoint
* adding an ``%http_header Accept <type/subtype>`` magic with the desired accepted
  MIME type(s)

E.g., assuming the backend needs a ``result_format`` parameter in the query
string, and that it should contain a MIME type, one possible set of magics
would be::

  %format none
  %qparam result_format application/json
  %http_header Accept application/json,application/sparql-results+json

where we include in the *Accept* HTTP header all MIME types the endpoint might
produce.
  

``%http_header``
----------------

Sends an arbitrary HTTP header to the endpoint. Its syntax is::

  %http_header <name> <value>

If ``<value>`` is not present, the existing HTTP header is removed for
subsequent queries. The header name in ``<name>`` is case insensitive.

Example::

  %http_header Accept application/json


``%qparam``
-----------

Defines a custom additional query parameter to be sent with every request. Its
syntax is::

  %qparam <name> <value>

which will add the ``<name>=<value>`` parameter to every subsequent query (it can
be used e.g. to send API keys, or any parameter required by the endpoint).

Any number of parameters can be defined; they will all be added to the queries
executed after their definitions. To remove a parameter, use a line with no
value::

  %qparam <name>

  
``%auth``
---------

Define HTTP authentication to send to the backend. Its syntax is::

   %auth (basic | digest) <username> <password>

Once defined, it will be sent to the backend on every subsequent query. To
remove a defined authentication, just use::

   %auth none


3. Query formulation
====================
   

``%prefix``
-----------

Set a URI prefix for all subsequent queries. Its syntax is::

  %prefix <name> <uri>

Its effect is the same as using the SPARQL ``PREFIX`` keyword, only that once
defined it is automatically prepended to *all* queries in cells below it.

To remove a prefix, use a magic without URI::

  %prefix <name>


``%graph``
----------

Set the default graph for all queries, as::

  %graph <uri>

It is equivalent to using the ``FROM`` SPARQL keyword in a query, but when it
is defined is automatically sent in all queries.


``%header``
-----------

Prepends a certain textual header line to all sparql queries. This can be used
to set some (potentially non SPARQL) command in the query.

For instance Virtuoso endpoints accept the *DEFINE* keyword which can be used
to trigger the server reasoner.

The syntax is::

   %header <arbitrary line including spaces>

Any number of header magics may be defined; each one defines an arbitrary line
to be prepended to all SPARQL queries. They are sent *before* any defined
``%PREFIX`` magics.

The magic::

  %header off

removes all defined headers.



4. Rendering
============
  

``%display``
------------

Sets the output rendering shape::

    %display raw | table [withtypes] | diagram [svg|png] [withliterals]

There are three possible display shapes:

* ``raw`` outputs the literal text returned by the SPARQL endpoint, in the
  format that was requested (see ``%format`` magic)
* ``table`` generates a table with the result. The optional ``withtypes``
  modifier adds to each column an additional column that shows the data
  type for each value
* ``diagram`` takes the RDF graph returned (makes sense only for N3 result
  format) and generates an image with a rendering of the graph. For it to
  work, the ``dot`` program from GraphViz must be available in the search path.
  The modifier selects the image format. Default is SVG, which usually works
  much better (PNG quality is lower, image size is fixed and cannot contain
  hyperlinks).

Default is ``table``. Note that if the result format is not a supported format
for a table or diagram representation (i.e. it is not JSON/XML or N3), then raw
format will be used.


``%show``
---------

Maximum number of results shown, as::

   %show N

Default is 20. It is also possible to use::
    
   %show all


``%lang``
---------

Selects the language chosen for the RDF labels, in either the *table* or the
*diagram* formats


``%outfile``
------------

Saves the raw result of every query to a file::

  %outfile <filename>

Use a full path for the filename. If the name contains a `%d` part, it will be
used to substitute the cell number, i.e. the magic::

  %outfile /data/query-%03d.txt

will save each executed query to files ``/data/query-001.txt``,
``/data/query-002.txt``, etc.

Using::

  %outfile off

will cancel file saving.
  

..  _SPARQL: https://www.w3.org/TR/sparql11-overview/
.. _Jupyter wrapper Kernel: http://jupyter-client.readthedocs.io/en/latest/wrapperkernels.html
.. _SPARQLWrapper: https://rdflib.github.io/sparqlwrapper/
.. _rdflib: https://github.com/RDFLib/rdflib
.. _Graphviz: http://www.graphviz.org/
.. _online Notebook viewer: http://nbviewer.jupyter.org/github/paulovn/sparql-kernel/blob/master/examples/
