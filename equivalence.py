import statementParser
import statementInterface
import statementHelpers as sh
import pandas

# Implements an Equivalence class to represent and check logical equivalence between two Statements
# Implements the same "interface" methods as Statement for integration with the frontend/backend
class Equivalence(statementInterface.LogicalStatementInterface):
    equivalentChars = ["≡"]
    def __init__(self, text):
        self.statement1 = None
        self.statement2 = None
        # Empty equivalence is allowed (for initialization purposes)
        if len(text) == 0:
            return
        parts = None
        for char in Equivalence.equivalentChars:
            if char in text:
                parts = text.split(char)
                break
        if parts is None or len(parts) != 2:
            raise ValueError("Equivalence statement must contain exactly one equivalence symbol (≡)")
        self.statement1 = statementParser.Statement(parts[0].strip())
        self.statement2 = statementParser.Statement(parts[1].strip())

    def __str__(self):
        return f"[{self.statement1}] is equivalent to [{self.statement2}]?"

    def __lt__(self, other):
        if isinstance(other, Equivalence):
            return self.statement1 < other.statement1 or (self.statement1.prettyPrint() == other.statement1.prettyPrint() and self.statement2 < other.statement2)
        elif isinstance(other, statementParser.Statement):
            return False
        else:
            raise ValueError("Cannot compare Equivalence with non-Statement or non-Equivalence")

    def printStringAndOwnership(self):
        # Concatenate each list from the returned ordered tripplets
        info1 = self.statement1.printStringAndOwnership()
        info2 = self.statement2.printStringAndOwnership()
        combined_string = info1[0] + "≡" + info2[0]
        combined_ownership = info1[1] + [self] + info2[1]
        combined_operators = info1[2] + [False] + info2[2]
        return (combined_string, combined_ownership, combined_operators)

    def prettyPrint(self):
        return f"{self.statement1.prettyPrint()} ≡ {self.statement2.prettyPrint()}"
    
    def reportSimpleStatements(self):
        simple1 = self.statement1.reportSimpleStatements()
        simple2 = self.statement2.reportSimpleStatements()
        return simple1.union(simple2)
    
    def reportAllSubstatements(self):
        subs1 = self.statement1.reportAllSubstatements()
        subs2 = self.statement2.reportAllSubstatements()
        all_subs = set(subs1).union(set(subs2))
        #Note: statements are substatements of themselves in this formulation, so we don't need to add them explicitly
        return all_subs

    def countComplexSubstatements(self):
        return self.statement1.countComplexSubstatements() + self.statement2.countComplexSubstatements()

    def rectifyGraph(self):
        Equivalence_copy = Equivalence(f"{self.statement1.prettyPrint()} ≡ {self.statement2.prettyPrint()}")
        statementMap = {}
        for s in Equivalence_copy.allSubstatements():
            statementMap[s.prettyPrint()] = s
        Equivalence_copy.rectifySubstatements(statementMap)
        return Equivalence_copy

    def rectifySubstatements(self, statementMap):
        # Replace substatements with those from the map
        self.statement1 = statementMap[self.statement1.prettyPrint()]
        self.statement2 = statementMap[self.statement2.prettyPrint()]
        # Recursively rectify substatements
        self.statement1.rectifySubstatements(statementMap)
        self.statement2.rectifySubstatements(statementMap)

    # An iterator that yields all substatements of this equivalence, NOT including itself
    def allSubstatements(self):
        yield self.statement1
        yield from self.statement1.allSubstatements()
        yield self.statement2
        yield from self.statement2.allSubstatements()

    # An iterator that yields all substatements of this equivalence, NOT including itself, along with their depth
    def allSubstatementsWithDepth(self, depth=1):
        yield (self.statement1, depth)
        yield from self.statement1.allSubstatementsWithDepth(depth + 1)
        yield (self.statement2, depth)
        yield from self.statement2.allSubstatementsWithDepth(depth + 1)

    def printTree(self):
        print(self.prettyPrint())
        for s, depth in self.allSubstatementsWithDepth():
            spacer = ""
            if depth > 0:
                spacer = "└─"
                if depth > 1:
                    spacer = "  " * (depth - 1) + spacer
            print(f"{spacer}{s.prettyPrint()}")

    def evaluate(self, valuation):
        raise ValueError("Equivalence is a meta-logic statement, and so cannot be evaluated for an individual valuation.")

    def checkEquivalence(self):
        simple_statements_1 = self.statement1.reportSimpleStatements()
        simple_statements_2 = self.statement2.reportSimpleStatements()
        if simple_statements_1 != simple_statements_2:
            return False
        # Create valuation dataframe
        simple_list = list(simple_statements_1)
        simple_list.sort()
        valuations = sh.createValuations(simple_list)
        df = pandas.DataFrame(valuations)
        # Evaluate both statements for each row
        for i in range(len(df)):
            row = df.iloc[i]
            if self.statement1.evaluate(row) != self.statement2.evaluate(row):
                return False
        return True