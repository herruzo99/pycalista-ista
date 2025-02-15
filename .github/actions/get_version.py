"""
Script to read and print the version of the `pycalista_ista` package.

The version information is stored in the `__version__.py` module within the
`pycalista_ista` package. This script dynamically imports the module and
prints the version.

Functions
---------
main()
    Reads and prints the version of `pycalista_ista`.

Examples
--------
To use this script, run it from the command line:

    $ python get_version.py

This will output the version of the `pycalista_ista` package.
"""

import importlib.util
import sys


def main():
    """
    Read and print the version of pycalista_ista.

    This function dynamically imports the `__version__.py` module from the
    `pycalista_ista` package and prints the version defined in that module.

    Returns
    -------
    int
        The return code. Returns 0 upon successful completion.

    Examples
    --------
    >>> main()
    3.3.2
    0
    """
    spec = importlib.util.spec_from_file_location(
        "pycalista_ista.__version__", "./src/pycalista_ista/__version.py"
    )
    version_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(version_module)
    print(version_module.__version__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
