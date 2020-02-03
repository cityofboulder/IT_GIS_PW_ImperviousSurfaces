import os
import shelve
import logging
import logging.config
import logging.handlers

import yaml
import arcpy


class Impervious:
    def __init__(self, lyr):
        self.name = list(lyr)[0]
        self.location = os.path.join(read_conn, "PW.PWAREA")
        self.path = os.path.join(self.location, self.name)
        self.query = "LIFECYCLE = 'Active'" + list(lyr)[1]
        self.rows = self.rows()

    def __hash__(self):
        return hash(self.__key())

    def __key(self):
        """Creates a tuple ordered by GLOBALIDs, used for hash comparisons."""

        attributes = [(r["GLOBALID"], r["SHAPE@"]) for r in self.rows]
        key = tuple(sorted(attributes, key=lambda y: y[0]))
        return key

    def rows(self):
        """Returns a list of tuples representing (GLOBALID, SHAPE) pairs."""

        fields = ["GLOBALID", "SHAPE@"]
        rows = []

        with arcpy.da.SearchCursor(self.path, fields, self.query) as cursor:
            for row in cursor:
                r = {fields[i]: row[i] for i in range(len(fields))}
                rows.append(r)

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

    def memory_fc(self, template_fc):
        """Creates a feature class in memory based off of template schema."""
        fc = arcpy.CreateFeatureclass_management("in_memory",
                                                 self.name,
                                                 template=template_fc)
        arcpy.Append_management(self.path, fc, "NO_TEST")

        with arcpy.da.UpdateCursor(fc, ["ORIGIN"]) as cursor:
            for row in cursor:
                row[0] = self.name
                cursor.updateRow(row)

        return fc


def main(lyrs):
    # Define the output layer
    surfaces = os.path.join(edit_conn, "PW.ImperviousSurface")

    # Instantiate each layer as an Impervious class
    impervious_features = (Impervious(layer) for layer in lyrs)
    equals_previous = (imp.equals_previous() for imp in impervious_features)

    # See if any changes have been made to the layers involved
    if all(equals_previous):
        log.info("None of the layers have changed since the previous run...")
    else:
        # Check how far up the hierarchy the derived layer needs to change
        # 0 = MaintenanceAreas, 1 = Buildings, 2 = Roads, and so on
        idx = [i for i, x in enumerate(equals_previous) if not x][0]


if __name__ == '__main__':
    # Initialize configurations
    with open(r'.\config.yaml') as config_file:
        config = yaml.safe_load(config_file.read())
        logging.config.dictConfig(config['logging'])

    read_conn = config['connections']['read']
    edit_conn = config['connections']['edit']

    # Initialize the logger for this file
    log = config.logging.getLogger(__name__)

    # Define order for intersecting layers, and relevant queries for each
    # Dicts within a list helps enforce ordering
    layers = [{"GISPROD3.PW.PWMaintenanceArea":
               "AND FACILITYTYPE = 'Median' AND SURFTYPE = 'Hard'"},
              {"GISPROD3.PW.Building": ""},
              {"GISPROD3.PW.RoadArea": ""},
              {"GISPROD3.PW.ParkingLot": "AND SURFACETYPE = 'Impervious'"},
              {"GISPROD3.PW.Driveway": ""},
              {"GISPROD3.PW.SidewalkArea": ""},
              {"GISPROD3.PW.ImperviousMisc": ""}]

    try:
        main(layers)
    except Exception:
        log.exception("Something prevented the script from running")
