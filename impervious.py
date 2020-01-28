import getpass
import logging
import logging.config
import logging.handlers

import yaml
import arcpy

# Initialize configurations
username = getpass.getuser()
user_email = f"{username}@bouldercolorado.gov"

with open(r'.\impervious-surfaces\config.yaml') as config_file:
    config = yaml.safe_load(config_file.read())
    logging.config.dictConfig(config['logging'])

read_conn = config['connections']['read']
edit_conn = config['connections']['edit']

# Define order for intersecting layers, and relevant queries for each
layers = [{"GISPROD3.PW.PWMaintenanceArea":
           "AND FACILITYTYPE = 'Median' AND SURFTYPE = 'Hard'"},
          {"GISPROD3.PW.Building": ""},
          {"GISPROD3.PW.RoadArea": ""},
          {"GISPROD3.PW.ParkingLot": "AND SURFACETYPE = 'Impervious'"},
          {"GISPROD3.PW.Driveway": ""},
          {"GISPROD3.PW.SidewalkArea": ""},
          {"GISPROD3.PW.ImperviousMisc": ""}]

# Move through each layer
for layer in sorted(layers, key=lambda x: layers[x]['order']):
    query = "LIFECYCLE = 'Active'"
    if layers[layer]['query']:
        query += ' AND ' + layers[layer]['query']
