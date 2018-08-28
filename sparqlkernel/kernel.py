"""
The main kernel class for Jupyter. 
Interact with the notebook and process all frontend requests.
"""

from ipykernel.kernelbase import Kernel
from traitlets import List

import logging

import SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import SPARQLWrapperException

from .constants import __version__, LANGUAGE
from .utils import is_collection, data_msg
from .setlogging import set_logging
from .language import sparql_names, sparql_help
from .connection import SparqlConnection, KrnlException, magics, magic_help
# IPython.core.display.HTML



# -----------------------------------------------------------------------

def is_magic(token, token_start, buf):
    """
    Detect if the passed token corresponds to a magic command: starts
    with a percent, and it's at the beginning of a line
    """
    return token[0] == '%' and (token_start == 0 or buf[token_start-1] == '\n')


def token_at_cursor(code, pos=0):
    """
    Find the token present at the passed position in the code buffer
     :return (tuple): a pair (token, start_position)
    """
    l = len(code)
    end = start = pos
    # Go forwards while we get alphanumeric chars
    while end < l and code[end].isalpha():
        end += 1
    # Go backwards while we get alphanumeric chars
    while start > 0 and code[start-1].isalpha():
        start -= 1
    # If previous character is a %, add it (potential magic)
    if start > 0 and code[start-1] == '%':
        start -= 1
    return code[start:end], start


# --------------------------------------------------------------------------

class SparqlKernel(Kernel):
    """
    The class implementing the Jupyter kernel
    """

    # Kernel info
    implementation = 'SPARQL'
    implementation_version = __version__
    banner = "SPARQL kernel"
    language = LANGUAGE
    language_version = '1.1'
    language_info = {'name': 'sparql',
                     'mimetype': 'application/sparql-query',
                     'codemirror_mode': {"name": "sparql"},
                     'pygments_lexer': 'sparql-nb'}


    # Add some items to notebook help menu
    help_links = List([
        {
            'text': "SPARQL",
            'url': "https://www.w3.org/TR/rdf-sparql-query/",
        },
        {
            'text': "SPARQL 1.1",
            'url': "https://www.w3.org/TR/sparql11-overview/",
        },
        {
            'text': "SPARQL Tutorial",
            'url': "https://jena.apache.org/tutorials/sparql.html",
        }, ])


    # -----------------------------------------------------------------

    def __init__(self, **kwargs):
        """
        Initialize the object
        """
        # Define logging status before calling parent constructor
        set_logging(level='WARN')
        # Initialize parent class
        super(SparqlKernel, self).__init__(**kwargs)
        # Define our own logger, different from parent's (i.e. self.log)
        self._klog = logging.getLogger(__name__)
        self._klog.info('START')
        # Create the object holding the SPARQL connections
        self._k = SparqlConnection()

    # -----------------------------------------------------------------


    def _send(self, data, msg_type='ok', silent=False):
        """
        Send a response to the frontend and return an execute message
         @param data: response to send
         @param msg_type (str): message type: 'ok', 'raw', 'error', 'multi'
         @param silent (bool): suppress output
         @return (dict): the return value for the kernel
        """
        # Data to send back
        if data is not None:
            # log the message
            try:
                self._klog.debug(u"msg to frontend (%d): %.160s...", silent, data)
            except Exception as e:
                self._klog.warn(u"can't log response: %s", e)
            # send it to the frontend
            if not silent:
                if msg_type != 'raw':
                    data = data_msg(data, mtype=msg_type)
                self.send_response(self.iopub_socket, 'display_data', data)

        # Result message
        return {'status': 'error' if msg_type == 'error' else 'ok',
                # The base class will increment the execution count
                'execution_count': self.execution_count,
                'payload': [],
                'user_expressions': {}
                }



    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        """
        Method called to execute a cell
        """
        self._klog.info("[%.30s] [%d] [%s]", code, silent, user_expressions)

        # Split lines and remove empty lines & comments
        code_noc = [line.strip() for line in code.split('\n')
                    if line and line[0] != '#']
        if not code_noc:
            return self._send(None)

        # Process
        try:
            # Detect if we've got magics
            magic_lines = []
            for line in code_noc:
                if line[0] != '%':
                    break
                magic_lines.append(line)

            # Process magics. Once done, remove them from the query buffer
            if magic_lines:
                out = [self._k.magic(line) for line in magic_lines]
                self._send(out, 'multi', silent=silent)
                code = '\n'.join(code_noc[len(magic_lines):])

            # If we have a regular SPARQL query, process it now
            result = self._k.query(code, num=self.execution_count) if code else None

            # Return the result
            return self._send(result, 'raw', silent=silent)

        except Exception as e:
            return self._send(e, 'error', silent=silent)


    # -----------------------------------------------------------------

    def do_inspect(self, code, cursor_pos, detail_level=0):
        """
        Method called on help requests
        """
        self._klog.info("{%s}", code[cursor_pos:cursor_pos+10])

        # Find the token for which help is requested
        token, start = token_at_cursor(code, cursor_pos)
        self._klog.debug("token={%s} {%d}", token, detail_level)

        # Find the help for this token
        if not is_magic(token, start, code):
            info = sparql_help.get(token.upper(), None)
        elif token == '%':
            info = magic_help
        else:
            info = magics.get(token, None)
            if info:
                info = '{} {}\n\n{}'.format(token, *info)

        return {'status': 'ok',
                'data': {'text/plain': info},
                'metadata': {},
                'found': info is not None
               }

    # -----------------------------------------------------------------

    def do_complete(self, code, cursor_pos):
        """
        Method called on autocompletion requests
        """
        self._klog.info("{%s}", code[cursor_pos:cursor_pos+10])

        token, start = token_at_cursor(code, cursor_pos)
        tkn_low = token.lower()
        if is_magic(token, start, code):
            matches = [k for k in magics.keys() if k.startswith(tkn_low)]
        else:
            matches = [sparql_names[k] for k in sparql_names
                       if k.startswith(tkn_low)]
        self._klog.debug("token={%s} matches={%r}", token, matches)

        if matches:
            return {'status': 'ok',
                    'cursor_start': start,
                    'cursor_end': start+len(token),
                    'matches': matches}

# -----------------------------------------------------------------

if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=SparqlKernel)
