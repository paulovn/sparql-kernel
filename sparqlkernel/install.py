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

from jupyter_client.kernelspecapp  import InstallKernelSpec, RemoveKernelSpec

from IPython.utils.path import ensure_dir_exists
from IPython.utils.tempdir import TemporaryDirectory

from .constants import __version__, DISPLAY_NAME, LANGUAGE

PKGNAME = os.path.basename( os.path.dirname(__file__) )


# The kernel specfile
kernel_json = {
    "argv": [sys.executable, 
	     "-m", PKGNAME, 
	     "-f", "{connection_file}"],
    "display_name": DISPLAY_NAME,
    "name": "aiml_chatbot",
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


def install_custom_css(destdir, cssfile, resource=PKGNAME ):
    """
    Install the kernel CSS file and include it within custom.css
    """
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
    prefix = '/* KERNEL: {} '.format(resource)
    with open(custom + '-new', 'w') as fout:
        fout.write('{}START --------- */\n'.format(prefix))
        fout.write( include + '\n' )
        fout.write('{}END ----------- */\n\n'.format(prefix))
        if os.path.exists( custom ):
            with open( custom ) as fin:
                for line in fin:
                    fout.write( line )
    os.rename( custom+'-new',custom)


def remove_custom_css(destdir, cssfile, resource=PKGNAME ):
    """
    Remove the kernel CSS file and eliminat its include in custom.css
    """
    fullname = os.path.join( destdir, cssfile )
    if not fullname.endswith('.css'):
        fullname += '.css'
    
    if not os.path.exists( fullname ):
        return False

    # Remove the inclusion in the main CSS
    custom = os.path.join( destdir, 'custom.css' )
    copy = True
    prefix = '/* KERNEL: {} '.format(resource)
    with open(custom + '-new', 'w') as fout:
        with open(custom) as fin:
            for line in fin:
                if line.startswith( prefix + 'START' ):
                    copy = False
                elif line.startswith( prefix + 'END' ):
                    copy = True
                elif copy:
                    fout.write( line )
    os.rename( custom+'-new',custom)

    # Remove the CSS file
    os.remove( fullname )

    return True



# --------------------------------------------------------------------------


class SparqlKernelInstall( InstallKernelSpec ):
    """
    The kernel installation class
    """

    version = __version__
    kernel_name = PKGNAME
    description = '''Install the AIML Chatbot Kernel
    Either as a system kernel or for a concrete user'''

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

        self.log.info('Installing AIML chatbot kernel')
        with TemporaryDirectory() as td:
            os.chmod(td, 0o755) # Starts off as 700, not user readable
            # Add kernel spec
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

    spec_names = [ PKGNAME ]
    description = '''Remove the AIML Chatbot Kernel'''

    def parse_command_line(self, argv):
        """
        Skip parent method and go for its ancestor
        (because parent method requires an extra argument: the kernel to remove)
        """
        super(RemoveKernelSpec, self).parse_command_line(argv)

    def start(self):
        # Call parent (this one the actual parent) to remove the kernelspec dir
        super(SparqlKernelRemove, self).start()

        # Remove the installed custom CSS
        self.log.info('Removing CSS')
        # Use the ~/.jupyter/custom dir
        import jupyter_core
        destd = os.path.join( jupyter_core.paths.jupyter_config_dir(),'custom')
        if remove_custom_css( destd, PKGNAME ):
            self.log.info('Removed from %s', destd)
        # Use the system custom dir
        import notebook
        destd = os.path.join( notebook.DEFAULT_STATIC_FILES_PATH, 'custom' )
        if remove_custom_css( destd, PKGNAME ):
            self.log.info('Removed from %s', destd)
