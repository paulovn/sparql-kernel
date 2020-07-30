# Build the Python source package & upload to PyPi

# Package version: taken from the __init__.py file
PKGNAME_BASE_UND := $(subst -,_,$(PKGNAME_BASE))
VERSION_FILE := sparqlkernel/constants.py
VERSION	     := $(shell grep __version__ $(VERSION_FILE) | sed -r "s/__version__ = '(.*)'/\1/")

PKG := dist/sparqlkernel-$(VERSION).tar.gz

# ----------------------------------------------------------------------------

all:
	python setup.py sdist

clean:
	rm -f $(PKG)

install: all
	pip install --upgrade $(PKG)

reinstall: clean install

# ----------------------------------------------------------------------------

upload: all
	twine upload $(PKG)
	# python setup.py sdist --formats=gztar upload

upload-test: all
	twine upload -r pypitest $(PKG)


