from setuptools import setup, find_packages

setup(
    name="aeonisk",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
        "openai>=1.0.0",
        "anthropic>=0.18.0",
        "aiohttp>=3.8.0",
        "PyYAML>=6.0.0",
        "numpy>=1.21.0",
        "scipy>=1.7.0",
        "matplotlib>=3.5.0",
        "pandas>=1.3.0",
    ],
    python_requires=">=3.8",
    author="Aeonisk Team",
    description="Aeonisk YAGS Engine and Benchmark System",
    entry_points={
        "console_scripts": [
            "aeonisk-benchmark=aeonisk.benchmark.cli:main",
            "aeonisk-dataset=aeonisk.dataset.cli:main",
            "aeonisk-engine=aeonisk.engine.cli:main",
        ],
    },
)