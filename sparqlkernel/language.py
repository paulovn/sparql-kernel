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
    'USING', 'NAMED',
    'FROM NAMED', 'GRAPH',
    'ORDER BY', 'ASC', 'DESC',
    'COUNT', 'SUM', 'MIN', 'MAX', 'AVG', 'GROUP_CONCAT', 'SAMPLE',

    'LOAD', 'CLEAR', 'DROP', 'CREATE', 'ADD', 'MOVE', 'COPY', 'SILENT',
    'INSERT', 'DELETE',
    'INSERT DATA', 'DELETE DATA', 'DELETE WHERE',

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
LIMIT Integer
OFFSET Integer
''',

    'CONSTRUCT' :
r'''Returns an RDF graph constructed by substituting variables in a set of 
triple templates.

CONSTRUCT ConstructTemplate DatasetClause* WhereClause SolutionModifier
''',

    'ASK' :
r'''Returns a boolean indicating whether a query pattern matches or not.

ASK DatasetClause* WhereClause''',

    'DESCRIBE' :
r'''Returns an RDF graph that describes the resources found.

DESCRIBE ( VarOrIRIref+ | '*' ) 
DatasetClause* WhereClause? SolutionModifier''',


    'FILTER' :
r'''Restrict the solutions of a graph pattern: eliminate solutions 
that, when substituted into the expression, either result in 
an effective boolean value of false or produce an error.

FILTER ( Expression ) | BuiltInCall | FunctionCall

BuiltInCall ->
  STR ( Expression )
| LANG ( Expression ) 
| LANGMATCHES ( Expression , Expression ) 
| DATATYPE ( Expression ) 
| BOUND ( Var ) 
| sameTerm ( Expression , Expression ) 
| isIRI ( Expression ) 
| isURI ( Expression ) 
| isBLANK ( Expression ) 
| isLITERAL ( Expression )' 
| REGEX ( Expression , Expression , ... )''',

    'ORDER' : 
r'''Establishes the order of a solution sequence

ORDER BY ASC(Expr) | DESC(Expr) | (Expr) | ?Varname | $Varname''',

    'LIMIT' :
r'''Puts an upper bound on the number of solutions returned. 

LIMIT Integer''',
}
