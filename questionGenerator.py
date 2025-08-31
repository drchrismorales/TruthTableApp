import statementParser
import random

def makeRandomQuestion(connective_list, max_simple, connective_depth, with_replacement=True):
    question = statementParser.Statement("")
    simple_set = set()
    simple_var = ord('P')
    current_list = connective_list[:]
    if "not" in current_list:
        current_list.remove("not")
    picked = random.choice(current_list)
    question.connective = picked
    # Create a connective coordinator to manage depth
    connective_coordinator = lambda: None
    connective_coordinator.depth = connective_depth
    connective_coordinator.depth -= 1
    if connective_coordinator.depth > 0:
        current_list = connective_list[:]
        current_list.remove(picked)
        question.subStatements.append(makeRandomSubstatement(current_list, connective_list, simple_set, max_simple, connective_coordinator, with_replacement))
        #Note (guaranteed to be binary. Not is not chosen, and we will treat n-ary connectives as binary for random generation)
        question.subStatements.append(makeRandomSubstatement(current_list, connective_list, simple_set, max_simple, connective_coordinator, with_replacement))
    else:
        substatement = statementParser.Statement(chr(simple_var))
        question.subStatements.append(substatement)
        simple_set.add(chr(simple_var))
        # Pick next substatement
        if(len(simple_set) >= max_simple):
            # Randomly choose from existing simple variables
            simple_list = list(simple_set)
            if(len(simple_list) > 1):
                simple_list.remove(chr(simple_var))
                simple_var = ord(random.choice(simple_list))
            # else do nothing, just reuse the one simple variable
        else:
            # Increment simple variable
            simple_var += 1
            if(simple_var > ord('Z')):
                simple_var = ord('A')
        substatement = statementParser.Statement(chr(simple_var))
        question.subStatements.append(substatement)
        simple_set.add(chr(simple_var))
    random.shuffle(question.subStatements)
    return question.prettyPrint()

def makeRandomSubstatement(current_list, connective_list, simple_set, max_simple, connective_coordinator, with_replacement):
    if connective_coordinator.depth > 0:
        substatement = statementParser.Statement("")
        picked = random.choice(current_list)
        substatement.connective = picked
        connective_coordinator.depth -= 1
        substatement_count = 2
        if picked == "not":
            substatement_count = 1
        if(with_replacement):
            current_list = connective_list[:]
        current_list.remove(picked)
        for i in range(substatement_count):
            substatement.subStatements.append(makeRandomSubstatement(current_list, connective_list, simple_set, max_simple, connective_coordinator, with_replacement))
        random.shuffle(substatement.subStatements)
        return substatement
    else:
        if len(simple_set) == 0:
            # First simple variable
            simple_var = ord('P')
            substatement_text = chr(simple_var)
            simple_set.add(substatement_text)
            return statementParser.Statement(substatement_text)
        elif len(simple_set) < max_simple and len(simple_set) > 0 and len(simple_set) < 26:
            # The next simple variable is one more than the previous highest
            simple_var = ord('P') + len(simple_set)
            if simple_var > ord('Z'):
                simple_var = ord('A') + (simple_var - ord('Z') - 1)
            substatement_text = chr(simple_var)
            simple_set.add(substatement_text)
            return statementParser.Statement(substatement_text)
        else:
            # Randomly choose from existing simple variables
            simple_list = list(simple_set)
            substatement_text = random.choice(simple_list)
            return statementParser.Statement(substatement_text)
    raise ValueError("Should not reach here")

