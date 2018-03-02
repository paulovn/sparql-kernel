"""
Perform kernel installation, including
  * json kernel specfile
  * kernel resources (logo images)
  * custom css
"""

from __future__ import print_function
import sys
import os
import os.path
import json
import pkgutil
import io

from jupyter_client.kernelspecapp  import InstallKernelSpec, RemoveKernelSpec
from traitlets import Unicode

from IPython.utils.path import ensure_dir_exists
from IPython.utils.tempdir import TemporaryDirectory

from .constants import __version__, KERNEL_NAME, DISPLAY_NAME, LANGUAGE

PY3 = sys.version_info[0] == 3
if PY3:
    unicode = str

MODULEDIR = os.path.dirname(__file__)
PKGNAME = os.path.basename( MODULEDIR )


# The kernel specfile
kernel_json = {
    "argv": [sys.executable, 
	     "-m", PKGNAME, 
	     "-f", "{connection_file}"],
    "display_name": DISPLAY_NAME,
    "language": LANGUAGE,
    "name": KERNEL_NAME
}


# --------------------------------------------------------------------------

def css_frame_prefix( name ):
    '''Define the comment prefix used in custom css to frame kernel CSS'''
    return u'/* @{{KERNEL}} {} '.format(name)


def copyresource( resource, filename, destdir ):
    """
    Copy a resource file to a destination
    """
    data = pkgutil.get_data(resource, os.path.join('resources',filename) )
    #log.info( "Installing %s", os.path.join(destdir,filename) )
    with open( os.path.join(destdir,filename), 'wb' ) as fp:
        fp.write(data)


def install_kernel_resources( destdir, resource=PKGNAME, files=None ):
    """
    Copy the resource files to the kernelspec folder.
    """
    if files is None:
        files = ['logo-64x64.png', 'logo-32x32.png']
    for filename in files:
        try:
            copyresource( resource, filename, destdir )
        except Exception as e:
            sys.stderr.write(str(e))


def install_custom_css( destdir, cssfile, resource=PKGNAME ):
    """
    Add the kernel CSS to custom.css
    """
    ensure_dir_exists( destdir )
    custom = os.path.join( destdir, 'custom.css' )
    prefix = css_frame_prefix(resource)

    # Check if custom.css already includes it. If so, let's remove it first
    exists = False
    if os.path.exists( custom ):
        with io.open(custom) as f:
            for line in f:
                if line.find( prefix ) >= 0:
                    exists = True
                    break
    if exists:
        remove_custom_css( destdir, resource )

    # Fetch the CSS file
    cssfile += '.css'
    data = pkgutil.get_data( resource, os.path.join('resources',cssfile) )
    # get_data() delivers encoded data, str (Python2) or bytes (Python3)

    # Add the CSS at the beginning of custom.css
    # io.open uses unicode strings (unicode in Python2, str in Python3)
    with io.open(custom + '-new', 'wt', encoding='utf-8') as fout:
        fout.write( u'{}START ======================== */\n'.format(prefix))
        fout.write( data.decode('utf-8') )
        fout.write( u'{}END ======================== */\n'.format(prefix))
        if os.path.exists( custom ):
            with io.open( custom, 'rt', encoding='utf-8' ) as fin:
                for line in fin:
                    fout.write( unicode(line) )
    os.rename( custom+'-new',custom)


def remove_custom_css(destdir, resource=PKGNAME ):
    """
    Remove the kernel CSS from custom.css
    """

    # Remove the inclusion in the main CSS
    if not os.path.isdir( destdir ):
        return False
    custom = os.path.join( destdir, 'custom.css' )
    copy = True
    found = False
    prefix = css_frame_prefix(resource)
    with io.open(custom + '-new', 'wt') as fout:
        with io.open(custom) as fin:
            for line in fin:
                if line.startswith( prefix + 'START' ):
                    copy = False
                    found = True
                elif line.startswith( prefix + 'END' ):
                    copy = True
                elif copy:
                    fout.write( line )

    if found:
        os.rename( custom+'-new',custom)
    else:
        os.unlink( custom+'-new')

    return found



# --------------------------------------------------------------------------


class SparqlKernelInstall( InstallKernelSpec ):
    """
    The kernel installation class
    """

    version = __version__
    kernel_name = KERNEL_NAME
    description = '''Install the SPARQL Jupyter Kernel.
    Either as a system kernel or for a concrete user'''

    logdir = Unicode( os.environ.get('LOGDIR', ''),
        config=True,
        help="""Default directory to use for the logfile."""
    )
    aliases =  { 'logdir' : 'SparqlKernelInstall.logdir' } 

    def parse_command_line(self, argv):
        """
        Skip parent method and go for its ancestor
        (because parent method requires an extra argument: the kernel to install)
        """
        super(InstallKernelSpec, self).parse_command_line(argv)


    def start(self):
        if self.user and self.prefix:
            self.exit("Can't specify both user and prefix. Please choose one or\
 the other.")

        self.log.info('Installing SPARQL kernel')
        with TemporaryDirectory() as td:
            os.chmod(td, 0o755) # Starts off as 700, not user readable
            # Add kernel spec
            if len(self.logdir):
                kernel_json['env'] = { 'LOGDIR_DEFAULT' : self.logdir }
            with open(os.path.join(td, 'kernel.json'), 'w') as f:
                json.dump(kernel_json, f, sort_keys=True)
            # Add resources
            install_kernel_resources(td, resource=PKGNAME)
            # Install JSON kernel specification + resources
            self.log.info('Installing kernel spec')
            self.sourcedir = td
            install_dir = self.kernel_spec_manager.install_kernel_spec( td,
                kernel_name=self.kernel_name,
                user=self.user,
                prefix=self.prefix,
                replace=self.replace,
            )
        self.log.info( "Installed into %s", install_dir )

        #install_kernel( self.kernel_spec_manager )
	#self.create_kernel_json( install_dir )

        # Install the custom css
        self.log.info('Installing CSS')
        if self.user:
            # Use the ~/.jupyter/custom dir
            import jupyter_core
            destd = os.path.join( jupyter_core.paths.jupyter_config_dir(),'custom')
        else:
            # Use the system custom dir
            import notebook
            destd = os.path.join( notebook.DEFAULT_STATIC_FILES_PATH, 'custom' )

        self.log.info('Installing CSS into %s', destd)
        install_custom_css( destd, PKGNAME )


# --------------------------------------------------------------------------


class SparqlKernelRemove( RemoveKernelSpec ):
    """
    The kernel uninstallation class
    """

    spec_names = [ KERNEL_NAME ]
    description = '''Remove the SPARQL Jupyter Kernel'''

    def parse_command_line(self, argv):
        """
        Skip parent method and go for its ancestor
        (because parent method requires an extra argument: the kernel to remove)
        """
        super(RemoveKernelSpec, self).parse_command_line(argv)

    def start(self):
        # Call parent (this time the real parent) to remove the kernelspec dir
        super(SparqlKernelRemove, self).start()

        # Remove the installed custom CSS
        # Try the ~/.jupyter/custom dir & the system custom dir
        self.log.info('Removing CSS')
        import jupyter_core
        import notebook
        cssd = ( os.path.join(jupyter_core.paths.jupyter_config_dir(),'custom'),
                 os.path.join(notebook.DEFAULT_STATIC_FILES_PATH,'custom') )
        for destd in cssd:
            if remove_custom_css( destd, PKGNAME ):
                self.log.info('Removed CSS from %s', destd)
