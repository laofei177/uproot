class DirectoryInfo(object):
    
    def __init__(self, fNbytesKeys, fNbytesName, fSeekKeys):
        self.fVersion = 5
        self.fDatimeC = 1573188772
        self.fDatimeM = 1573188772
        self.fNbytesKeys = fNbytesKeys
        self.fNbytesName = fNbytesName
        self.fSeekDir =  100
        self.fSeekParent =  0
        self.fSeekKeys = fSeekKeys
        
    def first(self):
        packer = ">hIIii"
        return packer, self.fVersion, self.fDatimeC, self.fDatimeM, self.fNbytesKeys, self.fNbytesName
    
    def second(self):
        packer = ">iii"
        return packer, self.fSeekDir, self.fSeekParent, self.fSeekKeys
        