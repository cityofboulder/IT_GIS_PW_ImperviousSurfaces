SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Road' as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.RoadArea_evw
WHERE LIFECYCLE = 'Active'