# Impervious Surfaces for Utility Billing

## Background
---

This script utilizes planimetric data from city sources to derive a layer that can be used for estimating impervious area on properties for utility billing purposes. In the broadest terms, it does the following:

1. Query all 'Active' assets within the planimetrics. Utility Billing only cares about structures and surfaces that have already been put into place and they do not want proposed surfaces skewing impervious area calculations.

2. Creates a *pseudo-topology* of items. For example, if a Building polygon overlaps a Driveway polygon, the script will "over-rule" the bit of intersecting Driveway and call it a Building. The hierarchy for this logic is as follows:

    - Medians (Maintenance Areas with FACILITYTYPE = 'Median' AND SURFTYPE = 'Hard')
    - Buildings
    - Roads
    - Parking Lots (SURFACETYPE = 'Impervious')
    - Driveway
    - Sidewalk
    - ImperviousMisc

## Assumptions
---

This script assumes that the user has access to &mdash; and working knowledge of &mdash; the following software:

- ArcGIS Pro 2.4+
- Python 3.6+

This script hinges on the ability to leverage `arcpy` as well as the `conda` environment that both ship with ArcGIS Pro.

## Setup and Use
---

### Instructions

1. Ensure that your computer knows where ArcGIS Pro's conda environment lives

    - Type in `where conda` in your cmd prompt. If it's set up properly, that command should return something like `C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe`
    - If that does not come up, add the file path containing Pro's conda.exe to your system environment variables.

1. Add the following to the config file:

    - whether to check the component layers against the last script run
    - file location of your sde connection used for editing
    - file location of your sde connection used for reading
    - email password (both in the logging section and email password section)
    - email recipients

2. Run the `setup_conda_env.bat` by double-clicking it
3. Run the `run_script.bat` by double-clicking it

### Explanation of setup files

The `setup_conda_env.bat` file helps manage the creation of conda environments and the installation of python libraries inside that environment.

The `run_script.bat` file runs the python file within that new conda environment's python executable.