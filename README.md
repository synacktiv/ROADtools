# ROADtools 
*(**R**ogue **O**ffice 365 and **A**zure (active) **D**irectory tools)*

![Python 3 only](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/pypi/l/roadlib.svg)

<img src="roadrecon/frontend/src/assets/rt_transparent.svg" width="300px" alt="ROADtools logo" />

ROADtools is a framework to interact with Azure AD. It consists of a library (roadlib) with common components, the ROADrecon Azure AD exploration tool and the ROADtools Token eXchange (roadtx) tool.

## ROADlib
![PyPI version](https://img.shields.io/pypi/v/roadlib.svg)

ROADlib is a library that can be used to authenticate with Azure AD or to build tools that integrate with a database containing ROADrecon data. The database model in ROADlib is automatically generated based on the metadata definition of the Azure AD internal API. ROADlib lives in the ROADtools namespace, so to import it in your scripts use `from roadtools.roadlib import X`

## ROADrecon
![PyPI version](https://img.shields.io/pypi/v/roadrecon.svg)
[![Build Status](https://dev.azure.com/dirkjanm/ROADtools/_apis/build/status/dirkjanm.ROADtools?branchName=master)](https://dev.azure.com/dirkjanm/ROADtools/_build/latest?definitionId=19&branchName=master)

ROADrecon is a tool for exploring information in Azure AD from both a Red Team and Blue Team perspective. In short, this is what it does:
* Uses an automatically generated metadata model to create an SQLAlchemy backed database on disk.
* Use asynchronous HTTP calls in Python to dump all available information in the Azure AD graph to this database.
* Provide plugins to query this database and output it to a useful format.
* Provide a web interface (FastAPI backend, React frontend) that queries the offline database directly for its analysis.

ROADrecon uses `async` Python features and is only compatible with Python 3.10 and newer (development is done with Python 3.11, tests are run with versions up to Python 3.14). 

### Installation
There are multiple ways to install ROADrecon:

**Using a published version on PyPi**  
Stable versions can be installed with `pip install roadrecon`. This will automatically add the `roadrecon` command to your PATH.

**Using a version from GitHub**  
Every commit to master is automatically built into a release version with Azure Pipelines. This ensures that you can install the latest version of the GUI without having to install `npm` and all it's dependencies. You can download the `roadlib` and `roadrecon` build files from the [Azure Pipelines artifacts](https://dev.azure.com/dirkjanm/ROADtools/_build/latest?definitionId=19&branchName=master) (click on the button "1 Published". The build output files are stored in `ROADtools.zip`. You can either install the `.whl` or `.tar.gz` files directly using pip or unzip both and install the folders in the correct order (`roadlib` first):

```
pip install roadlib/
pip install roadrecon/
```

You can also install them in development mode with `pip install -e roadlib/`.

**Developing the front-end**  
If you want to make changes to the front-end (React, in `roadrecon/frontend-react/`), you will need to have `node` (22) and `npm` installed. Then install the components from git:
```
git clone https://github.com/dirkjanm/roadtools.git
pip install -e roadlib/
pip install -e roadrecon/
cd roadrecon/frontend-react/
npm ci
```

Run the API with `uvicorn roadtools.roadrecon.api.app:create_app --factory --reload --port 8000` (it reads the database from `$ROADRECON_DB`, default `roadrecon.db`), then `npm run dev` from `roadrecon/frontend-react/`. Vite serves the front-end on http://127.0.0.1:5173 and forwards `/api` to port 8000. To build the JavaScript files into ROADrecon's `roadtools/roadrecon/dist_gui` directory, run `npm run build`.

Alternatively, `roadrecon/compose.yaml` runs everything in containers (podman or docker), from the `roadrecon/` directory:
```
podman compose run --rm py python roadrecon/tests/gendb.py -o roadrecon/.dev/roadrecon.db   # synthetic database
podman compose up                  # built GUI + API on http://127.0.0.1:5000 (ROADRECON_DB overrides the database)
podman compose up api web          # development: API with --reload + Vite on http://127.0.0.1:5173
podman compose run --rm py pytest roadrecon/tests -q
podman compose run --rm node npm run build
```

### Using ROADrecon
After gathering data with `roadrecon auth` and `roadrecon gather`, start the GUI with `roadrecon gui` (or `roadrecon-gui`) and open http://127.0.0.1:5000. Options: `-d` for the database file (default `roadrecon.db`), `--host` and `--port` (default `127.0.0.1:5000`), and `--read-only` to never write to the database (by default, indexes are added on start-up).

The GUI shows:
* A dashboard with tenant statistics, tenant information and directory settings.
* Lists of users, groups, devices, administrative units, service principals, applications, directory roles, application role assignments, OAuth2 permission grants and MFA status, with server-side search, filters, sorting and CSV/JSON export.
* A page per object, with its properties, its relations (members, owners, roles, PIM, Azure roles, access packages, Conditional Access policies) and the raw object.
* Conditional Access policies with every reference resolved to a link, the users in scope of a policy, and the named locations with the policies that use them.
* A SQL page to run read-only queries directly against the database, with built-in queries.
* A global search across all objects (⌘K / Ctrl+K).

The API documentation is served on `/docs`.

See [this Wiki page](https://github.com/dirkjanm/ROADtools/wiki/Getting-started-with-ROADrecon) on how to get started.

## ROADtools Token eXchange (roadtx)
![PyPI version](https://img.shields.io/pypi/v/roadtx.svg)
[![Build Status](https://dev.azure.com/dirkjanm/ROADtools/_apis/build/status/dirkjanm.ROADtools?branchName=master)](https://dev.azure.com/dirkjanm/ROADtools/_build/latest?definitionId=19&branchName=master)

roadtx is a tool for exchanging and using different types of Azure AD issued tokens. It supports many different authentication flows, device registration and PRT related operations. For an overview of the tool, see the [roadtx Wiki](https://github.com/dirkjanm/ROADtools/wiki/ROADtools-Token-eXchange-(roadtx)).

### Installation
There are multiple ways to install roadtx. Note that roadtx requires Python 3.10 or newer.

**Using a published version on PyPi**  
Stable versions can be installed with `pip install roadtx`. This will automatically add the `roadtx` command to your PATH.

**Using a version from GitHub** 
You can clone this repository and install `roadlib` and then `roadtx` to make sure you have the latest versions of both the tool and the library:

```
pip install roadlib/
pip install roadtx/
```

You can also install them in development mode with `pip install -e roadtx/`.

### Using roadtx
See [the Wiki](https://github.com/dirkjanm/ROADtools/wiki/ROADtools-Token-eXchange-(roadtx)) on how to use roadtx. See also the [release blog](https://dirkjanm.io/introducing-roadtools-token-exchange-roadtx/).
