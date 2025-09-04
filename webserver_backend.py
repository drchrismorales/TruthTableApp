#!/usr/bin/python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import pandas as pd
import equivalence
import questionManager

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        global coreLogic
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
        st, st_DAG, split, nIDed, ordering, tt_row_ordering, subsequent_step = coreLogic.get_current_question_from_cookie(self.headers)

        question_type = "Equivalence" if isinstance(st, equivalence.Equivalence) else "Statement"

        form_data = self.get_form_data()
        # Route as-needed based on path and question status
        # Special overide cases (favicon, no question)
        if path == '/favicon.ico':
            self.send_response(204)
            return
        elif st is None:
            response_cookie, response_body = coreLogic.newQuestionPage()
        # Route to check pages based on path
        elif path == '/split_check':
            response_cookie, response_body = coreLogic.checkSplitStatementPage(form_data, st)
        elif path == '/identify_substatements_check':
            response_cookie, response_body = coreLogic.checkIdentifySubstatementsPage(form_data, st, nIDed)
        elif path == '/order_check':
            response_cookie, response_body = coreLogic.checkOrderSubstatementsPage(form_data, st_DAG)
        elif path == '/truth_table_check':
            response_cookie, response_body = coreLogic.checkTruthTablePage(form_data, st_DAG, ordering, question_type)
        elif path == '/identify_columns_check':
            response_cookie, response_body = coreLogic.checkIdentifyColumnsPage(form_data, st_DAG, ordering, tt_row_ordering)
        elif path == '/equivalence_check':
            response_cookie, response_body = coreLogic.checkEquivalencePage(form_data, st_DAG, ordering, tt_row_ordering)

        # Route to current question step pages based on question status
        elif not split:
            response_cookie, response_body = coreLogic.splitStatementPage(st)
        elif nIDed < st.countComplexSubstatements():
            response_cookie, response_body = coreLogic.identifySubstatementsPage(st, nIDed)
        elif len(ordering) != len(list(st_DAG.reportAllSubstatements())):
            response_cookie, response_body = coreLogic.orderSubstatementsPage(st_DAG)
        elif len(tt_row_ordering) != 2**len(list(st_DAG.reportSimpleStatements())):
            response_cookie, response_body = coreLogic.truthTablePage(st_DAG, ordering)
        elif question_type == "Statement":
            #That was the last question
            response_cookie, response_body = coreLogic.newQuestionPage()
        elif question_type == "Equivalence":
            if subsequent_step == 0:
                response_cookie, response_body = coreLogic.identifyColumnsPage(st_DAG, ordering, tt_row_ordering)
            elif subsequent_step == 1:
                response_cookie, response_body = coreLogic.equivalentQuestionPage(st_DAG, ordering, tt_row_ordering)
            else:
                #That was the last question
                response_cookie, response_body = coreLogic.newQuestionPage()
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

coreLogic = questionManager.QuestionManager()
httpd = HTTPServer(('', 8000), SimpleHTTPRequestHandler)
httpd.serve_forever()

