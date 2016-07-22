from __future__ import absolute_import

from ipykernel.kernelapp import IPKernelApp
from traitlets import Dict

# -----------------------------------------------------------------------

class SparqlKernelApp( IPKernelApp ):
    """
    The main kernel application, inheriting from the ipykernel
    """
    from .kernel import SparqlKernel
    from .install import SparqlKernelInstall, SparqlKernelRemove
    kernel_class = SparqlKernel

    # We override subcommands to add our own install & remove commands
    subcommands = Dict({                                                        
        'install': (SparqlKernelInstall, 
                    SparqlKernelInstall.description.splitlines()[0]), 
        'remove': (SparqlKernelRemove, 
                   SparqlKernelRemove.description.splitlines()[0]), 
    })


# -----------------------------------------------------------------------

def main():
    """
    This is the installed entry point
    """
    SparqlKernelApp.launch_instance()

if __name__ == '__main__':
    main()
