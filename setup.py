"""
Install the sparqlkernel Jupyter kernel
Also add kernel resources (logos and CSS)
"""

import os
import os.path
import sys
import json
import pkgutil

from distutils.core import setup
from distutils.command.install import install
from distutils import log

from IPython.utils.path import ensure_dir_exists

from sparqlkernel.constants import __version__, LANGUAGE, DISPLAY_NAME
PKGNAME = 'sparqlkernel'


# The kernel spacification to be installed
kernel_json = {
    "argv": [sys.executable,"-m", PKGNAME, "-f", "{connection_file}"],
    "display_name": DISPLAY_NAME,
    "language_info": { "name": LANGUAGE },
    "codemirror_mode":  {
        "version": 2,
        "name": "sparql"
    }
}


# --------------------------------------------------------------------------


def copyresource( resource, filename, destdir ):
    """
    Copy a resource file to a destination
    """
    data = pkgutil.get_data(resource, os.path.join('resources',filename) )
    with open( os.path.join(destdir,filename), 'wb' ) as fp:
        fp.write(data)


def install_custom_css(destdir, cssfile, resource=PKGNAME ):
    """
    Install the custom CSS file and include it within custom.css
    """
    log.info( "Installing %s", cssfile )

    # Copy it
    ensure_dir_exists( destdir )
    cssfile += '.css'
    copyresource( resource, cssfile, destdir )

    # Check if custom.css already includes it. If so, we can return
    include = "@import url('{}');".format( cssfile )
    custom = os.path.join( destdir, 'custom.css' )
    if os.path.exists( custom ):
        with open(custom) as f:
            for line in f:
                if line.find( include ) >= 0:
                    return

    # Add the import line at the beginning of custom.css
    with open(custom + '-new', 'w') as fout:
        fout.write('/* --- Added for {} --- */\n'.format(resource) )
        fout.write( include + '\n' )
        fout.write('/* -------------------- */\n'.format(resource) )
        with open( custom ) as fin:
            for line in fin:
                fout.write( line )
    os.rename( custom+'-new',custom)



def install_kernel_resources( destdir, resource=PKGNAME, files=None ):
    """
    Copy the resource files to the kernelspec folder.
    """
    if files is None:
        files = ['logo-64x64.png', 'logo-32x32.png']
    log.info( "Installing kernel resources: %s", files )
    for filename in files:
        try:
            copyresource( resource, filename, destdir )
        except Exception as e:
            sys.stderr.write(str(e))


# --------------------------------------------------------------------------

class install_with_kernelspec(install):

    def run(self):
        # Regular package installation
        install.run(self)

        # Now write the kernelspec
        log.info( "Installing kernelspec" )
        from jupyter_client.kernelspec import KernelSpecManager
        destdir = os.path.join( KernelSpecManager().user_kernel_dir, LANGUAGE )
        ensure_dir_exists( destdir )
        with open(os.path.join(destdir, 'kernel.json'), 'w') as f:
            json.dump(kernel_json, f, sort_keys=True)

        # Copy the kernel resources (logo images)
        install_kernel_resources(destdir)

        # Install the css
        # Use the ~/.jupyter/custom dir
        import jupyter_core
        destd = os.path.join( jupyter_core.paths.jupyter_config_dir(),'custom')
        # Use the system custom dir
        #import notebook
        #destd = os.path.join( notebook.DEFAULT_STATIC_FILES_PATH, 'custom' )
        install_custom_css( destd, PKGNAME )



# ----------------------------------------------------------------------

svem_flag = '--single-version-externally-managed'
if svem_flag in sys.argv:
    # Die, setuptools, die.
    sys.argv.remove(svem_flag)


setup(name=PKGNAME,
      version=__version__,
      description= 'A Jupyter kernel for SPARQL code',
      long_description=
'''This module installs a Jupyter kernel for SPARQL. It allows sending queries
to an SPARQL endpoint and fetching & presenting the results in a notebook.
It is implemented as a Jupyter wrapper kernel, by using the Python 
SPARQLWrapper & rdflib packages''',
      author='Paulo Villegas',
      author_email='paulo.vllgs@gmail.com',
      url='https://github.com/paulovn/sparql-kernel',

      requires = [ 'IPython', 'ipykernel', 'traitlets', 
                   'rdflib', 'SPARQLWrapper', ],
      install_requires=[],

      packages=[ PKGNAME ],
      cmdclass={ 'install': install_with_kernelspec },
      package_data={
          'sparqlkernel': [ 'resources/logo-*.png', 
                            'resources/sparqlkernel.css' ]
      },
      classifiers = [
          'Framework :: IPython',
          'Programming Language :: Python :: 2.7',
          'Topic :: Database :: Front-Ends',
          'Topic :: System :: Shells',
          'License :: OSI Approved :: BSD License',
      ]
  )
