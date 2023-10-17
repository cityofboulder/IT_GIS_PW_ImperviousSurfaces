SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Sidewalk' as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.SidewalkArea_evw