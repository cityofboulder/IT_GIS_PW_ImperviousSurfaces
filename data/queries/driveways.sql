SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Driveway' as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.Driveway_evw
WHERE LIFECYCLE = 'Active'