SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Parking Lot' as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.ParkingLot_evw
WHERE LIFECYCLE = 'Active'
      AND SURFACETYPE = 'Impervious'