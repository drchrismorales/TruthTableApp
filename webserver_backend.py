from http.server import HTTPServer, BaseHTTPRequestHandler
import statementParser
import questionGenerator
import pandas as pd
import statementSorter
import statementInterface
import equivalence
import statementHelpers as sh

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        response_cookie = None
        response_body = ""
        #Fixme: logging
        print("Received GET request for path:", self.path)
        # Split html arguments away from path
        #Fixme: why is query here?
        path, _, query = self.path.partition('?')

        #  For now, if no path was given, default to truth table question page
        if not path or path == '/':
            path = '/truth_table_question'

        # Check for question in cookie
        st, st_DAG, split, nIDed, ordering, tt_row_ordering, subsequent_step = self.get_current_question_from_cookie(self.headers)

        question_type = "Equivalence" if isinstance(st, equivalence.Equivalence) else "Statement"

        form_data = self.get_form_data()
        # Route as-needed based on path and question status
        # Special overide cases (favicon, no question)
        if path == '/favicon.ico':
            self.send_response(204)
            return
        elif st is None:
            response_cookie, response_body = self.newQuestionPage()
        # Route to check pages based on path
        elif path == '/split_check':
            response_cookie, response_body = self.checkSplitStatementPage(form_data, st)
        elif path == '/identify_substatements_check':
            response_cookie, response_body = self.checkIdentifySubstatementsPage(form_data, st, nIDed)
        elif path == '/order_check':
            response_cookie, response_body = self.checkOrderSubstatementsPage(form_data, st_DAG)
        elif path == '/truth_table_check':
            response_cookie, response_body = self.checkTruthTablePage(form_data, st_DAG, ordering, question_type)
        elif path == '/identify_columns_check':
            response_cookie, response_body = self.checkIdentifyColumnsPage(form_data, st_DAG, ordering, tt_row_ordering)
        elif path == '/equivalence_check':
            response_cookie, response_body = self.checkEquivalencePage(form_data, st_DAG, ordering, tt_row_ordering)

        # Route to current question step pages based on question status
        elif not split:
            response_cookie, response_body = self.splitStatementPage(st)
        elif nIDed < st.countComplexSubstatements():
            response_cookie, response_body = self.identifySubstatementsPage(st, nIDed)
        elif len(ordering) != len(list(st_DAG.reportAllSubstatements())):
            response_cookie, response_body = self.orderSubstatementsPage(st_DAG)
        elif len(tt_row_ordering) != 2**len(list(st_DAG.reportSimpleStatements())):
            response_cookie, response_body = self.truthTablePage(st_DAG, ordering)
        elif question_type == "Statement":
            #That was the last question
            response_cookie, response_body = self.newQuestionPage()
        elif question_type == "Equivalence":
            if subsequent_step == 0:
                response_cookie, response_body = self.identifyColumnsPage(st_DAG, ordering, tt_row_ordering)
            elif subsequent_step == 1:
                response_cookie, response_body = self.equivalentQuestionPage(st_DAG, ordering, tt_row_ordering)
            else:
                #That was the last question
                response_cookie, response_body = self.newQuestionPage()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
        # Send the response
        self.send_response(200)
        if response_cookie is not None:
            self.send_header("Set-Cookie", response_cookie)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(response_body.encode("utf-8"))

    def newQuestionPage(self):
        #type: () -> tuple[str|None, str]
        st = self.getNewQuestion()
        response_cookie = self.bake_cookie(st, False, 0, [], [], 0)
        # Announce new question to student in body
        response_body = (
            "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>New Question</title></head>"
            f"<body><h2>New question generated: {st.prettyPrint()}</h2>"
        )
        # Add a "start working" button that will begin the first step
        response_body += (
            "<form method='GET' action='/truth_table_question'>"
            "<input type='submit' value='Start working on it' />"
            "</form></body></html>"
        )
        return response_cookie, response_body

    def getNewQuestion(self):
        #type: () -> statementInterface.LogicalStatementInterface
        # Generate a new question
        st = statementSorter.parse("P ∧ Q ≡ ~P ∨ ~Q")  # For testing
        print(st)
        print(st.prettyPrint())
        st.rectifyGraph()
        return st # For testing
        question = questionGenerator.makeRandomQuestion(["and", "or", "not", "xor","implies","iff"], 2, 2)
        st = statementSorter.parse(question)
        st = st.rectifyGraph()
        return st

    def splitStatementPage(self, st):
        #type: (statementInterface.LogicalStatementInterface) -> tuple[str|None, str]
        questionData = st.printStringAndOwnership()
        questionStr = questionData[0]
        # Ask the student to identify all logical operators in the statement
        HTML_out = f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Split Statement for {questionStr}</title></head><body>"
        HTML_out = HTML_out + f"<h2>Identify the logical operators in the statement: </h2>"
        # Output a table where each column contains a checkbox above one character of the statement
        HTML_out = HTML_out + "<form method='GET' action='/split_check'>"
        HTML_out = HTML_out + "<table border='1'><tr>"
        for i in range(len(questionStr)):
            HTML_out = HTML_out + f"<td><input type='checkbox' name='op_{i}' /></td>"
        HTML_out = HTML_out + "</tr><tr>"
        for i in range(len(questionStr)):
            HTML_out = HTML_out + f"<td>{questionStr[i]}</td>"
        HTML_out = HTML_out + "</tr></table>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' formaction='/split_check' />"
        HTML_out = HTML_out + "</form></body></html>"
        #return: No cookie, HTML body
        return None, HTML_out

    #Asks the current "Identify all symbols in the current substatemtent question"
    #Assumes that all operators that occur in the statement before nIDed have been identified,
    # so it displays them.
    def identifySubstatementsPage(self, st, nIDed):
        #type: (statementInterface.LogicalStatementInterface, int) -> tuple[str|None, str]
        questionData = st.printStringAndOwnership()
        questionStr = questionData[0]
        operators = questionData[2]
        # Figure out which operator we are currently asking about
        operator_indices = [i for i, is_op in enumerate(operators) if is_op]
        if nIDed >= len(operator_indices):
            # Should be impossible, we don't route here if nIDed is >= number of operators
            return None, "<html><body><h2>Error: No more operators to identify.</h2></body></html>"
        current_op_index = operator_indices[nIDed]
        # Print out a three-row table:
        # Row 1: Largly empty, with an arrow symbol (↓) above the current operator
        # Row 2: The characters of the statement, one per cell
        # Row 3: Checkboxes, one per character, to identify which are part of the current operator (With no checkbox below the current operator)
        HTML_out = f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Which symbols belong to the substatement(s) of the indicated operator?</title></head><body>"
        HTML_out = HTML_out + f"<h2>Which symbols belong to the substatement(s) of the indicated operator?</h2>"
        HTML_out = HTML_out + "<form method='GET' action='/identify_substatements_check'>"
        HTML_out = HTML_out + "<table border='1'><tr>"
        for i in range(len(questionStr)):
            if i == current_op_index:
                HTML_out = HTML_out + "<th>↓</th>"
            else:
                HTML_out = HTML_out + "<th></th>"
        HTML_out = HTML_out + "</tr><tr>"
        for i in range(len(questionStr)):
            HTML_out = HTML_out + f"<td>{questionStr[i]}</td>"
        HTML_out = HTML_out + "</tr><tr>"
        for i in range(len(questionStr)):
            if i == current_op_index:
                HTML_out = HTML_out + "<td></td>"
            else:
                HTML_out = HTML_out + f"<td><input type='checkbox' name='sub_{i}' /></td>"
        HTML_out = HTML_out + "</tr></table>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' />"
        HTML_out = HTML_out + "</form></body></html>"
        #return: No cookie, HTML body
        return None, HTML_out

    def orderSubstatementsPage(self, st):
        #type: (statementInterface.LogicalStatementInterface) -> tuple[str|None, str]
        substatements = list(st.reportAllSubstatements())
        ownership = st.printStringAndOwnership()[1]
        n_substatements = len(substatements)
        # Ask the students to pick a valid ordering of the substatements for their truth table
        HTML_out = f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Order the substatements for {st.prettyPrint()}</title></head><body>"
        HTML_out = HTML_out + f"<h2>Decide what order you'd like to evaluate the statements in:</h2>"

        sub_indices = self.interfaceOrder(substatements, ownership)

        # Print a two-column n-row table, where the first column contains the substatement,
        # and the second column contains a dropdown to select its order (1 to n_substatements)
        HTML_out = HTML_out + "<form method='GET' action='/order_check'>"
        HTML_out = HTML_out + "<table border='1'><tr><th>Substatement</th><th>Order</th></tr>"
        for index in sorted(sub_indices.keys()):
            sub = sub_indices[index]
            HTML_out = HTML_out + f"<tr><td>{sub.prettyPrint()}</td><td><select name='order_{index}'>"
            for order in range(1, n_substatements + 1):
                HTML_out = HTML_out + f"<option value='{order}'>{order}</option>"
            HTML_out = HTML_out + "</select></td></tr>"
        HTML_out = HTML_out + "</table>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' formaction='/order_check' />"
        HTML_out = HTML_out + "</form></body></html>"
        #return: No cookie, HTML body
        return None, HTML_out

    def truthTablePage(self, st, ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int]) -> tuple[str|None, str]
        question = st.prettyPrint()
        simple = list(st.reportSimpleStatements())
        statements = list(st.reportAllSubstatements())
        nrows = 2**len(simple)
        ncols = len(statements)
        n, m = nrows, ncols
        statements.sort()
        # Reorder the statements according to the provided ordering
        if ordering != []:
            if len(ordering) == len(statements):
                statements = [statements[i] for i in ordering]
            else:
                return None, "<html><body><h2>Error: Ordering length does not match number of statements.</h2></body></html>"
        # Print out a truth table with dropdowns for each cell
        HTML_out = f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Truth Table for {question}</title></head><body>"
        HTML_out = HTML_out + f"<h2>Fill in the Truth Table for {question}</h2>"
        HTML_out = HTML_out + f"<form method='GET' action='/truth_table_check'>"
        # Print the statement headers
        HTML_out = HTML_out + "<table border='1'><tr>"
        for j in range(m):
            HTML_out = HTML_out + f"<th>{statements[j].prettyPrint()}</th>"
        HTML_out = HTML_out + "</tr><tr>"
        for i in range(n):
            for j in range(m):
                HTML_out = HTML_out + (
                    f"<td><select name='field_{i}_{j}'>"
                    "<option value='' selected></option>"
                    "<option value='T'>T</option>"
                    "<option value='F'>F</option>"
                    "</select></td>"
                )
            HTML_out = HTML_out + "</tr>"
        HTML_out = HTML_out + "</table>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' formaction='/truth_table_check' />"
        HTML_out = HTML_out + "</form></body></html>"

        #return: No cookie, HTML body
        return None, HTML_out
    def identifyColumnsPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[str|None, str]
        question = st.prettyPrint()
        statements = list(st.reportAllSubstatements())
        ncols = len(statements)
        m = ncols
        statements.sort()
        # Use the helper to recreate the truth table
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return None, "<html><body><h2>Error: Could not recreate truth table.</h2></body></html>"
        # Print out the truth table with the correct answers filled in, and checkboxes below each column
        HTML_out = f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Identify the columns needed to answer the {question}</title></head><body>"
        HTML_out += f"<h2>Identify the columns that are needed to answer the question: {question}</h2>"
        HTML_out += "<form method='GET' action='/identify_columns_check'>"
        #Begin the table
        HTML_out += "<table border='1'>"
        # Print the truth table
        HTML_out += printTruthTableToTD(df)
        # Print checkboxes below each column
        HTML_out += "<tr>"
        for j in range(m):
            HTML_out += f"<td><input type='checkbox' name='col_{j}' /></td>"
        HTML_out += "</tr>"
        HTML_out += "</table>"
        HTML_out += "<input type='submit' value='Submit' formaction='/identify_columns_check' />"
        HTML_out += "</form></body></html>"
        #return: No cookie, HTML body
        return None, HTML_out

    def equivalentQuestionPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[str|None, str]
        # Recreate the truth table
        if not isinstance(st, equivalence.Equivalence):
            return None, "<html><body><h2>Error: Not an equivalence question.</h2></body></html>"
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return None, "<html><body><h2>Error: Could not recreate truth table.</h2></body></html>"
        question = st.prettyPrint()
        # Ask the student if the two statements are equivalent, printing the truth table with up-arrows under the columns that are needed to answer the question
        HTML_out = f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Are the two statements equivalent?</title></head><body>"
        HTML_out += f"<h2>Are the two statements equivalent? {question}</h2>"
        HTML_out += "<form method='GET' action='/equivalence_check'>"
        #Begin the table
        HTML_out += "<table border='1'>"
        # Print the truth table
        HTML_out += printTruthTableToTD(df)
        # Print a (mostly-empty) row with up-arrows under the columns that are needed to answer the question
        right_side = st.statement2.prettyPrint()
        left_side = st.statement1.prettyPrint()
        HTML_out += "<tr>"
        for col in df.columns:
            if col == left_side or col == right_side:
                HTML_out += "<td>↑</td>"
            else:
                HTML_out += "<td></td>"
        HTML_out += "</tr>"
        HTML_out += "</table>"
        # Add radio buttons for Yes/No
        HTML_out += "<p>Are the two statements equivalent?</p>"
        HTML_out += "<input type='radio' id='yes' name='equiv' value='yes'>"
        HTML_out += "<label for='yes'>Yes</label><br>"
        HTML_out += "<input type='radio' id='no' name='equiv' value='no'>"
        HTML_out += "<label for='no'>No</label><br>"
        HTML_out += "<input type='submit' value='Submit' formaction='/equivalence_check' />"
        HTML_out += "</form></body></html>"
        #return: No cookie, HTML body
        return None, HTML_out

    def checkSplitStatementPage(self, form_data, st):
        #type: (dict, statementInterface.LogicalStatementInterface) -> tuple[str|None, str]
        questionData = st.printStringAndOwnership()
        operators = questionData[2]
        response_cookie = None
        if form_data is None:
            return None, "No form data received."
        # Check which checkboxes were ticked
        selected = [False] * len(operators)
        for key in form_data.keys():
            if key.startswith('op_'):
                _, i = key.split('_')
                try:
                    idx = int(i)
                    if 0 <= idx < len(selected):
                        selected[idx] = True
                except ValueError:
                    continue
        # Compare selected to operators
        print("Selected:", selected)
        print("Answer key:", operators)
        correct = (selected == operators)
        HTML_response = ""
        if correct:
            # Update the cookie to mark the statement as split
            cookie_question = cookieEncode(st.prettyPrint())
            response_cookie = self.bake_cookie(st, True, 0, [], [], 0)
            HTML_response = "<html><body><h2>Correct!</h2></body></html>"
            # Add a button to "Continue" that links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Continue' /></form>"
        else:
            HTML_response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that also links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Try again' /></form>"
        return response_cookie, HTML_response

    def checkIdentifySubstatementsPage(self, form_data, st, nIDed):
        #type: (dict, statementInterface.LogicalStatementInterface, int) -> tuple[str|None, str]
        questionData = st.printStringAndOwnership()
        questionStr = questionData[0]
        ownership = questionData[1]
        operators = questionData[2]
        response_cookie = None
        # Figure out which operator we are currently asking about
        operator_indices = [i for i, is_op in enumerate(operators) if is_op]
        if nIDed >= len(operator_indices):
            # Should be impossible, we don't route here if nIDed is >= number of operators
            return None, "<html><body><h2>Error: No more operators to identify.</h2></body></html>"
        current_op_index = operator_indices[nIDed]
        if form_data is None:
            return None, "No form data received."
        # Check which checkboxes were ticked
        selected = [False] * len(ownership)
        for key in form_data.keys():
            if key.startswith('sub_'):
                _, i = key.split('_')
                try:
                    idx = int(i)
                    if 0 <= idx < len(selected):
                        selected[idx] = True
                except ValueError:
                    continue
        # Mark the current operator position as selected (there is no checkbox for it)
        selected[current_op_index] = True
        current_st = ownership[current_op_index]
        current_substatements = current_st.reportAllSubstatements()
        # Create answer key:
        answer_key = [False] * len(ownership)
        # Use the ownership information to determine the correct selection
        for i in range(len(ownership)):
            if ownership[i] in current_substatements:
                answer_key[i] = True
        # Assess correctness
        #  As currently impelmented, parentheses have no owner, so they must be ignored in the comparison
        correct = True
        print("Selected:", selected)
        print("Answer key:", answer_key)
        for i in range(len(ownership)):
            if ownership[i] is None:
                continue
            if selected[i] != answer_key[i]:
                correct = False
                break
        HTML_response = ""
        if correct:
            # Update the cookie to mark the next operator as to be identified
            response_cookie = self.bake_cookie(st, True, nIDed + 1, [], [], 0)
            HTML_response = "<html><body><h2>Correct!</h2></body></html>"
            # Add a button to "Continue" that links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Continue' /></form>"
        else:
            HTML_response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that also links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Try again' /></form>"
        return response_cookie, HTML_response

    def checkOrderSubstatementsPage(self, form_data, st):
        #type: (dict, statementInterface.LogicalStatementInterface) -> tuple[str|None, str]
        # Get all substatements
        substatements = list(st.reportAllSubstatements())
        ownership = st.printStringAndOwnership()[1]
        response_cookie = None
        if form_data is None:
            return None, "No form data received."

        # Make a list of the selected values
        selected_ordering = [None] * len(substatements)
        for k in form_data.keys():
            if k.startswith('order_'):
                _, index = k.split('_')
                try:
                    idx = int(index)
                    if 0 <= idx < len(selected_ordering):
                        selected_ordering[idx] = int(form_data[k])
                except ValueError:
                    continue
        # Check if the ordering is valid, interface-wise (i.e. all numbers 1 to n used exactly once, no remaining None)
        print("Selected ordering:", selected_ordering)
        valid = (None not in selected_ordering) and (len(set(selected_ordering)) == len(selected_ordering))
        if valid:
            for i in range(len(selected_ordering)):
                if selected_ordering[i] < 1 or selected_ordering[i] > len(selected_ordering):
                    valid = False
                    break
        if not valid:
            HTML_response = "<html><body><h2>Invalid ordering. Try again.</h2></body></html>"
            # Add a button to "Try again" that also links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Try again' /></form>"
            return None, HTML_response
        #Convert the ordering from 1-indexed to 0-indexed
        selected_ordering = [x - 1 for x in selected_ordering]
        print("Normalized selected ordering:", selected_ordering)
        sub_indices = self.interfaceOrder(substatements, ownership)
        print("Interface order:", sub_indices)
        # Order the list of substatements by where they first appear in the main statement
        ordered_substatements = [sub_indices[i] for i in sorted(sub_indices.keys())]
        print("Current substatements:", [s.prettyPrint() for s in ordered_substatements])
        # Reorder the substatements according to the selected ordering
        ordered_substatements = [x for _, x in sorted(zip(selected_ordering, ordered_substatements))]
        print("Reordered substatements:", [s.prettyPrint() for s in ordered_substatements])
        # Check if the ordering is logically valid (i.e. no statement appears before its substatements)
        correct = sh.isValidEvaluationOrder(ordered_substatements)
        # The Parser considers the natural order to be the sorted order of the substatements, so we need to adjust for that
        tt_order = list(st.reportAllSubstatements())
        tt_order.sort()
        # What would tt_order need to be reordered by to match selected_ordering?
        # Get the indices of each substatement in tt_order
        tt_indices = [tt_order.index(s) for s in ordered_substatements]
        HTML_response = ""
        if correct:
            # Update the cookie with the new ordering
            response_cookie = self.bake_cookie(st, True, len(substatements), tt_indices, [], 0)
            HTML_response = "<html><body><h2>Correct!</h2></body></html>"
            # Add a button to "Continue" that links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Continue' /></form>"
        else:
            HTML_response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that also links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Try again' /></form>"
        return response_cookie, HTML_response

    def checkTruthTablePage(self, form_data, st, ordering, question_type):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], str) -> tuple[str|None, str]
        cookie_text = None
        if form_data is None:
            return None, "No form data received."
        simple = list(st.reportSimpleStatements())
        statements = list(st.reportAllSubstatements())
        statements.sort()
        # Reorder the statements according to the provided ordering
        if ordering != []:
            if len(ordering) == len(statements):
                statements = [statements[i] for i in ordering]
            else:
                return None, "<html><body><h2>Error: Ordering length does not match number of statements.</h2></body></html>"
        nrows = 2**len(simple)
        ncols = len(statements)
        n, m = nrows, ncols
        # Reconstruct the DataFrame from form data
        df = pd.DataFrame(index=range(n), columns=range(m))
        for key, value in form_data.items():
            if key.startswith('field_'):
                _, i, j = key.split('_')
                df.at[int(i), int(j)] = value
        # Evaluate the truth table
        result = evaluateTruthTable(df, st, statements)
        correct = result[0]
        tt_ordering = result[1]
        HTML_response = ""
        if result:
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_ordering, 0)
            HTML_response = "<html><body><h2>Correct!</h2></body></html>"
            if question_type == 'Statement':
                # Add a button to "Try another question" that links to /truth_table_question
                HTML_response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try another question' /></form>"
            else:
                # Add a button to "Continue" that links to the main page
                HTML_response += "<form method='GET' action='/'><input type='submit' value='Continue' /></form>"
        else:
            HTML_response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that links to /truth_table_question
            HTML_response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try again' /></form>"

        return cookie_text, HTML_response
    def checkIdentifyColumnsPage(self, form_data, st, ordering, tt_row_ordering):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[str|None, str]
        cookie_text = None
        if form_data is None:
            return None, "No form data received."
        simple = list(st.reportSimpleStatements())
        statements = list(st.reportAllSubstatements())
        statements.sort()
        # Reorder the statements according to the provided ordering
        if ordering != []:
            if len(ordering) == len(statements):
                statements = [statements[i] for i in ordering]
            else:
                return None, "<html><body><h2>Error: Ordering length does not match number of statements.</h2></body></html>"
        # Check if the marked columns correspond to the two sub-statements of the equivalence
        if not isinstance(st, equivalence.Equivalence):
            return None, "<html><body><h2>Error: Current statement is not an equivalence.</h2></body></html>"
        left, right = st.statement1, st.statement2
        left_index = statements.index(left)
        right_index = statements.index(right)
        selected = [False] * len(statements)
        for key in form_data.keys():
            if key.startswith('col_'):
                _, j = key.split('_')
                try:
                    idx = int(j)
                    if 0 <= idx < len(selected):
                        selected[idx] = True
                except ValueError:
                    continue
        print("Selected columns:", selected)
        answer_key = [False] * len(statements)
        answer_key[left_index] = True
        answer_key[right_index] = True
        print("Answer key:", answer_key)
        correct = (selected == answer_key)
        HTML_response = ""
        if correct:
            # Update the cookie to mark the next step as to be answered
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 1)
            HTML_response = "<html><body><h2>Correct!</h2></body></html>"
            # Add a button to "Continue" that links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Continue' /></form>"
        else:
            HTML_response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that also links to the main page
            HTML_response += "<form method='GET' action='/'><input type='submit' value='Try again' /></form>"
        return cookie_text, HTML_response

    def checkEquivalencePage(self, form_data, st, ordering, tt_row_ordering):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[str|None, str]
        cookie_text = None
        if form_data is None:
            return None, "No form data received."
        if 'equiv' not in form_data:
            return None, "<html><body><h2>Error: No answer selected.</h2></body></html>"
        answer = form_data['equiv']
        if answer not in ['yes', 'no']:
            return None, "<html><body><h2>Error: Invalid answer selected.</h2></body></html>"
        if not isinstance(st, equivalence.Equivalence):
            return None, "<html><body><h2>Error: Current statement is not an equivalence.</h2></body></html>"
        answer_bool = (answer == 'yes')
        # Determine if the two statements are actually equivalent
        answer = st.checkEquivalence()
        correct = (answer == answer_bool)
        HTML_response = ""
        if correct:
            # Update the cookie to mark the question as completed
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 2)
            HTML_response = "<html><body><h2>Correct!</h2></body></html>"
            # Add a button to "Try another question" that links to /truth_table_question
            HTML_response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try another question' /></form>"
        else:
            HTML_response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that links to /truth_table_question
            HTML_response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try again' /></form>"
        return cookie_text, HTML_response

    def bake_cookie(self, st, split, nIDed, ordering, tt_row_ordering, subsequent_step):
        #type: (statementInterface.LogicalStatementInterface, bool, int, list[int], list[int], int) -> str
        cookie_question = cookieEncode(st.prettyPrint())
        cookie_split = 'True' if split else 'False'
        if ordering == [] or ordering is None:
            cookie_ordering = '[]'
        else:
            cookie_ordering = '[' + ':'.join([str(i) for i in ordering]) + ']'
        if tt_row_ordering == [] or tt_row_ordering is None:
            cookie_tt_row_ordering = '[]'
        else:
            cookie_tt_row_ordering = '[' + ':'.join([str(i) for i in tt_row_ordering]) + ']'
        response_cookie = f"current_question={cookie_question}&{cookie_split}&{nIDed}&{cookie_ordering}&{cookie_tt_row_ordering}&{subsequent_step}; Path=/"
        return response_cookie

    # returns the current question Statement object from the cookie, or None if not found
    def get_current_question_from_cookie(self, headers): 
        #type: (str) -> tuple[statementInterface.LogicalStatementInterface|None, statementInterface.LogicalStatementInterface|None, bool, int, list[int], list[int], int]
        cookie_header = headers.get('Cookie')
        question = None
        split = False
        nIDed = 0
        ordering = []
        tt_row_ordering = []
        subsequent_step = 0
        default_value = (None, None, False, 0, [], [], 0)
        if not cookie_header:
            return default_value
        cookies = cookie_header.split(';')
        for cookie in cookies:
            if 'current_question=' in cookie:
                question = cookie.split('=')[1].strip()
                break
        if question is None:
            return default_value
        # Split the cookie into its components
        try:
            question, split, nIDed, ordering, tt_row_ordering, subsequent_step = question.split('&')
        except:
            # Malformed cookie
            return default_value
        # Decode the question
        question = cookieDecode(question)
        split = (split == 'True')
        try:
            nIDed = int(nIDed)
            subsequent_step = int(subsequent_step)
        except:
            # Malformed cookie
            return default_value
        ordering = decode_ordering(ordering)
        tt_row_ordering = decode_ordering(tt_row_ordering)
        if ordering is None or tt_row_ordering is None:
            # Malformed cookie
            return default_value
        #Parse the question into a Statement object
        try:
            st = statementSorter.parse(question)
        except Exception as e:
            # Exception handling
            return default_value
        st_DAG = st.rectifyGraph()
        return st, st_DAG, split, nIDed, ordering, tt_row_ordering, subsequent_step

    def get_form_data(self):
        #type: () -> dict[str, str]
        # Retrieve form data from query string
        post_data = self.path.split('?', 1)[1] if '?' in self.path else None
        if post_data is None:
            return None
        form_data = {}
        for pair in post_data.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
            else:
                key, value = pair, ''
            form_data[key] = value
        return form_data

    def interfaceOrder(self, substatements, ownership):
        #type: (list[statementInterface.LogicalStatementInterface], list[statementInterface.LogicalStatementInterface|None]) -> dict[int, statementInterface.LogicalStatementInterface]
        # Order the list of substatements by where they first appear in the main statement
        sub_indices = {}
        for sub in substatements:
            first_index = None
            for i in range(len(ownership)):
                if ownership[i] == sub:
                    sub_indices[i] = sub
                    break
        #Due to some statements being longer than one character, some indices may be missing, so we need to re-enumerate the values so that no indices are skipped
        # Enumerate them in sorted order of their original indices
        enumerated_indices = enumerate(sorted(sub_indices.keys()))
        # Invert the dictionary to map substatement string index to normalized index
        inverted_dict = {value: key for key, value in enumerated_indices}
        # Use the inverted dictionary to create a new dictionary with normalized indices as values
        sub_indices = {inverted_dict[i]: sub for i, sub in sub_indices.items()}
        return sub_indices


