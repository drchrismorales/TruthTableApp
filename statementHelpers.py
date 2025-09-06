import pandas
import statementInterface
import logger

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
                    logger.logger.error("Missing substatement: %s for statement: %s", sub.prettyPrint(), s.prettyPrint())
                    return False
            seenSet.add(s)
    return True

# Compare two dataframes (truth tables) for equivalence (ie, same columns and rows, but row and column order may differ)
def dataframesEquivalent(df1, df2):
    #type: (pandas.DataFrame, pandas.DataFrame) -> tuple[bool, list[int]|None]
    # Normalise column order and row order
    df1 = df1.sort_index(axis=1)
    df2 = df2.sort_index(axis=1)
    df11 = df1.sort_values(by=df1.columns.tolist()).reset_index(drop=True)
    df21 = df2.sort_values(by=df2.columns.tolist()).reset_index(drop=True)
    # Now compare
    equal = df11.equals(df21)
    if not equal:
        return False, None
    # If equal, return the row ordering that would convert df1 to df2
    row_ordering = []
    for i in range(len(df1)):
        row = df1.iloc[i]
        for j in range(len(df2)):
            if row.equals(df2.iloc[j]):
                row_ordering.append(j)
                break
    return True, row_ordering

def createValuations(simpleStatements):
    #type: (list[str]) -> dict[str, list[bool]]
    valuations = {}
    for s in simpleStatements:
        if len(valuations.keys()) == 0:
            valuations[s] = [True, False]
        else:
            oldlen = len(valuations[list(valuations.keys())[0]])
            for k in valuations.keys():
                valuations[k] = valuations[k] * 2
            valuations[s] = [True] * oldlen + [False] * oldlen
    return valuations

def calculateTruthTable(statement, value_df=None):
    if value_df is None:
        simple = statement.reportSimpleStatements()
        simple = list(simple)
        simple.sort()
        valuations = createValuations(simple)
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

