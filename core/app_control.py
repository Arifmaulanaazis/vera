from datetime import datetime 

APP_INFO = {
    "name": "VERA",
    "full_name": "VERA: Virtual Execution and Reaction Architecture",
    "version": "1.1.2",
    "author": "apt. Arif Maulana Azis, S.Farm",
    "organization": "VERA",
    "copyright": f"© {datetime.now().year} VERA, All Rights Reserved.",
    "website": "https://vera-desktop-app.netlify.app",
    "support_email": "titandigitalsoft@gmail.com",
    "documentation_url": "https://vera-desktop-app.netlify.app/docs",
    "description": "Virtual Execution and Reaction Architecture",
    "license": "MIT License",
    "repository": "https://github.com/Arifmaulanaazis/vera",
    "issues_url": "https://github.com/Arifmaulanaazis/vera/issues",
    "features": [
        "Molecular Docking: Advanced molecular docking using AutoDock Vina, GPU acceleration, and comprehensive analysis tools",
        "Molecular Minimization: Advanced molecular minimization using RDKit and OpenBabel with conformer generation",
        "Molecular Dynamics: Complete GROMACS workflow from preparation to analysis with trajectory visualization",
        "Machine Learning: Comprehensive machine learning workflow from data preparation to model training and evaluation",
        "Chemical Visualization: 2D structure drawing, 3D web viewer (NGL.js), and protein-ligand interaction visualization",
        "Data Visualization: Advanced plotting with histograms, scatter plots, line charts, bar charts, pie charts, and heatmaps",
        "Chemical Data Collection: Database access for PubChem compound search and RCSB PDB structure retrieval",
        "Data Processing: Advanced dataframe manipulation with filtering, sorting, merging, and column operations",
        "File I/O: Comprehensive support for molecular formats (SDF, MOL, MOL2, PDB, PDBQT) and data formats (CSV, Excel, JSON)",
        "User Interface: Intuitive drag-and-drop node-based workflow interface with real-time visualization",
        "Performance: GPU acceleration for computationally intensive tasks and optimized toolchains",
        "Cross-platform: Windows compatibility with integrated molecular modeling and analysis tools"
    ],

    "libraries": {
        "gui_framework": {
            "PySide6": {
                "version": ">=6.6.0",
                "description": "Qt6 Python bindings for GUI framework",
                "website": "https://doc.qt.io/qtforpython/",
                "pypi": "https://pypi.org/project/PySide6/",
                "license": "LGPL v3"
            },
            "PySide6-WebEngine": {
                "version": ">=6.6.0",
                "description": "Qt WebEngine integration for embedding web content",
                "website": "https://doc.qt.io/qtforpython-6/",
                "pypi": "https://pypi.org/project/PySide6-WebEngine/",
                "license": "LGPL v3"
            }
        },
        "data_analysis": {
            "numpy": {
                "version": ">=1.24.0", 
                "description": "Numerical computing", 
                "website": "https://numpy.org/", 
                "pypi": "https://pypi.org/project/numpy/", 
                "license": "BSD-3-Clause"
            },
            "pandas": {"version": ">=2.0.0", 
                "description": "Data manipulation and analysis", 
                "website": "https://pandas.pydata.org/", 
                "pypi": "https://pypi.org/project/pandas/",
                "license": "BSD-3-Clause"
            },
            "openpyxl": {"version": ">=3.1.5",
                "description": "Excel file handling",
                "website": "https://openpyxl.readthedocs.io/",
                "pypi": "https://pypi.org/project/openpyxl/",
                "license": "MIT"
            }
        },
        "cheminformatics_bioinformatics": {
            "rdkit": {"version": ">=2023.9.1", 
                "description": "Cheminformatics toolkit",
                "website": "https://www.rdkit.org/",
                "pypi": "https://pypi.org/project/rdkit/",
                "license": "BSD"
            },
            "biopython": {"version": ">=1.81", 
                "description": "Biological computation toolkit", 
                "website": "https://biopython.org/",
                "pypi": "https://pypi.org/project/biopython/",
                "license": "BSD-3-Clause"
            },
            "prolif": {"version": ">=2.0.0",
                "description": "Protein-ligand interaction fingerprints",
                "website": "https://prolif.readthedocs.io/",
                "pypi": "https://pypi.org/project/prolif/",
                "license": "MIT"
            },
            "pubchempy": {"version": ">=1.0.4", 
                "description": "PubChem API client",
                "website": "https://pubchempy.readthedocs.io/",
                "pypi": "https://pypi.org/project/pubchempy/",
                "license": "BSD-3-Clause"
            }
        },
        "visualization": {
            "matplotlib": {"version": "3.9.4", 
                "description": "2D plotting library", 
                "website": "https://matplotlib.org/", 
                "pypi": "https://pypi.org/project/matplotlib/", 
                "license": "PSF"
            },
            "seaborn": {"version": "0.13.2", 
                "description": "Statistical data visualization", 
                "website": "https://seaborn.pydata.org/", 
                "pypi": "https://pypi.org/project/seaborn/", 
                "license": "BSD-3-Clause"
            },
            "plotly": {"version": "5.17.0", 
                "description": "Interactive graphing and dashboards", 
                "website": "https://plotly.com/python/", 
                "pypi": "https://pypi.org/project/plotly/", 
                "license": "MIT"
            },
            "NGL.js": {"version": "2.2.1",
                "description": "Web-based molecular viewer",
                "website": "https://cdn.jsdelivr.net/npm/ngl@2.2.1/dist/ngl.js",
                "license": "MIT"
            }
        },
        "networking": {
            "requests": {"version": "2.31.0", 
                "description": "HTTP requests library", 
                "website": "https://requests.readthedocs.io/", 
                "pypi": "https://pypi.org/project/requests/", 
                "license": "Apache-2.0"
            },
            "beautifulsoup4": {"version": "4.12.0", 
                "description": "HTML/XML parsing", 
                "website": "https://www.crummy.com/software/BeautifulSoup/", 
                "pypi": "https://pypi.org/project/beautifulsoup4/", 
                "license": "MIT"
            },
            "lxml": {"version": "4.9.0", 
                "description": "XML/HTML processing", 
                "website": "https://lxml.de/", 
                "pypi": "https://pypi.org/project/lxml/", 
                "license": "BSD"
            }
        },
        "graphics_acceleration": {
            "PyOpenGL": {"version": ">=3.1.0", 
                "description": "OpenGL bindings for Python",
                "website": "http://pyopengl.sourceforge.net/",
                "pypi": "https://pypi.org/project/PyOpenGL/",
                "license": "BSD"
            },
            "PyOpenGL_accelerate": {"version": "3.1.0", 
                "description": "Accelerated PyOpenGL functions", 
                "website": "http://pyopengl.sourceforge.net/", 
                "pypi": "https://pypi.org/project/PyOpenGL-accelerate/", 
                "license": "BSD"
            },
            "PyOpenCL": {"version": "2024.1", 
                "description": "OpenCL bindings for parallel computing", 
                "website": "https://documen.tician.de/pyopencl/", 
                "pypi": "https://pypi.org/project/pyopencl/", 
                "license": "MIT"
            }
        },
        "utilities": {
            "Pillow": {"version": "10.0.0", 
                "description": "Image processing library", 
                "website": "https://python-pillow.org/", 
                "pypi": "https://pypi.org/project/Pillow/", 
                "license": "HPND"
            },
            "ipython": {"version": "8.15.0", 
                "description": "Interactive Python shell", 
                "website": "https://ipython.org/", 
                "pypi": "https://pypi.org/project/ipython/", 
                "license": "BSD"
            }
        },
        "machine_learning": {
            "scikit-learn": {"version": "1.1.0", 
                "description": "Machine learning library", 
                "website": "https://scikit-learn.org/", 
                "pypi": "https://pypi.org/project/scikit-learn/", 
                "license": "BSD-3-Clause"
            }
        },
        "build_packaging": {
            "Nuitka": {"version": "0.6.18.4", 
                "description": "Python to C++ compiler for executables", 
                "website": "https://nuitka.net/", 
                "pypi": "https://pypi.org/project/Nuitka/", 
                "license": "Apache-2.0"
            }
        },
        "third_party_apps": {
            "AutoDock Vina": {"version": "1.1.2 & 1.2.3 - 1.2.7", 
                "description": "Molecular docking software", 
                "website": "http://vina.scripps.edu/"
            },
            "AutoDock Vina GPU": {"version": "2.1", 
                "description": "GPU-accelerated AutoDock Vina", 
                "website": "https://github.com/ccsb-scripps/AutoDock-GPU"
            },
            "Vina Split": {"version": "1.1.2 & 1.2.4 - 1.2.7", 
                "description": "Tool to split docking input/output files", 
                "website": "https://github.com/ccsb-scripps/vina_split"
            },
            "GROMACS": {"version": "2025.1 - 2025.2", 
                "description": "Molecular dynamics simulation package", 
                "website": "http://www.gromacs.org/"
            },
            "OpenBabel": {"version": "3.1.1", 
                "description": "Chemical toolbox for format conversion", 
                "website": "https://openbabel.org/"
            },
        }
    },
    "system_requirements": {
        "python": "3.13.5",
        "platform": "Windows 10/11",
        "architecture": "x64",
        "memory": "8GB RAM (recommended)",
        "storage": "3GB free space"
    }
}
