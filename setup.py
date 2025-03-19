from setuptools import find_packages, setup

setup(
    name="pycalista-ista",
    version="0.3.1",
    author="Juan Herruzo",
    author_email="juan@herruzo.dev",
    description="Python library for the ista calista service.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/herruzo99/pycalista-ista",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "xlrd>=2.0.1",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.12",  # Specify Python version requirement
    entry_points={
        "homeassistant.integration": [
            "pycalista-ista = pycalista_ista"  # Adjust for your integration's setup
        ],
    },
    include_package_data=True,  # Include additional files like configuration.yaml, etc.
    package_data={
        "pycalista_ista": ["*.json"],  # Example if you have data files
    },
)
