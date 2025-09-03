import statementParser
import equivalence

def parse(text):
    text = text.strip()
    for c in equivalence.Equivalence.equivalentChars:
        if c in text:
            return equivalence.Equivalence(text)
    return statementParser.Statement(text)
