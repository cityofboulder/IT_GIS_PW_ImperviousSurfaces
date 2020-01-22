## Impervious Surfaces for Utility Billing

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


