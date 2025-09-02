import pandas

class Statement():
    nonletterSubstatementStartChars = ['¬', '~', '!']
    connectiveChars = ['&', '∧', '∨', '|', '→', '↔', '⊕']
    connectiveMap = {
        '&': 'and',
        '∧': 'and',
        '∨': 'or',
        '|': 'or',
        '→': 'implies',
        '↔': 'iff',
        '¬': 'not',
        '~': 'not',
        '!': 'not',
        '⊕': 'xor'
    }
    connectiveCharMap = {
        'and': '∧',
        'or': '∨',
        'implies': '→',
        'iff': '↔',
        'not': '¬',
        'xor': '⊕'
    }
    # Parse a statement into its substatements and connectives
    #  Allows an empty string, which represents no statement
    #   Suitable for use by other code to build up statements
    # Assumes that the statement is well-formed, with balanced parentheses
    #  and valid characters
    def __init__(self, text):
        self.text = text
        self.subStatements = []
        self.connective = None
        if len(text) == 0:
            return
        stack = []
        openParens = 0
        droppedLeadingParens = 0
        #print("Parsing:", text, "at depth")
        for i in range(len(text)):
            char = text[i]
            # Regular character
            if char.isalpha():
                stack.append(char)
            # Closing parenthesis
            elif char == ')':
                openParens -= 1
                if openParens < 0:
                    raise ValueError("Invalid statement format, negative open parenthesis", text, stack, char, i)
                # Do not add final parentheses to stack.
                if openParens > 0 or droppedLeadingParens == 0:
                    stack.append(char)
            elif char == '(':
                # Do not add leading parentheses to stack.
                if openParens > 0 or len(stack) != 0:
                    stack.append(char)
                else:
                    droppedLeadingParens += 1
                openParens += 1
            elif openParens > 0:
                stack.append(char)
            # Character that starts a substatement
            elif char in Statement.nonletterSubstatementStartChars:
                if len(stack) == 0:
                    stack.append(char)
                else:
                    raise ValueError("Invalid statement format", text, stack, char, i)
            # Handle n-ary connectives
            elif char in Statement.connectiveChars:
                if len(stack) == 0:
                    raise ValueError("Invalid statement format", text, stack, char, i)
                if char in Statement.connectiveChars:
                    if self.connective is not None and self.connective != Statement.connectiveMap[char]:
                        raise ValueError(
                            f"Invalid statement format: connective={self.connective}, text='{text}', stack={stack}, char='{char}', index={i}"
                        )
                    self.connective = Statement.connectiveMap[char]
                substatement = "".join(stack)
                stack = []
                self.subStatements.append(Statement(substatement))
        # Detect unary connective
        if len(stack) > 0 and stack[0] in Statement.connectiveMap and Statement.connectiveMap[stack[0]] == 'not' and self.connective is None:
            self.connective = 'not'
            stack = stack[1:]
            # Remove parentheses around substatement if present
            if len(stack) > 0 and stack[0] == '(':
                stack = stack[1:-1]
        # Finish last substatement
        if(len(stack) > 0 and self.connective is not None):
            substatement = "".join(stack)
            self.subStatements.append(Statement(substatement))
        # Validation
        if self.connective == "not" and len(self.subStatements) != 1:
            raise ValueError("Invalid statement format", text, stack, char)

    # Print a version suitable for debugging
    def __str__(self):
        outstr = ""
        if self.connective is None:
            return self.text
        if self.connective == "not":
            return self.connective + " " + f"[{str(self.subStatements[0])}]"
        #else it's an n-ary connective
        for i in range(len(self.subStatements)):
            outstr += f"[{str(self.subStatements[i])}]" 
            if i < len(self.subStatements) - 1:
                outstr += " " + self.connective + " "
        return outstr

    # Comparison operator: Sort first by length of prettyPrint, then lexicographically by prettyPrint
    #  Should ensure that 
    #   1) Simpler statements are always before more complex statements in the default evaluation order
    #   2) The order is consistent and deterministic: all non-identical statements can be ordered
    def __lt__(self, other):
        selfstr = self.prettyPrint()
        otherstr = other.prettyPrint()
        if len(selfstr) != len(otherstr):
            return len(selfstr) < len(otherstr)
        return selfstr < otherstr

    # Return a tuple (string, ownership list)
    #  Where string is a string representation of the statement, suitable for display to students
    #  and ownership list is a list of the same length, where each element is either None (for parentheses)
    #   or a reference to the Statement object that "owns" that character
    #   (i.e. the Statement object that should be referenced if that character is clicked on in a GUI or otherwise needs to be evaluated)
    def printStringAndOwnership(self):
        outstr = ""
        ownership = []
        operators = []
        if self.connective is None:
            outstr = self.text
            ownership = [self]*len(self.text)
            operators = [False]*len(self.text)
        elif self.connective == "not":
            subdata = self.subStatements[0].printStringAndOwnership()
            substr = subdata[0]
            subownership = subdata[1]
            suboperators = subdata[2]
            if(self.subStatements[0].connective is not None):
                outstr = Statement.connectiveCharMap[self.connective] + f"({substr})"
                # ~ is us, ( and ) are unowned (not really "part" of the substatement, and ditto for us)
                ownership = [self] + [None] + subownership + [None]
                operators = [True] + [False] + suboperators + [False]
            else:
                outstr = Statement.connectiveCharMap[self.connective] + f"{substr}"
                ownership = [self] + subownership
                operators = [True] + suboperators
        #else it's an n-ary connective
        else:
            for i in range(len(self.subStatements)):
                subdata = self.subStatements[i].printStringAndOwnership()
                substr = subdata[0]
                subownership = subdata[1]
                suboperators = subdata[2]
                if(self.subStatements[i].connective is not None and self.subStatements[i].connective != "not"):
                    outstr += f"({substr})"
                    ownership += [None] + subownership + [None]
                    operators += [False] + suboperators + [False]
                else:
                    outstr += f"{substr}"
                    ownership += subownership
                    operators += suboperators
                if i < len(self.subStatements) - 1:
                    outstr += Statement.connectiveCharMap[self.connective]
                    ownership += [self]
                    operators += [True]
        return (outstr, ownership, operators)

    # Print a version with logical symbols, suitable to display to students
    def prettyPrint(self):
        outstr = self.printStringAndOwnership()[0]
        # Add spaces around binary connectives for readability
        for c in Statement.connectiveChars:
            outstr = outstr.replace(c, f" {c} ")
        return outstr

    # Return a set of the simple statements that make up this statement
    def reportSimpleStatements(self):
        returnset = set()
        if self.connective is None:
            returnset.add(self.text)
        else:
            for s in self.subStatements:
                returnset.update(s.reportSimpleStatements())
        return returnset
    # Return a set of all substatements that make up this statement, including itself
    def reportAllSubstatements(self):
        returnset = set()
        returnset.add(self)
        if self.connective is not None:
            for s in self.subStatements:
                returnset.update(s.reportAllSubstatements())
        return returnset
    
    def countComplexSubstatements(self):
        i = 0
        for s in self.reportAllSubstatements():
            if s.connective is not None:
                i += 1
        return i

    # Creates a new Directed Acyclic Graph (DAG) statement where each distinct substatement is represented by a single Statement object,
    #  and all references to that substatement point to that single object
    def rectifyGraph(self):
        newStatement = Statement(self.text)
        statementMap = {}
        for s in newStatement.allSubstatements():
            statementMap[s.prettyPrint()] = s
        newStatement.rectifySubstatements(statementMap)
        return newStatement
    # Helper function for above
    # Given a map that links unique substatement strings to Statement objects,
    #  updates this statement and all its substatements to use those Statement objects
    # Because the map is built from the statement being rectified, the statement objects
    #  in the map will be modified as the recursion proceeds
    #  but this is not a problem as they will be modified to use only statement objects from the map
    # This means that statement objects that are NOT part of the map may not be rectified,
    #  but as they are in the process of being trimmed out of the tree anyway this is not a problem
    def rectifySubstatements(self, statementMap):
        if self.connective is not None:
            for i in range(len(self.subStatements)):
                self.subStatements[i] = statementMap[self.subStatements[i].prettyPrint()]
                self.subStatements[i].rectifySubstatements(statementMap)
    # An itterator that yields all substatements of this statement, including itself
    def allSubstatements(self):
        yield self
        for s in self.subStatements:
            yield from s.allSubstatements()

    # An itterator that yields all substatements of this statement, including itself, with depth attribute
    def allSubstatementsWithDepth(self, depth=0):
        yield (self, depth)
        for s in self.subStatements:
            yield from s.allSubstatementsWithDepth(depth + 1)

    # Print all substatements, indented by depth
    def printTree(self):
        for s, depth in self.allSubstatementsWithDepth():
            spacer = ""
            if depth > 0:
                spacer = "└─"
                if depth > 1:
                    spacer = "  " * (depth - 1) + spacer
            print(f"{spacer}{s.prettyPrint()}")
    
    # Evaluate the statement given a dictionary of valuations for the simple statements
    #  e.g. {'P': True, 'Q': False}
    # With the aid of a loop, can be used to generate a truth table
    def evaluate(self, valuation):
        if self.connective is None:
            if self.text not in valuation:
                raise ValueError("No valuation for statement", self.text)
            return valuation[self.text]
        elif self.connective == "not":
            return not self.subStatements[0].evaluate(valuation)
        elif self.connective == "and":
            result = True
            for s in self.subStatements:
                result = result and s.evaluate(valuation)
            return result
        elif self.connective == "or":
            result = False
            for s in self.subStatements:
                result = result or s.evaluate(valuation)
            return result
        elif self.connective == "implies":
            if len(self.subStatements) != 2:
                raise ValueError("Implication must have exactly two substatements", self.text)
            return (not self.subStatements[0].evaluate(valuation)) or self.subStatements[1].evaluate(valuation)
        elif self.connective == "iff":
            if len(self.subStatements) != 2:
                raise ValueError("Biconditional must have exactly two substatements", self.text)
            return self.subStatements[0].evaluate(valuation) == self.subStatements[1].evaluate(valuation)
        elif self.connective == "xor":
            result = False
            # Has the associative property, so can be n-ary, the general rule is that it's true if an odd number of substatements are true
            for s in self.subStatements:
                result = result != s.evaluate(valuation)
            return result
        else:
            raise ValueError("Unknown connective", self.connective)

