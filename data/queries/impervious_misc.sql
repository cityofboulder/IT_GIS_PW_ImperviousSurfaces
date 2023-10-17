SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Miscellaneous' as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.ImperviousMisc_evw
WHERE LIFECYCLE = 'Active'