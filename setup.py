from setuptools import setup, find_packages

setup(
    name="transitsync-routing",
    version="0.1.0",
    description="GTFS-based transit route planning for Wellington using Metlink and OpenStreetMap.",
    author="Hamish Burke",
    author_email="hamishapps@gmail.com",  # Optional
    url="https://github.com/Slaymish/transitsync-routing",  # Replace with your actual repo
    packages=find_packages(),
    install_requires=[
        "requests",
        "pytz"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)