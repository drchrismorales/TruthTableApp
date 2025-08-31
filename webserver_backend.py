#EG: http://localhost:8000/users/whoops.txt?gname=%27OR%271&fname=%27%27
from http.server import HTTPServer, BaseHTTPRequestHandler
import statementParser
import questionGenerator
import pandas as pd

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        response_cookie = None
        response_body = ""
        print("Received GET request for path:", self.path)
        # Split html arguments away from path
        path, _, query = self.path.partition('?')
        # Check for question in cookie
        st = self.get_current_question_from_cookie(self.headers)
        #  For now, if no path was given, default to truth table question page
        if not path or path == '/':
            path = '/truth_table_question'

        # Route based on path (soon, it will be routed based on question status (saved in cookie) with a much reduced role for path)
        if path == '/favicon.ico':
            self.send_response(204)
            return
        elif st is None:
            response_cookie, response_body = self.newQuestionPage()
        elif path == '/truth_table_question':
            response_cookie, response_body = self.truthTablePage(st)
        elif path == '/truth_table_check':
            response_cookie, response_body = self.checkTruthTablePage(st)
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
        st = self.getNewQuestion()
        # If we generated a new question, set the cookie
        cookie_question = cookieEncode(st.prettyPrint())
        response_cookie = f"current_question={cookie_question}; Path=/"
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

    def truthTablePage(self, st):
        cookie_string = None
        question = st.prettyPrint()
        simple = list(st.reportSimpleStatements())
        statements = list(st.reportAllSubstatements())
        nrows = 2**len(simple)
        ncols = len(statements)
        n, m = nrows, ncols
        fields = []
        statements.sort()
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
        HTML_out = HTML_out + "<input type='submit' value='Submit' />"
        HTML_out = HTML_out + "</form></body></html>"

        #return: No cookie, HTML body
        return None, HTML_out

    def checkTruthTablePage(self, st):
        cookie_text = None
        # Retrieve form data from query string
        post_data = self.path.split('?', 1)[1] if '?' in self.path else None
        if post_data is None:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("No form data received.".encode("utf-8"))
            return
        form_data = {}
        for pair in post_data.split('&'):
            key, value = pair.split('=')
            form_data[key] = value
        simple = list(st.reportSimpleStatements())
        statements = list(st.reportAllSubstatements())
        statements.sort()
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
        HTML_response = ""
        if result:
            #Also drop the cookie
            cookie_text = "current_question=; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
            HTML_response = "<html><body><h2>Correct!</h2></body></html>"
            # Add a button to "Try another question" that links to /truth_table_question
            HTML_response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try another question' /></form>"
        else:
            HTML_response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that links to /truth_table_question
            HTML_response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try again' /></form>"

        return cookie_text, HTML_response

    # returns the current question Statement object from the cookie, or None if not found
    def get_current_question_from_cookie(self, headers):
        cookie_header = headers.get('Cookie')
        question = None
        if cookie_header:
            cookies = cookie_header.split(';')
            for cookie in cookies:
                if 'current_question=' in cookie:
                    question = cookie.split('=')[1].strip()
                    question = cookieDecode(question)
                    break
        if question is not None:
            #try to parse it
            try:
                st = statementParser.Statement(question)
            except Exception as e:
                # Exception handling
                return None
            st = st.rectifyGraph()
            return st
        return None

    def getNewQuestion(self):
        # Generate a new question
        question = questionGenerator.makeRandomQuestion(["and", "or", "not"], 2, 1)
        st = statementParser.Statement(question)
        st = st.rectifyGraph()
        return st

def evaluateTruthTable(df, statement, statements):
    # Convert 'T'/'F'/'' to True/False/None
    bool_df = df.replace({'T': True, 'F': False, '': None})
    # Rename columns to statement strings
    bool_df.columns = [s.prettyPrint() for s in statements]
    print(f"Evaluating DataFrame:\n{bool_df}")
    # Calculate the correct truth table
    answerkey = statementParser.calculateTruthTable(statement)
    print(f"Answer key:\n{answerkey}")
    # Compare the two DataFrames
    correct = statementParser.dataframesEquivalent(answerkey, bool_df)
    print(f"Comparison result: {correct}")
    return correct

def cookieEncode(s):
    # Encode the string to ASCII, replacing non-ASCII characters with escape sequences
    return s.encode('ascii', 'backslashreplace').decode('ascii')

def cookieDecode(question):
    # Decode the cookie-encoded string back to its original form
    return question.encode('ascii').decode('unicode_escape')

httpd = HTTPServer(('', 8000), SimpleHTTPRequestHandler)
httpd.serve_forever()
