SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Building' as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.Building_evw
WHERE LIFECYCLE = 'Active'