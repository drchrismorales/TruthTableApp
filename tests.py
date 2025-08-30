import statementParser
import questionGenerator
import random
import pandas

def test(text):
    st = statementParser.Statement(text)
    print(str(st))
    allSub = st.reportAllSubstatements()
    print("All substatements:")
    for s in allSub:
        print("", s.prettyPrint())
    st = st.rectifyGraph()
    allSub = st.reportAllSubstatements()
    print("All substatements (rectified):")
    for s in allSub:
        print("", s.prettyPrint())
    simple = st.reportSimpleStatements()
    simple = list(simple)
    simple.sort()
    print(simple)
    print(st.prettyPrint())
    #######################################################
    ## Truth table
    #######################################################
    print("Truth table")
    ttOne = statementParser.calculateTruthTable(st)
    #df['Result'] = df.apply(lambda row: st.evaluate(row.to_dict()), axis=1)
    print(ttOne)
    #Manually provide shuffled valuations
    valuations = {}
    random.shuffle(simple)
    for s in simple:
        if len(valuations.keys()) == 0:
            valuations[s] = [True, False]
        else:
            oldlen = len(valuations[list(valuations.keys())[0]])
            for k in valuations.keys():
                valuations[k] = valuations[k] * 2
            valuations[s] = [True] * oldlen + [False] * oldlen
    df = pandas.DataFrame(valuations)
    df = df.sample(frac=1).reset_index(drop=True)  # Shuffle rows
    ttTwo = statementParser.calculateTruthTable(st, df)
    print(ttTwo)
    print("Truth tables equivalent:", statementParser.dataframesEquivalent(ttOne, ttTwo))
    st.printTree()

if __name__ == "__main__":
    test("A ∧ B")
    print("----------------")
    test("~A ∧ B")
    print("----------------")
    test("(A ∧ B) ∨ ~ C")
    print("----------------")
    test("((A ∧ B) ∨ ~ C) → D")
    print("----------------")
    test("A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G ∧ H ∧ I ∧ J ∧ K")
    print("----------------")
    test("A ∧ (B ∨ C) ∧ D")
    print("----------------")
    test("~(Q ∨ P) ∧ (P ∨ Q)")
    print("----------------")
    # lots of nots
    test("~(~(~(~(~(~(~(~(~(~A)))))))))")
    print("----------------")
    # random questions
    for i in range(5):
        question = questionGenerator.makeRandomQuestion(["and", "or", "implies", "iff", "not"], 5, 4)
        test(question)
        print("----------------")
    # random questions
    for i in range(5):
        question = questionGenerator.makeRandomQuestion(["and", "or", "not"], 2, 3)
        test(question)
        print("----------------")
    for i in range(5):
        question = questionGenerator.makeRandomQuestion(["and", "or", "not"], 2, 2)
        test(question)
        print("----------------")
