
if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    from sparqlkernel.kernel import SparqlKernel
    IPKernelApp.launch_instance( kernel_class=SparqlKernel )
