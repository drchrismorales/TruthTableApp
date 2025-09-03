
class LogicalStatementInterface():
    def __init__(self, text):
        raise NotImplementedError("This is an interface class.")

    def __str__(self):
        raise NotImplementedError("This is an interface class.")

    def __lt__(self, other):
        raise NotImplementedError("This is an interface class.")

    def printStringAndOwnership(self):
        raise NotImplementedError("This is an interface class.")

    def prettyPrint(self):
        raise NotImplementedError("This is an interface class.")

    def reportSimpleStatements(self):
        raise NotImplementedError("This is an interface class.")

    def reportAllSubstatements(self):
        raise NotImplementedError("This is an interface class.")
    
    def countComplexSubstatements(self):
        raise NotImplementedError("This is an interface class.")

    def rectifyGraph(self):
        raise NotImplementedError("This is an interface class.")

    def rectifySubstatements(self, statementMap):
        raise NotImplementedError("This is an interface class.")

    def allSubstatements(self):
        raise NotImplementedError("This is an interface class.")

    def allSubstatementsWithDepth(self, depth=0):
        raise NotImplementedError("This is an interface class.")

    def printTree(self):
        raise NotImplementedError("This is an interface class.")
    
    def evaluate(self, valuation):
        raise NotImplementedError("This is an interface class.")


