"""Setup script for the pycalista-ista package."""

from setuptools import find_packages, setup

# Read version from __version.py
with open("pycalista_ista/__version.py", encoding="utf-8") as f:
    # Execute the file context to get __version__
    exec(f.read())

# Read README for long description
with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="pycalista-ista",
    # Use the version variable loaded from __version.py
    version=__version__, # type: ignore[name-defined]  # noqa: F821
    author="Juan Herruzo",
    author_email="juan@herruzo.dev",
    description="Async Python library for the ista Calista service.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/herruzo99/pycalista-ista",
    packages=find_packages(exclude=["tests", "docs"]), # Exclude tests and docs
    # Core dependencies
    install_requires=[
        "aiohttp>=3.9.0", # Added aiohttp for async requests
        "pandas>=2.0.0",  # For Excel parsing
        "unidecode>=1.0.0", # For header normalization
        "yarl>=1.8.0", # Dependency of aiohttp, good practice to list it
        # xlrd is NOT needed if using pandas with openpyxl for xlsx
        # Consider adding openpyxl if xlsx support is primary
        "openpyxl>=3.0.0", # Add openpyxl for .xlsx support in pandas
    ],
    # Development dependencies
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.23.0", # For testing async code
            "pytest-cov>=5.0.0",
            "aioresponses>=0.7.4", # For mocking aiohttp requests
            "black>=24.0.0",
            "isort>=5.0.0",
            "mypy>=1.8.0",
            "ruff>=0.3.0", # Linter
            "types-aiohttp", # Type hints for aiohttp
            "types-requests", # Although requests removed, useful for context
        ],
        "docs": [
            "mkdocs>=1.5.0",
            "mkdocs-material>=9.0.0",
            "mkdocstrings[python]>=0.24.0",
            # Add other mkdocs plugins used in mkdocs.yml
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta", # Update status as appropriate
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12", # Specify supported versions
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: AsyncIO", # Indicate async support
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Home Automation",
    ],
    python_requires=">=3.12",
    # Entry points remain the same if needed for other purposes,
    # but not typically used for HA library dependencies directly.
    # entry_points={ ... },
    include_package_data=True,
    package_data={
        "pycalista_ista": ["py.typed"], # Add py.typed for PEP 561 compliance
    },
    # Add keywords for discoverability on PyPI
    keywords=["ista", "calista", "home assistant", "iot", "energy", "water", "asyncio"],
)