def evaluateTruthTable(df, statement, statements):
    #type: (pd.DataFrame, statementInterface.LogicalStatementInterface, list[statementInterface.LogicalStatementInterface]) -> tuple[bool, list[int]|None]
    # Convert 'T'/'F'/'' to True/False/None
    bool_df = df.replace({'T': True, 'F': False, '': None})
    # Rename columns to statement strings
    bool_df.columns = [s.prettyPrint() for s in statements]
    print(f"Evaluating DataFrame:\n{bool_df}")
    # Calculate the correct truth table
    answerkey = sh.calculateTruthTable(statement)
    print(f"Answer key:\n{answerkey}")
    # Compare the two DataFrames
    comparison_result = sh.dataframesEquivalent(answerkey, bool_df)
    print(f"Comparison result: {comparison_result}")
    return comparison_result

def cookieEncode(s):
    #type: (str) -> str
    # Encode the string to ASCII, replacing non-ASCII characters with escape sequences
    return s.encode('ascii', 'backslashreplace').decode('ascii')

def cookieDecode(question):
    #type: (str) -> str
    # Decode the cookie-encoded string back to its original form
    return question.encode('ascii').decode('unicode_escape')

def decode_ordering(ordering):
    #type: (str) -> list[int]|None
    if ordering == '[]':
        return []
    try:
        ordering = ordering[1:-1]  # Remove the surrounding brackets
        ordering = ordering.split(':')
        ordering = [int(o) for o in ordering]
    except:
        # Malformed cookie
        return None
    return ordering


