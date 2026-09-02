import questionGenerator
import pandas as pd
import statementSorter
import statementInterface
import equivalence
import argument
import statementHelpers as sh
import cryptography.fernet as f
import base64
import hashlib
import logger
import urllib.parse
import settings

#hwkNumList = ["2", "3", "4", "5"]  # Add to this for each homework assignment to prevent reuse of old completion codes
#numToDoList = [6, 2, 0, 4]  # Number of questions to complete for each homework assignment
class HomeworkSet:
    def __init__(self, number, toDo, generator):
        self.number = number
        self.toDo = toDo
        self.generator = generator

HOMEWORK_SETS = [
    HomeworkSet("1b", questionGenerator.TruthTableQuestions_COMPLETION_COUNT, questionGenerator.TruthTableQuestions),
    HomeworkSet("2", questionGenerator.EquivalenceQuestions_COMPLETION_COUNT, questionGenerator.EquivalenceQuestions),
    HomeworkSet("3", 2, questionGenerator.HomeworkTwo),
    HomeworkSet("4", 0, questionGenerator.HomeworkOneandTwoReview),
    HomeworkSet("5", 4, questionGenerator.HomeworkThree)
]

QUESTION_COOKIE_MAX_AGE = 60 * 60 * 24 * 182  # ~6 months, the rough duration of a college semester

ACTIVE_HOMEWORK_COOKIE_NAME = "activeHomework"

def homeworkSetByNumber(number):
    #type: (str) -> HomeworkSet|None
    for hwk in HOMEWORK_SETS:
        if hwk.number == number:
            return hwk
    return None

# The homework set selected by config.txt (ignoring any per-student override cookie).
def configuredHomework():
    #type: () -> HomeworkSet
    hwkset = settings.activeHomeworkID()
    if hwkset is not None:
        for hwk in HOMEWORK_SETS:
            if hwk.number == hwkset:
                return hwk
    return HOMEWORK_SETS[0]  # Default to the first homework set if not specified or not found

# The activeHomework cookie's homework, if set and valid, else configuredHomework().
def activeHomework(headers):
    #type: (dict) -> HomeworkSet
    cookie_value = retrieve_active_homework_cookie(headers)
    if cookie_value is not None:
        for hwk in HOMEWORK_SETS:
            if hwk.number == cookie_value:
                return hwk
    return configuredHomework()

def retrieve_active_homework_cookie(headers):
    #type: (dict) -> str|None
    cookie_header = headers.get('Cookie')
    if not cookie_header:
        return None
    for cookie in cookie_header.split(';'):
        if f'{ACTIVE_HOMEWORK_COOKIE_NAME}=' in cookie:
            return cookie.split('=', 1)[1].strip()
    return None

# Seconds remaining until the next midnight (server local time).
def secondsUntilMidnight():
    #type: () -> int
    now = pd.Timestamp.now()
    midnight = (now + pd.Timedelta(days=1)).normalize()
    return int((midnight - now).total_seconds())

def bake_active_homework_cookie(hwk_number):
    #type: (str) -> str
    return f"{ACTIVE_HOMEWORK_COOKIE_NAME}={hwk_number}; Max-Age={secondsUntilMidnight()}; Path=/"

# Homeworks a student may switch to: the configured one and everything before it.
def eligibleHomeworkSets():
    #type: () -> list[HomeworkSet]
    ceiling_index = HOMEWORK_SETS.index(configuredHomework())
    return HOMEWORK_SETS[:ceiling_index + 1]

# Bakes a fresh activeHomework cookie if the student doesn't have one yet, else None.
def determine_active_homework(headers):
    #type: (dict) -> str|None
    if retrieve_active_homework_cookie(headers) is not None:
        return None
    return bake_active_homework_cookie(activeHomework(headers).number)

