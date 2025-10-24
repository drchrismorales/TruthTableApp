import statementInterface
import statementParser
import pandas
import statementHelpers as sh
import logger

class Argument(statementInterface.LogicalStatementInterface):
    separatorChars = [",", ";", "\n"]
    conclusionChars = ["∴"]
    def __init__(self, text):
        self.text = text
        self.premises = []
        self.conclusion = None
        # Empty argument is allowed (for initialization purposes)
        if len(text) == 0:
            return
        # Split on conclusion character first
        parts = None
        for char in Argument.conclusionChars:
            if char in text:
                parts = text.split(char)
                break
        if parts is None or len(parts) != 2:
            raise ValueError("Argument must contain exactly one conclusion symbol (∴)")
        # Parse conclusion
        self.conclusion = statementParser.Statement(parts[1].strip())
        # Parse premises
        premises_text = parts[0].strip()
        premises_parts = [premises_text]
        for char in Argument.separatorChars:
            if char in premises_text:
                premises_parts = [p.strip() for p in premises_text.split(char) if p.strip()]
                break
        if not premises_parts:
            raise ValueError("Argument must contain at least one premise.")
        if premises_parts[-1] == '':
            premises_parts = premises_parts[:-1]
        for premise_text in premises_parts:
            self.premises.append(statementParser.Statement(premise_text))
        

    def __str__(self):
        premises_str = "; ".join([str(p) for p in self.premises])
        return f"Premises: [{premises_str}] Therefore, Conclusion: [{self.conclusion}]"

    def __lt__(self, other):
        #Note: this is a somewhat arbitrary ordering, but it is consistent and allows sorting
        # Cannot compare Argument with Equivalence
        # The implicit assumption is that an Argument is only ever being compared to its own substatements.
        # With Argument/argument comparisons handled because....
        if isinstance(other, Argument):
            if len(self.premises) != len(other.premises):
                return len(self.premises) < len(other.premises)
            p1 = sorted(self.premises)
            p2 = sorted(other.premises)
            for s1, s2 in zip(p1, p2):
                if s1 != s2:
                    return s1 < s2
            return self.conclusion < other.conclusion
        elif isinstance(other, statementParser.Statement):
            return False
        else:
            raise ValueError("Cannot compare Argument with non-Statement or non-Argument")

    def printStringAndOwnership(self):
        info_list = [p.printStringAndOwnership() for p in self.premises]
        info_conclusion = self.conclusion.printStringAndOwnership()
        combined_string = ";".join([info[0] for info in info_list]) + ";∴" + info_conclusion[0]
        combined_ownership = []
        combined_operators = []
        for info in info_list:
            combined_ownership.extend(info[1])
            combined_operators.extend(info[2])
            combined_ownership.append(self)
            combined_operators.append(False)  # Separator "operator"
        combined_ownership.append(self)
        combined_operators.append(False)  # Conclusion "operator"
        combined_ownership.extend(info_conclusion[1])
        combined_operators.extend(info_conclusion[2])
        return (combined_string, combined_ownership, combined_operators)

    def prettyPrint(self):
        premises_str = "; ".join([p.prettyPrint() for p in self.premises])
        return f"{premises_str}; ∴ {self.conclusion.prettyPrint()}"

    def reportSimpleStatements(self):
        simple_statements = set()
        for premise in self.premises:
            simple_statements.update(premise.reportSimpleStatements())
        simple_statements.update(self.conclusion.reportSimpleStatements())
        return simple_statements

    def reportAllSubstatements(self):
        all_substatements = set()
        for premise in self.premises:
            all_substatements.update(premise.reportAllSubstatements())
        all_substatements.update(self.conclusion.reportAllSubstatements())
        return all_substatements

    def countComplexSubstatements(self):
        count = 0
        for premise in self.premises:
            count += premise.countComplexSubstatements()
        count += self.conclusion.countComplexSubstatements()
        return count

    def rectifyGraph(self):
        Argument_copy = Argument(self.prettyPrint())
        statementMap = {}
        for s in Argument_copy.allSubstatements():
            statementMap[s.prettyPrint()] = s
        Argument_copy.rectifySubstatements(statementMap)
        return Argument_copy

    def rectifySubstatements(self, statementMap):
        # Replace substatements with those from the map
        self.premises = [statementMap[p.prettyPrint()] for p in self.premises]
        self.conclusion = statementMap[self.conclusion.prettyPrint()]
        # Recursively rectify substatements
        for premise in self.premises:
            premise.rectifySubstatements(statementMap)
        self.conclusion.rectifySubstatements(statementMap)

    def allSubstatements(self):
        for premise in self.premises:
            yield premise
            yield from premise.allSubstatements()
        yield self.conclusion
        yield from self.conclusion.allSubstatements()

    def allSubstatementsWithDepth(self, depth=1):
        for premise in self.premises:
            yield (premise, depth)
            yield from premise.allSubstatementsWithDepth(depth + 1)
        yield (self.conclusion, depth)
        yield from self.conclusion.allSubstatementsWithDepth(depth + 1)

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
        raise ValueError("The argument that a given set of premises entail a given conclusion is a meta-logic statement, and so cannot be evaluated for an individual valuation.")

    def checkValidity(self):
        # An argument is valid if there is no valuation that makes all premises true and the conclusion false
        simple_statements = self.reportSimpleStatements()
        simple_list = list(simple_statements)
        simple_list.sort()
        valuations = sh.createValuations(simple_list)
        df = pandas.DataFrame(valuations)
        # Evaluate both statements for each row
        for _, row in df.iterrows():
            valuation = row.to_dict()
            premises_true = all(p.evaluate(valuation) for p in self.premises)
            conclusion_true = self.conclusion.evaluate(valuation)
            if premises_true and not conclusion_true:
                return False
        return True

