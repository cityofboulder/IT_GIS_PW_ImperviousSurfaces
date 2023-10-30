SELECT CONVERT(nvarchar(36), GlobalID) as guid
      ,'Miscellaneous' + ': ' + type as surftype
      ,Shape.STAsBinary() as geometry
FROM PW.ImperviousMisc_evw