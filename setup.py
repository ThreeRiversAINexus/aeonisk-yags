"""
Setup script for the Aeonisk YAGS toolkit.
"""

from setuptools import setup, find_packages

setup(
    name="aeonisk-yags",
    version="0.1.0",
    description="A toolkit for the Aeonisk RPG setting using the YAGS system",
    author="Aeonisk Team",
    author_email="info@example.com",
    packages=find_packages(where="scripts"),
    package_dir={"": "scripts"},
    install_requires=[
        "pyyaml>=6.0",
        "openai>=1.0.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "isort>=5.0.0",
            "flake8>=6.0.0",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
