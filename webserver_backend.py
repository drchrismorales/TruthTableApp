#EG: http://localhost:8000/users/whoops.txt?gname=%27OR%271&fname=%27%27
from http.server import HTTPServer, BaseHTTPRequestHandler
import statementParser
import questionGenerator
import pandas as pd

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        print("Received GET request for path:", self.path)
        # Split html arguments away from path
        path, _, query = self.path.partition('?')
        #  For now, if no path was given, default to truth table question page
        if not path or path == '/':
            path = '/truth_table_question'

        # Route based on path
        if path == '/truth_table_question':
            self.truthTablePage()
        elif path == '/truth_table_check':
            self.checkTruthTable()
        elif path == '/favicon.ico':
            self.send_response(204)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def truthTablePage(self):
        # Check if there's a current question in cookies
        cookie_header = self.headers.get('Cookie')
        question = None
        cookie_string = None
        if cookie_header:
            cookies = cookie_header.split(';')
            for cookie in cookies:
                if 'current_question=' in cookie:
                    question = cookie.split('=')[1].strip()
                    question = cookieDecode(question)
                    break
        if question:
            #try to parse it
            try:
                st = statementParser.Statement(question)
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Error parsing question: {e}".encode("utf-8"))
                return
        else:
            # Generate a new question
            question = questionGenerator.makeRandomQuestion(["and", "or", "not"], 2, 3)
            st = statementParser.Statement(question)
            # Set a cookie to keep track of the current question
            cookie_question = cookieEncode(question)
            #self.send_header("Set-Cookie", f"current_question={cookie_question}; Path=/")
            cookie_string = f"current_question={cookie_question}; Path=/"
        st = st.rectifyGraph()
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
        self.send_response(200)
        if cookie_string is not None:
            self.send_header("Set-Cookie", cookie_string)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_out.encode("utf-8"))
    
    def checkTruthTable(self):
        # Check if there's a current question in cookies
        cookie_header = self.headers.get('Cookie')
        question = None
        cookie_text = None
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
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Error parsing question: {e}".encode("utf-8"))
                return
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("No current question found.".encode("utf-8"))
            return
        st = st.rectifyGraph()
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
        response = ""
        if result:
            #Also drop the cookie
            cookie_text = "current_question=; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
            response = "<html><body><h2>Correct!</h2></body></html>"
            # Add a button to "Try another question" that links to /truth_table_question
            response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try another question' /></form>"
        else:
            response = "<html><body><h2>Incorrect. Try again.</h2></body></html>"
            # Add a button to "Try again" that links to /truth_table_question
            response += "<form method='GET' action='/truth_table_question'><input type='submit' value='Try again' /></form>"
        # Send the results back to the client
        self.send_response(200)
        if cookie_text is not None:
            self.send_header("Set-Cookie", cookie_text)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(response.encode("utf-8"))

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
