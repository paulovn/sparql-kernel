SPARQL kernel
=============

This module installs a Jupyter kernel for `SPARQL`_. It allows sending queries 
to an SPARQL endpoint and fetching & presenting the results in a notebook.

It is implemented as a `Jupyter wrapper kernel`_, by using the Python 
`SPARQLWrapper`_ & `rdflib`_ packages.


Requirements
------------

The kernel has only been tried with Jupyter 4.x. It works with Python 2.7 and
Python 3 (tested with Python 3.6).

The above mentioned `SPARQLWrapper`_ & `rdflib`_ Python packages are required
dependencies (they are marked as such, so they will automatically be installed
with the package if needed).

An optional dependency is `Graphviz`_, needed to create diagrams for RDF result 
graphs (Graphviz's ``dot`` program must be available for that to work).


Installation
------------

You will need Jupyter >= 4.0. The module is installable via ``pip``.

The installation process requires two steps:

1. Install the Python package::

     pip install sparqlkernel

2. Install the kernel into Jupyter::

     jupyter sparqlkernel install [--user] [--logdir <dir>]


The ``--user`` option will install the kernel in the current user's personal
config, while the generic command will install it as a global kernel (but
needs write permissions in the system directories).

Additionally, the ``--logdir <dir>`` option will define the default directory to
use for logfiles (it can be overriden when executing the kernel by defining
the ``LOGDIR`` environment variable). By default it will use the system
temporal directory.

Note that kernel installation also installs some custom CSS and a modification
for a Pygments highlighter; its purpose is to improve the layout of the kernel
results as they are presented in the notebook and to improve conversion to
other formats (HTML). But it also means that the rendered notebook will look 
slightly different in a Jupyter deployment in which the kernel has not been 
installed, or within an online viewer.

The ``examples`` subdirectory contains some notebook examples (again, they will
look slightly different if viewed on a running kernel). They can also be viewed
through the `online Notebook viewer`_.

To uninstall, perform the inverse operations (in reverse order), to uninstall
the kernel from Jupyter and to remove the Python package::

     jupyter sparqlkernel remove
     pip uninstall sparqlkernel



Syntax
------

The kernel implements the standard SPARQL primitives: ``SELECT``, ``ASK``, 
``DESCRIBE``, ``CONSTRUCT``. Once the endpoint is defined (see magics below), 
just write a SPARQL valid query in a cell and execute it; the query will be 
sent to the endpoint and the results printed out.

The kernel features keyword autocompletion (TAB key), as well as contextual 
help (Shift-TAB). This is unfinished work: completion is currently done as 
isolated SPARQL keywords (no SPARQL syntax context is used) and only a few 
keywords have contextual help, as of now. 

It also installs menu entries in the HELP menu pointing to SPARQL documentation.


Execution
---------

The query results are displayed in the notebook as cell results; there are a 
number of choices for the display format, controlled via magics (see below).

Each SPARQL query is immediately launched, and once the results are printed out it 
is forgotten. Cells are thus completely independent from each other (except for
magics, which are persistent).

When a notebook is fully executed (e.g. *Cells* -> *Run all*), all code cells
in the notebook, and hence all queries, are executed in sequence. To avoid
execution of any particular cell, its type can be changed to RAW cell instead of
CODE cell (in *Cells* -> *Cell Type* -> *Raw*).


Magics
------

The kernel behaviour can be controlled by the use of line magics (lines
starting with ``%``). See the `magics documentation`_ for details.


Logging
-------

Settings defined by magics are always printed out in the cell result area
(in red type) to inform what are the conditions in which a query is
sent. Additionally, it is possible write logs that contain additional debug
information.

The logging level is controlled by the ``%log`` magic. All logs are written to
a single file, with the name ``sparqlkernel.log``. Its default place is the
machine temporal directory (e.g. ``/tmp`` in Linux, or ``C:/TMP`` in Windows).
There are two possibilities to change its location:

* When installing the kernel, use the ``--logdir <dir>`` option
* Before starting Jupyter, define the ``LOGDIR`` environment variable.



..  _SPARQL: https://www.w3.org/TR/sparql11-overview/
.. _Jupyter wrapper Kernel: http://jupyter-client.readthedocs.io/en/latest/wrapperkernels.html
.. _SPARQLWrapper: https://rdflib.github.io/sparqlwrapper/
.. _rdflib: https://github.com/RDFLib/rdflib
.. _Graphviz: http://www.graphviz.org/
.. _online Notebook viewer: http://nbviewer.jupyter.org/github/paulovn/sparql-kernel/blob/master/examples/
.. _magics documentation: doc/magics.rst
