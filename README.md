<div id="top"></div>

<!-- PROJECT SHIELDS -->
<!--
*** Using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->
<!-- [![Contributors][contributors-shield]][contributors-url] -->
<!-- [![Forks][forks-shield]][forks-url] -->
<!-- [![Stargazers][stars-shield]][stars-url] -->
[![Issues][issues-shield]][issues-url]
[![License][license-shield]][license-url]



<!-- PROJECT LOGO -->
<br />
<div align="center">

<h3 align="center">Impervious Surfaces for Utility Billing</h3>

  <p align="center">
    A Pythonic ETL package that creates a pseudo-topology of impervious surfaces and summarizes impervious coverage at the parcel level.
    <br />
    <a href="https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces/issues">Report Bug</a>
    ·
    <a href="https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces/issues">Request Feature</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

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

<p align="right">(<a href="#top">back to top</a>)</p>

### Built With

* [Python](https://www.python.org/)
* [arcpy](https://pro.arcgis.com/en/pro-app/3.1/arcpy/get-started/what-is-arcpy-.htm)

<p align="right">(<a href="#top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started

This script hinges on the ability to leverage `arcpy` as well as the `conda` environment that both ship with ArcGIS Pro. As a result, you must administer your conda environment through ArcGIS Pro's interface.

### Installation

1. Clone the repo
   ```sh
   git clone https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces.git
   ```
1. Navigate to the ArcGIS Pro conda environment manager and clone the base `arcgispro-py3` environment. Name it `imperviousenv`.

1. Ensure the following packages are downloaded to the new cloned environment:
   ```sh
   geopandas
   keyring
   sqlalchemy
   pyodbc
   ipykernel
   ```

<p align="right">(<a href="#top">back to top</a>)</p>



<!-- USAGE EXAMPLES -->
## Usage

This script is meant to be run on the City's `gisscript` server on a daily basis. Check the <a href="https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces/blob/main/scheduled_tasks/IT_GIS_PW_ImperviousSurface%20daily.xml">scheduled task configuration</a> for more info.

<p align="right">(<a href="#top">back to top</a>)</p>


## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

Jesse Nestler  - nestlerj@bouldercolorado.gov

Project Link: [https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces](https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces)

<p align="right">(<a href="#top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
[issues-shield]: https://img.shields.io/github/issues/cityofboulder/IT_GIS_PW_ImperviousSurfaces.svg?style=for-the-badge
[issues-url]: https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces/issues
[license-shield]: https://img.shields.io/badge/License-MIT-yellow.svg
[license-url]: https://github.com/cityofboulder/IT_GIS_PW_ImperviousSurfaces/blob/master/LICENSE.txt