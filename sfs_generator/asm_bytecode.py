#!/usr/bin/env python3

class AsmBytecode:

    def __init__(self,begin,end,source,disasm,value):
        self.begin = begin
        self.end = end
        self.source = source
        self.disasm = disasm
        self.value = value


    def getBegin(self):
        return self.begin
    
    def setBegin(self, v):
        self.begin = v
        
    def getEnd(self):
        return self.end
    
    def setEnd(self, v):
        self.end = v
        
    def getSource(self):
        return self.source
    
    def setSource(self, v):
        self.source = v

    def getDisasm(self):
        return self.disasm
    
    def setDisasm(self, v):
        self.disasm = v

    def getValue(self):
        return self.value
    
    def setValue(self, v):
        self.value = v

    def __str__(self):
        content = "{begin:"+str(self.begin)+", end:"+str(self.end)+", source:"+str(self.source)+", name:"+str(self.disasm)+", value:"+str(self.value)+"}"
        return content

    def __repr__(self):
        content = "{begin:"+str(self.begin)+", end:"+str(self.end)+", source:"+str(self.source)+", name:"+str(self.disasm)+", value:"+str(self.value)+"}"
        return content

    def __eq__(self, other):
        return self.begin == other.begin and self.end == other.end and self.source == other.source and \
               self.disasm == other.disasm and self.value == other.value
