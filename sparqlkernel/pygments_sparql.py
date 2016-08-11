
from pygments.lexers.rdf import SparqlLexer
from pygments.token import Other

class SparqlLexerMagics( SparqlLexer ):
    """
    A variant of the standard SPARQL Pygments lexer that understands 
    line magics
    """
    #print( "I'm the custom converter")

    aliases = [ 'sparql-nb', 'sparql' ]
    name = 'SPARQL w/ notebook magics'

    # We add to the root tokens a regexp to match %magic lines
    tokens = SparqlLexer.tokens
    tokens['root'] = [ (r'^%[a-zA-Z]\w+.*\n', Other ) ] + tokens['root'] 

