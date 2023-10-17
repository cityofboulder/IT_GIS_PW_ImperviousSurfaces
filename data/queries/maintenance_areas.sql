SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Maintenance Area' as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.PWMaintenanceArea_evw
WHERE LIFECYCLE = 'Active'
      AND FACILITYTYPE = 'Median'
      AND SURFTYPE = 'Hard'