def recreateTruthTable(st, ordering, tt_row_ordering):
    #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> pd.DataFrame
    statements = list(st.reportAllSubstatements())
    statements.sort()
    # Reorder the statements according to the provided ordering
    if ordering != []:
        if len(ordering) == len(statements):
            statements = [statements[i] for i in ordering]
        else:
            return None
    # Calculate the truth table
    df = sh.calculateTruthTable(st)
    # Adjust the columns to match the order of statements
    df = df[[s.prettyPrint() for s in statements]]
    # Reorder the rows according to the provided tt_row_ordering
    if tt_row_ordering != []:
        if len(tt_row_ordering) == len(df):
            df = df.iloc[tt_row_ordering].reset_index(drop=True)
        else:
            return None
    return df

def printTruthTableToTD(df):
    #type: (pd.DataFrame) -> str
    # Convert the DataFrame to data suitable to be included in an HTML table with 'T'/'F' strings
    n, m = df.shape
    HTML_out = ""
    # Output the column names as the first row
    HTML_out = HTML_out + "<tr>"
    for col in df.columns:
        HTML_out = HTML_out + f"<th>{col}</th>"
    HTML_out = HTML_out + "</tr>"
    # Output each row of the DataFrame
    print("DataFrame to print:\n", df)
    for i in range(n):
        HTML_out = HTML_out + "<tr>"
        for j in range(m):
            val = df.iat[i, j]
            if val == True:
                val_str = 'T'
            elif val == False:
                val_str = 'F'
            else:
                val_str = ''
            HTML_out = HTML_out + f"<td>{val_str}</td>"
        HTML_out = HTML_out + "</tr>"
    return HTML_out

httpd = HTTPServer(('', 8000), SimpleHTTPRequestHandler)
httpd.serve_forever()

