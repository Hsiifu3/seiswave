from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="seiswave",
    version="2.0.0",
    packages=find_packages(exclude=["tests*", "examples*", "matlab_ref*"]),
    install_requires=[
        "numpy>=1.22",
        "scipy>=1.8",
        "matplotlib>=3.5",
    ],
    extras_require={
        "gui": ["PySide6>=6.5"],
    },
    entry_points={
        "console_scripts": [
            "seiswave=seiswave.__main__:main",
        ],
        "gui_scripts": [
            "seiswave-gui=seiswave.__main__:main",
        ],
    },
    author="Hsiifu3",
    author_email="",
    description="地震信号处理与选波工具包 / Seismic Signal Processing & Wave Selection Toolkit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Hsiifu3/seiswave",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering",
        "Intended Audience :: Science/Research",
    ],
    python_requires=">=3.10",
)
