"""
SPARQL language catalogs
"""

from itertools import chain


# ------------------------------------------------------------------------

sparql_keywords = [ 

    'SELECT', 'CONSTRUCT', 'ASK', 'DESCRIBE',
    'BASE', 'PREFIX', 
    'FROM',
    'LIMIT', 'OFFSET',
    'WHERE', 'FILTER', 'OPTIONAL', 'NOT', 'EXISTS',
    'UNION', 'MINUS', 'GROUP BY', 'VALUES', 'UNDEF',
    'BIND', 'AS', 
    'DISTINCT', 'REDUCED',
    'HAVING',
    'FROM NAMED', 'GRAPH',
    'ORDER BY', 'ASC', 'DESC',
    'COUNT', 'SUM', 'MIN', 'MAX', 'AVG', 'GROUP_CONCAT', 'SAMPLE',

    'LOAD', 'CLEAR', 'DROP', 'CREATE', 'ADD', 'MOVE', 'COPY', 'SILENT',
    'INSERT', 'DELETE',

    # SPARQL 1.1
    'SERVICE'
]

sparql_operators = [ 'bound', 'isIRI', 'isBlank', 'isLiteral',
                     'str', 'lang', 'datatype', 'sameTerm', 
                     'langMatches', 'regex',  ]


# All SPARQL reserved words
sparql_names = dict( ((k.lower(),k) for k in 
                      chain.from_iterable( (sparql_keywords,sparql_operators))
                  ) )

# ------------------------------------------------------------------------

# Dictionary containing preformatted help string for SPARQL keywords

sparql_help = {

    'SELECT' : 
r'''Returns all, or a subset of, the variables bound in a query
pattern match.

SELECT [DISTINCT | REDUCED] ( ?var | $var | * )
[FROM iri | FROM NAMED iri ]
WHERE { 
  TriplesBlock? ( ( GraphPatternNotTriples | Filter ) '.'? TriplesBlock? )* 
}
ORDER BY OrderCondition
LIMIT integer
OFFSET integer
''',

    'CONSTRUCT' :
r'''Returns an RDF graph constructed by substituting variables in a set of 
triple templates.
''',

    'ASK' :
r'''Returns a boolean indicating whether a query pattern matches or not.''',

    'DESCRIBE' :
r'''Returns an RDF graph that describes the resources found.

DESCRIBE ( VarOrIRIref+ | '*' ) 
DatasetClause* WhereClause? SolutionModifier'''
}


