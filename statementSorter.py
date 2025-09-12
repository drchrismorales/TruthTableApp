import statementParser
import equivalence
import argument

def parse(text):
    text = text.strip()
    # Is it an Equivalence?
    for c in equivalence.Equivalence.equivalentChars:
        if c in text:
            return equivalence.Equivalence(text)
    # Is it an Argument?
    for c in argument.Argument.conclusionChars:
        if c in text:
            return argument.Argument(text)
    # Otherwise, treat as a simple Statement
    return statementParser.Statement(text)