class QuestionManager:
    # Single place that assembles a full HTML document. Every response method builds an inner
    # body_html fragment and passes it here, so the doctype/head/body skeleton exists only once.
    def _renderPage(self, title, body_html):
        #type: (str, str) -> str
        return (
            f"<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>{title}</title></head>"
            f"<body>{body_html}</body></html>"
        )

    # Shared "Correct!" / "Incorrect. Try again." result page used by every check*Page method.
    def _renderResult(self, correct, title=None, heading=None, button_label=None):
        #type: (bool, str|None, str|None, str|None) -> str
        if correct:
            title = title or "Correct"
            heading = heading or "Correct!"
            button_label = button_label or "Continue"
        else:
            title = title or "Incorrect"
            heading = heading or "Incorrect. Try again."
            button_label = button_label or "Try again"
        body = f"<h1>{heading}</h1>"
        body += f"<form method='GET' action='/app'><input type='submit' value='{button_label}' aria-label='{button_label}' /></form>"
        return self._renderPage(title, body)

    # Shared error page. Always offers a way back to the app instead of leaving the student stuck.
    def _renderError(self, msg):
        #type: (str) -> str
        body = f"<h1>Error: {msg}</h1>"
        body += "<form method='GET' action='/app'><input type='submit' value='Return to app' aria-label='Return to app' /></form>"
        return self._renderPage("Error", body)

    def newQuestionPage(self, origin_ip, headers_adapter, completion_codes = [], completion_string=None, completion_codes_hwk=None):
        #type: (str, dict, list[str], str, HomeworkSet|None) -> tuple[list[str|None], str]
        st = self.getNewQuestion(completion_codes, headers_adapter)
        activehwk = activeHomework(headers_adapter)
        # Create a unique fingerprint for the question instance to allow detection of cookie tampering
        #  Note: We're not going to try to obscure what information is preserved in the cookie, nor totally prevent tampering,
        #  as it's all in good fun. But we do want to be able to detect if problems are substituted, or if two students submit the same completion token.
        # Finger print will be time the question was generated, the IP address of the requester, and the text of the statement, encrypted with a symmetric key
        time = str(pd.Timestamp.now().value) # Get current time as integer nanoseconds since epoch, convert to string
        fingerprint = f"{origin_ip}[]{time}[]{st.prettyPrint()}[]{activehwk.number}[]Started"
        # Retrieve encryption key from file
        fernet = self.get_key()
        encrypted_fingerprint = fernet.encrypt(fingerprint.encode())
        fingerprint_hex = encrypted_fingerprint.hex()

        response_cookie = self.bake_cookie(st, False, 0, [], [], 0, fingerprint_hex)
        # Announce new question to student in body
        response_body = f"<h1>New Question</h1><h2>New question generated: {st.prettyPrint()}</h2>"
        # Add a "start working" button that will begin the first step
        response_body += (
            "<form method='GET' action='/app'>"
            "<input type='submit' value='Start working on it' aria-label='Start working on it'/>"
            "</form>"
        )
        response_body += self.standardButtons()
        if completion_string is not None:
            response_body += f"<p>{completion_string}</p>"
        if completion_codes != []:
            # completion_codes may belong to a homework other than the currently active one.
            codes_hwk = completion_codes_hwk if completion_codes_hwk is not None else activehwk
            response_body += f"<p>Your completion codes (submit a set of {codes_hwk.toDo} on Brightspace to complete homework {codes_hwk.number} part B):</p><br>"
            num = 1
            for code in completion_codes:
                response_body += f"{num}: {formatCode(code)}<br>"
                num += 1
            response_body += "<br>"
        return [response_cookie], self._renderPage("New Question", response_body)

    # Checks the provided fingerprint against the current question.
    #  Will approve or deny completion based on whether the fingerprint matches the current question,
    #  and adds the fingerprint to the list of completion codes if approved, and that question isn't already in the list.
    #  Returns a completion string suitable for display to the user.
    # It is not possible to ensure that a student can't complete another student's question,
    #  simply due to the nature of remote work, so the IP address is not checked.
    # The combination of IP address and nanosecond-precision timestamp should be sufficient to ensure that all fingerprints are unique.
    # Note that this DOES NOT check that the student completed all steps of the question, rather than manipulating the cookie to skip to the end.
    #  There are computer security students in the class, they can have their fun.
    def checkFingerprint(self, st, fingerprint_hex, fingerprint_list):
        parts = self.decrypt_fingerprint(fingerprint_hex)
        if parts is None:
            return "Error: Invalid completion code."
        ip, time, statement, hwk, status = parts
        if not any(h.number == hwk for h in HOMEWORK_SETS):
            return "Error: Invalid completion code homework number."
        # Check if the fingerprint matches the current question
        # Checking the assigned problem text vs. the current problem text detects attempts to sub in one's own (easier) problem
        if statement == st.prettyPrint():
            for code in fingerprint_list:
                old_question = self.decode_fingerprint(code)
                if old_question is not None and old_question == statement:
                    return "This question has already been completed."
            # Approved, calculate completion code and add to list
            # Credit hwk (the question's own homework), not whatever's active now.
            completion_code = self.generate_completion_code(ip, time, statement, hwk)
            fingerprint_list.append(completion_code)
            return "Completion code accepted."
        return "Error: Invalid completion code."
    # Generate a completion code from the fingerprint parts
    def generate_completion_code(self, ip, time, statement, hwk):
        fernet = self.get_key()
        fingerprint = f"{ip}[]{time}[]{statement}[]{hwk}[]Completed"
        fingerprint_bytes = fingerprint.encode()
        encrypted_fingerprint = fernet.encrypt(fingerprint_bytes)
        return encrypted_fingerprint.hex()

    # Decrypts into (ip, time, statement, hwk, status), or None if malformed/tampered. No homework validation.
    def decrypt_fingerprint(self, fingerprint_hex):
        #type: (str) -> tuple[str,str,str,str,str]|None
        fernet = self.get_key()
        try:
            fingerprint_bytes = bytes.fromhex(fingerprint_hex)
            decrypted_fingerprint = fernet.decrypt(fingerprint_bytes).decode()
        except Exception as e:
            logger.logger.error("Error decrypting fingerprint: %s", e)
            return None
        parts = decrypted_fingerprint.split("[]")
        if len(parts) != 5:
            return None
        return tuple(parts)

    # Decode a fingerprint hex string to statement text (for checking duplicates)
    def decode_fingerprint(self, fingerprint_hex):
        parts = self.decrypt_fingerprint(fingerprint_hex)
        if parts is None:
            return None
        ip, time, statement, hwk, status = parts
        if not any(h.number == hwk for h in HOMEWORK_SETS):
            return None
        return statement
    # Retrieve the encryption key
    #  Currently stored in a file.
    #  Next version should use a secure method of key management.
    def get_key(self):
        #type: () -> bytes
        # Test: return a fixed key instead of the stored one
        keyefile = open("key.txt","r")
        keystr = keyefile.read()
        keyefile.close()
        key = base64.urlsafe_b64encode(hashlib.sha256(keystr.encode()).digest())
        return f.Fernet(key)

    def getNewQuestion(self, completion_codes, headers_adapter):
        #type: (list[str], dict) -> statementInterface.LogicalStatementInterface
        # compile list of previous questions
        previous_questions = set()
        activehwk = activeHomework(headers_adapter)
        for code in completion_codes:
            question = self.decode_fingerprint(code)
            if question is not None:
                previous_questions.add(question)
        question = activehwk.generator(list(previous_questions))
        st = statementSorter.parse(question)
        st = st.rectifyGraph()
        return st

    def splitStatementPage(self, st):
        #type: (statementInterface.LogicalStatementInterface) -> tuple[list[str|None], str]
        questionData = st.printStringAndOwnership()
        questionStr = questionData[0]
        # Ask the student to identify all logical operators in the statement
        HTML_out = f"<h1>Split Statement</h1>"
        HTML_out = HTML_out + f"<h2>Identify the logical operators in the statement: </h2>"
        # Each character's checkbox/label pair is its own flex column of independent toggles.
        HTML_out = HTML_out + "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='split_check' />"
        HTML_out = HTML_out + "<div style='display:flex;'>"
        for i in range(len(questionStr)):
            HTML_out = HTML_out + (
                "<div style='display:flex; flex-direction:column; align-items:center;'>"
                f"<input type='checkbox' name='op_{i}' aria-label='{questionStr[i]}' />"
                f"<span>{questionStr[i]}</span>"
                "</div>"
            )
        HTML_out = HTML_out + "</div>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' aria-label='Submit' formaction='/app' />"
        HTML_out = HTML_out + "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage(f"Split Statement for {questionStr}", HTML_out)

    #Asks the current "Identify all symbols in the current substatemtent question"
    #Assumes that all operators that occur in the statement before nIDed have been identified,
    # so it displays them.
    def identifySubstatementsPage(self, st, nIDed):
        #type: (statementInterface.LogicalStatementInterface, int) -> tuple[list[str|None], str]
        questionData = st.printStringAndOwnership()
        questionStr = questionData[0]
        operators = questionData[2]
        # Figure out which operator we are currently asking about
        operator_indices = [i for i, is_op in enumerate(operators) if is_op]
        if nIDed >= len(operator_indices):
            # Should be impossible, we don't route here if nIDed is >= number of operators
            return [None], self._renderError("No more operators to identify.")
        current_op_index = operator_indices[nIDed]
        # Each character gets a flex column (arrow/char/checkbox). No header row needed - each
        # column's checkbox or span already has an aria-label.
        HTML_out = f"<h1>Identify Substatements</h1><h2>Which symbols belong to the substatement(s) of the indicated operator?</h2>"
        HTML_out = HTML_out + "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='identify_substatements_check' />"
        HTML_out = HTML_out + "<div style='display:flex;'>"
        for i in range(len(questionStr)):
            # An empty <span> collapses to zero height as a flex item, so use &nbsp; as a
            # placeholder to keep columns aligned.
            arrow = "↓" if i == current_op_index else "&nbsp;"
            if i == current_op_index:
                checkbox = "<input type='checkbox' disabled aria-hidden='true' style='visibility:hidden;' />"
                # Checkbox is disabled, so the accessible name goes on this span instead:
                # role='img' makes aria-label authoritative (a bare <span> may not get one), and
                # tabindex='0' keeps it in the tab order since disabled inputs drop out of it.
                char_span = f"<span role='img' tabindex='0' aria-current='true' aria-label='{questionStr[i]}, the operator you are identifying'>{questionStr[i]}</span>"
            else:
                checkbox = f"<input type='checkbox' name='sub_{i}' aria-label='{questionStr[i]}' />"
                char_span = f"<span>{questionStr[i]}</span>"
            HTML_out = HTML_out + (
                "<div style='display:flex; flex-direction:column; align-items:center;'>"
                f"<span>{arrow}</span>"
                f"{char_span}"
                f"{checkbox}"
                "</div>"
            )
        HTML_out = HTML_out + "</div>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' aria-label='Submit' />"
        HTML_out = HTML_out + "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Which symbols belong to the substatement(s) of the indicated operator?", HTML_out)

    def orderSubstatementsPage(self, st):
        #type: (statementInterface.LogicalStatementInterface) -> tuple[list[str|None], str]
        substatements = list(st.reportAllSubstatements())
        ownership = st.printStringAndOwnership()[1]
        n_substatements = len(substatements)
        # Ask the students to pick a valid ordering of the substatements for their truth table
        HTML_out = f"<h1>Order Substatements</h1><h2>Decide what order you'd like to evaluate the statements in:</h2>"

        sub_indices = self.interfaceOrder(substatements, ownership)

        # Print a two-column n-row table, where the first column contains the substatement,
        # and the second column contains a dropdown to select its order (1 to n_substatements)
        HTML_out = HTML_out + "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='order_check' />"
        HTML_out = HTML_out + "<table border='1'><tr><th>Substatement</th><th>Order</th></tr>"
        for index in sorted(sub_indices.keys()):
            sub = sub_indices[index]
            HTML_out = HTML_out + f"<tr><td>{sub.prettyPrint()}</td><td><select name='order_{index}' aria-label='Order for {sub.prettyPrint()}'>"
            for order in range(1, n_substatements + 1):
                HTML_out = HTML_out + f"<option value='{order}'>{order}</option>"
            HTML_out = HTML_out + "</select></td></tr>"
        HTML_out = HTML_out + "</table>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out = HTML_out + "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Order Substatements", HTML_out)

    def truthTablePage(self, st, ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int]) -> tuple[list[str|None], str]
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
                return [None], self._renderError("Ordering length does not match number of statements.")
        # Print out a truth table with dropdowns for each cell
        HTML_out = f"<h1>Truth Table</h1><h2>Fill in the Truth Table for {question}</h2>"
        HTML_out = HTML_out + f"<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='truth_table_check' />"
        # Print the statement headers
        HTML_out = HTML_out + "<table border='1'><tr>"
        for j in range(m):
            HTML_out = HTML_out + f"<th>{statements[j].prettyPrint()}</th>"
        HTML_out = HTML_out + "</tr>"
        for i in range(n):
            HTML_out = HTML_out + "<tr>"
            for j in range(m):
                HTML_out = HTML_out + (
                    f"<td><select name='field_{i}_{j}' aria-label='Truth value for row {i+1}, column {statements[j].prettyPrint()}'>"
                    "<option value='' selected></option>"
                    "<option value='T'>T</option>"
                    "<option value='F'>F</option>"
                    "</select></td>"
                )
            HTML_out = HTML_out + "</tr>"
        HTML_out = HTML_out + "</table>"
        HTML_out = HTML_out + "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out += "</form>"
        HTML_out += self.standardButtons()

        #return: No cookie, HTML body
        return [None], self._renderPage("Truth Table", HTML_out)
    def identifyColumnsPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[list[str|None], str]
        question = st.prettyPrint()
        statements = list(st.reportAllSubstatements())
        ncols = len(statements)
        m = ncols
        statements.sort()
        # Use the helper to recreate the truth table
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return [None], self._renderError("Could not recreate truth table.")
        # Print out the truth table with the correct answers filled in, and checkboxes below each column
        HTML_out = f"<h1>Identify Columns</h1><h2>Identify the columns that are needed to answer the question: {question}</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='identify_columns_check' />"
        #Begin the table
        HTML_out += "<table border='1'>"
        # Print the truth table
        HTML_out += printTruthTableToTD(df)
        # Print checkboxes below each column
        HTML_out += "<tr>"
        for j in range(m):
            HTML_out += f"<td><input type='checkbox' name='col_{j}' aria-label='{df.columns[j]}' /></td>"
        HTML_out += "</tr>"
        HTML_out += "</table>"
        HTML_out += "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out += "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Identify Columns", HTML_out)

    def equivalentQuestionPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[list[str|None], str]
        # Recreate the truth table
        if not isinstance(st, equivalence.Equivalence):
            return [None], self._renderError("Not an equivalence question.")
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return [None], self._renderError("Could not recreate truth table.")
        question = st.prettyPrint()
        # Ask the student if the two statements are equivalent, printing the truth table with up-arrows under the columns that are needed to answer the question
        HTML_out = f"<h1>Are the two statements equivalent?</h1><h2>{question}</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='equivalence_check' />"
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
        HTML_out += "<input type='radio' id='yes' name='equiv' value='yes' aria-label='Yes'>"
        HTML_out += "<label for='yes'>Yes</label><br>"
        HTML_out += "<input type='radio' id='no' name='equiv' value='no' aria-label='No'>"
        HTML_out += "<label for='no'>No</label><br>"
        HTML_out += "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out += "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Are the two statements equivalent?", HTML_out)

    def identifyArgumentPremiseColumnsPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[list[str|None], str]
        # Recreate the truth table
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Not an argument question.")
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return [None], self._renderError("Could not recreate truth table.")
        question = st.prettyPrint()
        # Ask the student which columns are needed to determine if the argument is valid, printing the truth table with a row of checkboxes below
        HTML_out = f"<h1>Identify Premise Columns</h1><h2>Which columns contain the premises of the argument? {question}</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='identify_argument_columns_check' />"
        #Begin the table
        HTML_out += "<table border='1'>"
        # Print the truth table
        HTML_out += printTruthTableToTD(df)
        # Print checkboxes below each column
        HTML_out += "<tr>"
        for j in range(len(df.columns)):
            HTML_out += f"<td><input type='checkbox' name='col_{j}' aria-label='{df.columns[j]}' /></td>"
        HTML_out += "</tr>"
        HTML_out += "</table>"
        HTML_out += "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out += "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Identify Premise Columns", HTML_out)

    def identifyArgumentRowsPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[list[str|None], str]
        # Recreate the truth table
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Not an argument question.")
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return [None], self._renderError("Could not recreate truth table.")
        question = st.prettyPrint()
        # Ask the student which rows are needed to determine if the argument is valid, printing the truth table with a column of checkboxes to the left
        HTML_out = f"<h1>Identify Premise Rows</h1><h2>Which rows are needed to determine if the argument is valid? {question}</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='identify_argument_rows_check' />"
        #Begin the table
        HTML_out += "<table border='1'>"
        # Print the truth table with a column of checkboxes to the left
        HTML_out += "<tr><th></th>"
        for col in df.columns:
            HTML_out += f"<th>{col}</th>"
        HTML_out += "</tr>"
        # Only premise columns (arrow-marked below) matter here; hide the rest from screen readers.
        column_list = [p.prettyPrint() for p in st.premises]
        for i in range(len(df)):
            HTML_out += "<tr>"
            HTML_out += f"<td><input type='checkbox' name='row_{i}' aria-label='Row {i}' /></td>"
            for col in df.columns:
                val = df.iloc[i][col]
                cell_text = 'T' if val else 'F'
                if col in column_list:
                    HTML_out += f"<td>{cell_text}</td>"
                else:
                    HTML_out += f"<td aria-hidden='true'>{cell_text}</td>"
            HTML_out += "</tr>"
        # Print up arrows under the columns that contain the premises
        HTML_out += "<tr><td></td>"
        for col in df.columns:
            if col in column_list:
                HTML_out += "<td>↑</td>"
            else:
                HTML_out += "<td></td>"
        HTML_out += "</table>"
        HTML_out += "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out += "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Identify Premise Rows", HTML_out)

    def identifyArgumentConclusionColumnPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[list[str|None], str]
        # Recreate the truth table
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Not an argument question.")
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return [None], self._renderError("Could not recreate truth table.")
        question = st.prettyPrint()
        # Ask the student which columns are needed to determine if the argument is valid, printing the truth table with a row of checkboxes below
        HTML_out = f"<h1>Identify Conclusion Column</h1><h2>Which column contains the conclusion of the argument? {question}</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='identify_argument_conclusion_check' />"
        #Begin the table
        HTML_out += "<table border='1'>"
        # Print the truth table
        HTML_out += printTruthTableToTD(df)
        # Print checkboxes below each column
        HTML_out += "<tr>"
        for j in range(len(df.columns)):
            HTML_out += f"<td><input type='checkbox' name='col_{j}' aria-label='{df.columns[j]}' /></td>"
        HTML_out += "</tr>"
        HTML_out += "</table>"
        HTML_out += "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out += "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Identify Conclusion Column", HTML_out)

    def argumentQuestionPage(self, st, ordering, tt_row_ordering):
        #type: (statementInterface.LogicalStatementInterface, list[int], list[int]) -> tuple[list[str|None], str]
        # Recreate the truth table
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Not an argument question.")
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return [None], self._renderError("Could not recreate truth table.")
        question = st.prettyPrint()
        # Ask the student if the argument is valid, printing the truth table with up-arrows under the premise columns
        #  and right-arrows to the left of the rows needed
        HTML_out = f"<h1>Is the argument valid?</h1><h2>{question}</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out = HTML_out + "<input type='hidden' name='form_name' value='argument_validity_check' />"
        #Begin the table
        HTML_out += "<table border='1'>"
        # Print the truth table with a column of right-arrows to the left of any row where all the premises are true
        HTML_out += "<tr><th></th>"
        for col in df.columns:
            HTML_out += f"<th>{col}</th>"
        HTML_out += "</tr>"
        premise_columns = [p.prettyPrint() for p in st.premises]
        conclusion_col = st.conclusion.prettyPrint()
        # At this step, only the conclusion's value on premise-true rows matters; hide the arrow
        # and every other column/value from screen readers as irrelevant.
        for i in range(len(df)):
            HTML_out += "<tr>"
            all_true = True
            for pcol in premise_columns:
                if df.iloc[i][pcol] != True:
                    all_true = False
                    break
            arrow = "→" if all_true else ""
            HTML_out += f"<td aria-hidden='true'>{arrow}</td>"
            for col in df.columns:
                val = df.iloc[i][col]
                cell_text = 'T' if val else 'F'
                if col == conclusion_col and all_true:
                    HTML_out += f"<td aria-label='{cell_text}, premise row'>{cell_text}</td>"
                else:
                    HTML_out += f"<td aria-hidden='true'>{cell_text}</td>"
            HTML_out += "</tr>"
        # Print up arrows under the column that contains the conclusion
        HTML_out += "<tr><td></td>"
        for col in df.columns:
            if col == conclusion_col:
                HTML_out += "<td>↑</td>"
            else:
                HTML_out += "<td></td>"
        HTML_out += "</table>"
        # Add radio buttons for Yes/No
        HTML_out += "<p>Is the argument valid?</p>"
        HTML_out += "<input type='radio' id='yes' name='valid' value='yes' aria-label='Yes'>"
        HTML_out += "<label for='yes'>Yes</label><br>"
        HTML_out += "<input type='radio' id='no' name='valid' value='no' aria-label='No'>"
        HTML_out += "<label for='no'>No</label><br>"
        HTML_out += "<input type='submit' value='Submit' formaction='/app' aria-label='Submit' />"
        HTML_out += "</form>"
        HTML_out += self.standardButtons()
        #return: No cookie, HTML body
        return [None], self._renderPage("Is the argument valid?", HTML_out)

    def completeQuestionPage(self, origin_ip, st, fingerprint, headers_adapter):
        #type: (str, statementInterface.LogicalStatementInterface, str, dict) -> tuple[list[str|None], str]
        # Credit the homework embedded in the fingerprint, not whatever's active now. Falls back
        # to active homework if unreadable/unrecognized; checkFingerprint rejects those anyway.
        parts = self.decrypt_fingerprint(fingerprint)
        completed_hwk = (homeworkSetByNumber(parts[3]) if parts is not None else None) or activeHomework(headers_adapter)
        hwk_number = completed_hwk.number
        # Retrieve the list of previously-completed fingerprints from the cookie
        fingerprint_list = self.retrieve_fingerprint_cookie(headers_adapter, hwk_number)
        completion_string = self.checkFingerprint(st, fingerprint, fingerprint_list)  # Final check to aprove or deny completion (Note: mutates fingerprint_list)
        # The displayed page is the new question page; its completion codes belong to
        # completed_hwk, not necessarily the active homework.
        response_cookie, response_body = self.newQuestionPage(origin_ip, headers_adapter, fingerprint_list, completion_string, completed_hwk)
        response_cookie.append(self.bake_fingerprint_cookie(fingerprint_list, hwk_number))
        return response_cookie, response_body
    
    #Display all codes from all homeworks completed so far
    def displayAllCompletionCodesPage(self, headers_adapter):
        response_cookie = []
        response_body = "<h1>Your Completion Codes</h1>"
        for hwk in range(len(HOMEWORK_SETS)):
            fingerprint_list = self.retrieve_fingerprint_cookie(headers_adapter, HOMEWORK_SETS[hwk].number)
            # Display the fingerprints for this homework
            if fingerprint_list == []:
                response_body += f"<h2>No completion codes found for homework {HOMEWORK_SETS[hwk].number}.</h2><br>"
                continue
            logger.logger.info("Fingerprints for homework %s: %s", HOMEWORK_SETS[hwk].number, fingerprint_list)
            response_body = response_body + f"<h2>Completion codes for homework {HOMEWORK_SETS[hwk].number} (submit a set of {HOMEWORK_SETS[hwk].toDo} on Brightspace to complete):</h2><br>"
            num = 1
            for code in fingerprint_list:
                response_body += f"{num}: {formatCode(code)}<br>"
                num += 1
            response_body += "<br>"
        #Add a button to return to the main page
        response_body += "<form method='GET' action='/app'><input type='submit' value='Return to current question' aria-label='Return to current question' /></form>"
        return [None], self._renderPage("Your Completion Codes", response_body)

    # Radio buttons to pick a practice homework, restricted to eligibleHomeworkSets().
    def setActiveHomeworkPage(self, headers_adapter):
        #type: (dict) -> tuple[list[str|None], str]
        current = activeHomework(headers_adapter)
        HTML_out = "<h1>Set Active Homework</h1><h2>Choose which homework's questions you'd like to practice:</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out += "<input type='hidden' name='form_name' value='set_active_homework_check' />"
        for hwk in eligibleHomeworkSets():
            checked = " checked" if hwk.number == current.number else ""
            HTML_out += (
                f"<input type='radio' id='hwk_{hwk.number}' name='active_homework' value='{hwk.number}'{checked} />"
                f"<label for='hwk_{hwk.number}'>Homework {hwk.number}</label><br>"
            )
        HTML_out += "<input type='submit' value='Submit' aria-label='Submit' />"
        HTML_out += "</form>"
        # Custom Navigation - standardButtons() would re-offer Set Active Homework here.
        HTML_out += "<h2>Navigation</h2>"
        HTML_out += "<form method='GET' action='/app'><input type='submit' value='Return to current question' aria-label='Return to current question' /></form>"
        return [None], self._renderPage("Set Active Homework", HTML_out)

    def checkSplitStatementPage(self, form_data, st, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, str) -> tuple[list[str|None], str]
        questionData = st.printStringAndOwnership()
        operators = questionData[2]
        response_cookie = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
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
        logger.logger.info("Selected: %s", selected)
        logger.logger.info("Answer key: %s", operators)
        correct = (selected == operators)
        if correct:
            # Update the cookie to mark the statement as split
            cookie_question = cookieEncode(st.prettyPrint())
            response_cookie = self.bake_cookie(st, True, 0, [], [], 0, fingerprint)
        HTML_response = self._renderResult(correct)
        return [response_cookie], HTML_response

    def checkIdentifySubstatementsPage(self, form_data, st, nIDed, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, int, str) -> tuple[list[str|None], str]
        questionData = st.printStringAndOwnership()
        questionStr = questionData[0]
        ownership = questionData[1]
        operators = questionData[2]
        response_cookie = None
        # Figure out which operator we are currently asking about
        operator_indices = [i for i, is_op in enumerate(operators) if is_op]
        if nIDed >= len(operator_indices):
            # Should be impossible, we don't route here if nIDed is >= number of operators
            return [None], self._renderError("No more operators to identify.")
        current_op_index = operator_indices[nIDed]
        if form_data is None:
            return [None], self._renderError("No form data received.")
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
        logger.logger.info("Selected: %s", selected)
        logger.logger.info("Answer key: %s", answer_key)
        for i in range(len(ownership)):
            if ownership[i] is None:
                continue
            if selected[i] != answer_key[i]:
                correct = False
                break
        if correct:
            # Update the cookie to mark the next operator as to be identified
            response_cookie = self.bake_cookie(st, True, nIDed + 1, [], [], 0, fingerprint)
        HTML_response = self._renderResult(correct)
        return [response_cookie], HTML_response

    def checkOrderSubstatementsPage(self, form_data, st, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, str) -> tuple[list[str|None], str]
        # Get all substatements
        substatements = list(st.reportAllSubstatements())
        ownership = st.printStringAndOwnership()[1]
        response_cookie = None
        if form_data is None:
            return [None], self._renderError("No form data received.")

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
        logger.logger.info("Selected ordering: %s", selected_ordering)
        valid = (None not in selected_ordering) and (len(set(selected_ordering)) == len(selected_ordering))
        if valid:
            for i in range(len(selected_ordering)):
                if selected_ordering[i] < 1 or selected_ordering[i] > len(selected_ordering):
                    valid = False
                    break
        if not valid:
            HTML_response = self._renderResult(False, title="Invalid Ordering", heading="Invalid ordering. Try again.")
            return [None], HTML_response
        #Convert the ordering from 1-indexed to 0-indexed
        selected_ordering = [x - 1 for x in selected_ordering]
        logger.logger.info("Normalized selected ordering: %s", selected_ordering)
        sub_indices = self.interfaceOrder(substatements, ownership)
        logger.logger.info("Interface order: %s", sub_indices)
        # Order the list of substatements by where they first appear in the main statement
        ordered_substatements = [sub_indices[i] for i in sorted(sub_indices.keys())]
        logger.logger.info("Current substatements: %s", [s.prettyPrint() for s in ordered_substatements])
        # Reorder the substatements according to the selected ordering
        ordered_substatements = [x for _, x in sorted(zip(selected_ordering, ordered_substatements))]
        logger.logger.info("Reordered substatements: %s", [s.prettyPrint() for s in ordered_substatements])
        # Check if the ordering is logically valid (i.e. no statement appears before its substatements)
        correct = sh.isValidEvaluationOrder(ordered_substatements)
        # The Parser considers the natural order to be the sorted order of the substatements, so we need to adjust for that
        tt_order = list(st.reportAllSubstatements())
        tt_order.sort()
        # What would tt_order need to be reordered by to match selected_ordering?
        # Get the indices of each substatement in tt_order
        tt_indices = [tt_order.index(s) for s in ordered_substatements]
        if correct:
            # Update the cookie with the new ordering
            response_cookie = self.bake_cookie(st, True, len(substatements), tt_indices, [], 0, fingerprint)
        HTML_response = self._renderResult(correct)
        return [response_cookie], HTML_response

    def checkTruthTablePage(self, form_data, st, ordering, question_type, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], str, str) -> tuple[list[str|None], str]
        cookie_text = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
        simple = list(st.reportSimpleStatements())
        statements = list(st.reportAllSubstatements())
        statements.sort()
        # Reorder the statements according to the provided ordering
        if ordering != []:
            if len(ordering) == len(statements):
                statements = [statements[i] for i in ordering]
            else:
                return [None], self._renderError("Ordering length does not match number of statements.")
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
        if correct:
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_ordering, 0, fingerprint)
            button_label = 'Try another question' if question_type == 'Statement' else 'Continue'
            HTML_response = self._renderResult(True, button_label=button_label)
        else:
            HTML_response = self._renderResult(False)

        return [cookie_text], HTML_response
    def checkIdentifyColumnsPage(self, form_data, st, ordering, tt_row_ordering, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int], str) -> tuple[list[str|None], str]
        cookie_text = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
        statements = list(st.reportAllSubstatements())
        statements.sort()
        # Reorder the statements according to the provided ordering
        if ordering != []:
            if len(ordering) == len(statements):
                statements = [statements[i] for i in ordering]
            else:
                return [None], self._renderError("Ordering length does not match number of statements.")
        # Check if the marked columns correspond to the two sub-statements of the equivalence
        if not isinstance(st, equivalence.Equivalence):
            return [None], self._renderError("Current statement is not an equivalence.")
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
        logger.logger.info("Selected columns: %s", selected)
        answer_key = [False] * len(statements)
        answer_key[left_index] = True
        answer_key[right_index] = True
        logger.logger.info("Answer key: %s", answer_key)
        correct = (selected == answer_key)
        if correct:
            # Update the cookie to mark the next step as to be answered
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 1, fingerprint)
        HTML_response = self._renderResult(correct)
        return [cookie_text], HTML_response

    def checkEquivalencePage(self, form_data, st, ordering, tt_row_ordering, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int], str) -> tuple[list[str|None], str]
        cookie_text = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
        if 'equiv' not in form_data:
            return [None], self._renderError("No answer selected.")
        answer = form_data['equiv']
        if answer not in ['yes', 'no']:
            return [None], self._renderError("Invalid answer selected.")
        if not isinstance(st, equivalence.Equivalence):
            return [None], self._renderError("Current statement is not an equivalence.")
        answer_bool = (answer == 'yes')
        # Determine if the two statements are actually equivalent
        answer = st.checkEquivalence()
        correct = (answer == answer_bool)
        if correct:
            # Update the cookie to mark the question as completed
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 2, fingerprint)
            HTML_response = self._renderResult(True, button_label='Try another question')
        else:
            HTML_response = self._renderResult(False)
        return [cookie_text], HTML_response

    def checkIdentifyArgumentPremiseColumnsPage(self, form_data, st, ordering, tt_row_ordering, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int], str) -> tuple[list[str|None], str]
        cookie_text = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
        simple = list(st.reportSimpleStatements())
        statements = list(st.reportAllSubstatements())
        statements.sort()
        # Reorder the statements according to the provided ordering
        if ordering != []:
            if len(ordering) == len(statements):
                statements = [statements[i] for i in ordering]
            else:
                return [None], self._renderError("Ordering length does not match number of statements.")
        # Check if the marked columns correspond to the premises and conclusion of the argument
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Current statement is not an argument.")
        conclusion = st.conclusion
        premises = st.premises
        conclusion_index = statements.index(conclusion)
        premise_indices = [statements.index(p) for p in premises]
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
        logger.logger.info("Selected columns: %s", selected)
        answer_key = [False] * len(statements)
        for pi in premise_indices:
            answer_key[pi] = True
        logger.logger.info("Answer key: %s", answer_key)
        correct = (selected == answer_key)
        if correct:
            # Update the cookie to mark the next step as to be answered
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 1, fingerprint)
        HTML_response = self._renderResult(correct)
        return [cookie_text], HTML_response

    def checkIdentifyArgumentRowsPage(self, form_data, st, ordering, tt_row_ordering, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int], str) -> tuple[list[str|None], str]
        cookie_text = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
        # Re-create the truth table
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Current statement is not an argument.")
        df = recreateTruthTable(st, ordering, tt_row_ordering)
        if df is None:
            return [None], self._renderError("Could not recreate truth table.")
        # Find all rows where all premises are true
        premise_columns = [p.prettyPrint() for p in st.premises]
        relevant_rows = [False] * len(df)
        for i in range(len(df)):
            if all(df.iloc[i][col] for col in premise_columns):
                relevant_rows[i] = True
        # Check which checkboxes were ticked
        selected = [False] * len(df)
        for key in form_data.keys():
            if key.startswith('row_'):
                _, j = key.split('_')
                try:
                    idx = int(j)
                    if 0 <= idx < len(selected):
                        selected[idx] = True
                except ValueError:
                    continue
        logger.logger.info("Selected rows: %s", selected)
        logger.logger.info("Answer key: %s", relevant_rows)
        correct = (selected == relevant_rows)
        if correct:
            # Update the cookie to mark the next step as to be answered
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 2, fingerprint)
        HTML_response = self._renderResult(correct)
        return [cookie_text], HTML_response

    def checkIdentifyArgumentConclusionColumnPage(self, form_data, st, ordering, tt_row_ordering, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int], str) -> tuple[list[str|None], str]
        cookie_text = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
        # Re-create column list
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Current statement is not an argument.")
        statements = list(st.reportAllSubstatements())
        statements.sort()
        # Reorder the statements according to the provided ordering
        if ordering != []:
            if len(ordering) == len(statements):
                statements = [statements[i] for i in ordering]
            else:
                return [None], self._renderError("Ordering length does not match number of statements.")
        conclusion = st.conclusion
        conclusion_index = statements.index(conclusion)
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
        logger.logger.info("Selected columns: %s", selected)
        answer_key = [False] * len(statements)
        answer_key[conclusion_index] = True
        logger.logger.info("Answer key: %s", answer_key)
        correct = (selected == answer_key)
        if correct:
            # Update the cookie to mark the next step as to be answered
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 3, fingerprint)
        HTML_response = self._renderResult(correct)
        return [cookie_text], HTML_response

    def checkArgumentValidityPage(self, form_data, st, ordering, tt_row_ordering, fingerprint):
        #type: (dict, statementInterface.LogicalStatementInterface, list[int], list[int], str) -> tuple[list[str|None], str]
        cookie_text = None
        if form_data is None:
            return [None], self._renderError("No form data received.")
        if 'valid' not in form_data:
            return [None], self._renderError("No answer selected.")
        answer = form_data['valid']
        if answer not in ['yes', 'no']:
            return [None], self._renderError("Invalid answer selected.")
        if not isinstance(st, argument.Argument):
            return [None], self._renderError("Current statement is not an argument.")
        answer_bool = (answer == 'yes')
        # Determine if the argument is actually valid
        answer = st.checkValidity()
        correct = (answer == answer_bool)
        if correct:
            # Update the cookie to mark the question as completed
            cookie_text = self.bake_cookie(st, True, len(list(st.reportAllSubstatements())), ordering, tt_row_ordering, 4, fingerprint)
            HTML_response = self._renderResult(True, button_label='Try another question')
        else:
            HTML_response = self._renderResult(False)
        return [cookie_text], HTML_response

    def checkSetActiveHomeworkPage(self, form_data, headers_adapter):
        #type: (dict, dict) -> tuple[list[str|None], str]
        if form_data is None or 'active_homework' not in form_data:
            return [None], self._renderError("No homework selected.")
        selected = form_data['active_homework']
        eligible_numbers = [hwk.number for hwk in eligibleHomeworkSets()]
        if selected not in eligible_numbers:
            return [None], self._renderError("Invalid homework selected.")
        cookie_text = bake_active_homework_cookie(selected)
        HTML_out = f"<h1>Active homework set to {selected}.</h1>"
        HTML_out += "<form method='GET' action='/app'><input type='submit' value='Continue' aria-label='Continue' /></form>"
        return [cookie_text], self._renderPage("Active Homework Updated", HTML_out)

    def bake_cookie(self, st, split, nIDed, ordering, tt_row_ordering, subsequent_step, fingerprint):
        #type: (statementInterface.LogicalStatementInterface, bool, int, list[int], list[int], int, str) -> str
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
        response_cookie = f"current_question={cookie_question}&{cookie_split}&{nIDed}&{cookie_ordering}&{cookie_tt_row_ordering}&{subsequent_step}&{fingerprint}; Max-Age={QUESTION_COOKIE_MAX_AGE}; Path=/"
        return response_cookie

    # returns the current question Statement object from the cookie, or None if not found
    def get_current_question_from_cookie(self, headers): 
        #type: (str) -> tuple[statementInterface.LogicalStatementInterface|None, statementInterface.LogicalStatementInterface|None, bool, int, list[int], list[int], int, str|None]
        cookie_header = headers.get('Cookie')
        question = None
        split = False
        nIDed = 0
        ordering = []
        tt_row_ordering = []
        subsequent_step = 0
        fingerprint = None
        default_value = (None, None, False, 0, [], [], 0, None)
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
            question, split, nIDed, ordering, tt_row_ordering, subsequent_step, fingerprint = question.split('&')
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
        return st, st_DAG, split, nIDed, ordering, tt_row_ordering, subsequent_step, fingerprint

    def bake_fingerprint_cookie(self, fingerprint_list, hwk_number):
        #type: (list[str], str) -> str
        # Join the fingerprint list into a single string with colons for cookie safety
        fingerprint_str = ":".join(fingerprint_list)
        return f"hmwk{hwk_number}_fingerprints={fingerprint_str}; Path=/"

    def retrieve_fingerprint_cookie(self, headers, hwkNum):
        #type: (str, str) -> list[str]
        cookie_header = headers.get('Cookie')
        fingerprint_list = []
        if cookie_header:
            cookies = cookie_header.split(';')
            for cookie in cookies:
                if f'hmwk{hwkNum}_fingerprints=' in cookie:
                    fingerprint = cookie.split('=')[1].strip()
                    fingerprint = fingerprint.replace(':', ',')
                    fingerprint_list = fingerprint.split(',')
                    break
        return fingerprint_list

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
    
    def standardButtons(self):
        #type: () -> str
        # Add a button to get all completion codes, with the form_name set to get_codes
        HTML_out = "<h2>Navigation</h2>"
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out += "<input type='hidden' name='form_name' value='get_codes' />"
        HTML_out += "<input type='submit' value='Get Completion Codes' aria-label='Get Completion Codes' /></form>"
        # Add a button to change the active homework, with the form_name set to set_active_homework
        HTML_out += "<form method='GET' action='/app'>"
        HTML_out += "<input type='hidden' name='form_name' value='set_active_homework' />"
        HTML_out += "<input type='submit' value='Set Active Homework' aria-label='Set Active Homework' /></form>"
        return HTML_out