# Check if a given ordering of substatements is a valid ordering for evaluation for a statement and its substatements
#  i.e. no statement appears before any of its substatements, and the final statement is this statement
# The ordering should be a list of Statement objects
def isValidEvaluationOrder(ordering):
    seenSet = set()
    for s in ordering:
        if s in seenSet:
            return False
        if s.connective is None:
            seenSet.add(s)
        else:
            substatementSet = s.reportAllSubstatements()
            for sub in substatementSet:
                if sub not in seenSet and sub != s:
                    print("Missing substatement", sub.prettyPrint(), "for statement", s.prettyPrint())
                    return False
            seenSet.add(s)
    return True

# Compare two dataframes (truth tables) for equivalence (ie, same columns and rows, but row and column order may differ)
def dataframesEquivalent(df1, df2):
    # Normalise column order and row order
    df1 = df1.sort_index(axis=1)
    df2 = df2.sort_index(axis=1)
    df11 = df1.sort_values(by=df1.columns.tolist()).reset_index(drop=True)
    df21 = df2.sort_values(by=df2.columns.tolist()).reset_index(drop=True)
    # Now compare
    return df11.equals(df21)

def calculateTruthTable(statement, value_df=None):
    if value_df is None:
        simple = statement.reportSimpleStatements()
        simple = list(simple)
        simple.sort()
        valuations = {}
        for s in simple:
            if len(valuations.keys()) == 0:
                valuations[s] = [True, False]
            else:
                oldlen = len(valuations[list(valuations.keys())[0]])
                for k in valuations.keys():
                    valuations[k] = valuations[k] * 2
                valuations[s] = [True] * oldlen + [False] * oldlen
        df = pandas.DataFrame(valuations)
    else:
        df = value_df.copy()
        valuations = df.to_dict(orient='list')
    df = pandas.DataFrame(valuations)
    allSub = statement.reportAllSubstatements()
    allSub = list(allSub)
    # Sort by length of prettyPrint, so that simpler statements are evaluated first
    allSub.sort()
    for s in allSub:
        #Skip simple statements, already in dataframe
        if s.connective is not None:
            df[s.prettyPrint()] = df.apply(lambda row: s.evaluate(row.to_dict()), axis=1)
    return df

