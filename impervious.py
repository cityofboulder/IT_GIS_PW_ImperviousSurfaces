import os
import shelve
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


# Create a class for impervious layers
class Impervious:
    def __init__(self, lyr):
        self.name = list(lyr)[0]
        self.location = os.path.join(edit_conn, "PW.PWAREA")
        self.path = os.path.join(self.location, self.name)
        self.query = "LIFECYCLE = 'Active'" + list(lyr)[1]
        self.rows = self.rows()

    def __hash__(self):
        return hash(self.__key())

    def __key(self):
        """Creates a tuple ordered by GLOBALIDs, used for hash comparisons."""

        key = tuple(sorted(self.rows, key=lambda y: y[0]))
        return key

    def rows(self):
        """Returns a list of tuples representing (GLOBALID, SHAPE) pairs."""

        fields = ["GLOBALID", "SHAPE@"]
        rows = []

        with arcpy.da.SearchCursor(self.path, fields, self.query) as cursor:
            for row in cursor:
                rows.append((row[0], row[1]) for i in range(len(fields)))

        return rows

    def store_current(self):
        """Stores the __key() of a table for hash comparisons."""
        with shelve.open('.\\log\\previous_run', 'c') as db:
            db[self.name] = self.__key()

    def equals_previous(self):
        """Compares the current table to the previous run to ID changes."""
        try:
            with shelve.open('.\\log\\previous_run', 'c') as db:
                previous = db[self.name]
            if hash(self) == hash(previous):
                return True
            else:
                return False
        except KeyError:
            self.store_current()


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
for layer in layers:
    feature = Impervious(layer)