def evaluateTruthTable(df, statement, statements):
    #type: (pd.DataFrame, statementInterface.LogicalStatementInterface, list[statementInterface.LogicalStatementInterface]) -> tuple[bool, list[int]|None]
    # Convert 'T'/'F'/'' to True/False/None
    bool_df = df.replace({'T': True, 'F': False, '': None})
    # Rename columns to statement strings
    bool_df.columns = [s.prettyPrint() for s in statements]
    logger.logger.info("Evaluating DataFrame:\n%s", bool_df)
    # Calculate the correct truth table
    answerkey = sh.calculateTruthTable(statement)
    logger.logger.info("Answer key:\n%s", answerkey)
    # Compare the two DataFrames
    comparison_result = sh.dataframesEquivalent(answerkey, bool_df)
    logger.logger.info("Comparison result: %s", comparison_result)
    return comparison_result

def cookieEncode(s):
    #type: (str) -> str
    # Encode the string to ASCII, replacing non-ASCII characters with escape sequences
    s = s.encode('ascii', 'backslashreplace').decode('ascii')
    # URL encode the string to make it safe for cookies
    s = urllib.parse.quote(s)
    return s

def cookieDecode(question):
    #type: (str) -> str
    # URL decode the string
    question = urllib.parse.unquote(question)
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
    logger.logger.info("DataFrame to print:\n%s", df)
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

def formatCode(code):
    #adjust code from hex strings to base64 strings for display
    code_bytes = bytes.fromhex(code)
    #Already base 64 encoded, convert to ascii string to avoid ugly b'' formatting
    b64 = code_bytes.decode('ascii')
    return b64
