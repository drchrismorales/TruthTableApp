#!/usr/bin/python3
import os
import sys

HERE = os.path.dirname(__file__)          # /home/username/public_html
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from wsgiref.simple_server import make_server
import pandas as pd  # kept to mirror original imports; remove if unused
import argument
import equivalence
import questionManager
import logger

# Instantiate your core logic once (module-level, like before)
coreLogic = questionManager.QuestionManager()


def _wsgi_headers_adapter(environ):
    """
    Minimal adapter to mimic BaseHTTPRequestHandler.headers for code that
    expects something with dict-like access to 'Cookie'.
    """
    class HeadersAdapter(dict):
        def __init__(self, env):
            super().__init__()
            if 'HTTP_COOKIE' in env:
                # Match capitalization typically seen in HTTP headers
                self['Cookie'] = env['HTTP_COOKIE']

        # Optional convenience: emulate .get like a mapping
        def get(self, key, default=None):
            return super().get(key, default)

    return HeadersAdapter(environ)


def _get_form_data(environ):
    #type: (dict) -> dict|None
    """
    Mirror the original get_form_data behavior exactly:
    - Pull raw query string (no URL decoding)
    - Split on & and =, keep blank values
    - Return None if no query string present
    """
    qs = environ.get('QUERY_STRING', '')
    if not qs:
        return None
    form_data = {}
    for pair in qs.split('&'):
        if '=' in pair:
            key, value = pair.split('=', 1)
        else:
            key, value = pair, ''
        form_data[key] = value
    return form_data


def application(environ, start_response):
    method = environ.get('REQUEST_METHOD', 'GET')
    path = environ.get('PATH_INFO', '') or '/'

    logger.logger.info("Received {} request for path: {}?{}".format(
        method, path, environ.get('QUERY_STRING', '')
    ))

    if method != 'GET':
        start_response('405 Method Not Allowed', [('Content-Type', 'text/plain; charset=utf-8')])
        return [b'Method Not Allowed']

    headers_adapter = _wsgi_headers_adapter(environ)

    # Pull current question from cookie (as before)
    st, st_DAG, split, nIDed, ordering, tt_row_ordering, subsequent_step, fingerprint = (
        coreLogic.get_current_question_from_cookie(headers_adapter)
    )

    question_type = "Equivalence" if isinstance(st, equivalence.Equivalence) else "Argument" if isinstance(st, argument.Argument) else "Statement"
    form_data = _get_form_data(environ)

    page = None
    if form_data is not None:
        page = form_data.get('form_name', None)

    # Record the originating IP address for new questions
    origin_ip = environ.get('REMOTE_ADDR', 'unknown')

    response_cookie = None
    response_body = ""

    # Special overrides
    if path == '/favicon.ico':
        start_response('204 No Content', [])
        return [b'']

    # On first visit or no question, start new question
    if st is None:
        response_cookie, response_body = coreLogic.newQuestionPage(origin_ip)
    # Route to check pages based on form_name
    elif page == 'split_check':
        response_cookie, response_body = coreLogic.checkSplitStatementPage(form_data, st, fingerprint)
    elif page == 'identify_substatements_check':
        response_cookie, response_body = coreLogic.checkIdentifySubstatementsPage(form_data, st, nIDed, fingerprint)
    elif page == 'order_check':
        response_cookie, response_body = coreLogic.checkOrderSubstatementsPage(form_data, st_DAG, fingerprint)
    elif page == 'truth_table_check':
        response_cookie, response_body = coreLogic.checkTruthTablePage(form_data, st_DAG, ordering, question_type, fingerprint)
    elif page == 'identify_columns_check':
        response_cookie, response_body = coreLogic.checkIdentifyColumnsPage(form_data, st_DAG, ordering, tt_row_ordering, fingerprint)
    elif page == 'equivalence_check':
        response_cookie, response_body = coreLogic.checkEquivalencePage(form_data, st_DAG, ordering, tt_row_ordering, fingerprint)
    elif page == 'identify_argument_columns_check':
        response_cookie, response_body = coreLogic.checkIdentifyArgumentPremiseColumnsPage(form_data, st_DAG, ordering, tt_row_ordering, fingerprint)
    elif page == 'identify_argument_rows_check':
        response_cookie, response_body = coreLogic.checkIdentifyArgumentRowsPage(form_data, st_DAG, ordering, tt_row_ordering, fingerprint)
    elif page == 'identify_argument_conclusion_check':
        response_cookie, response_body = coreLogic.checkIdentifyArgumentConclusionColumnPage(form_data, st_DAG, ordering, tt_row_ordering, fingerprint)
    elif page == 'argument_validity_check':
        response_cookie, response_body = coreLogic.checkArgumentValidityPage(form_data, st_DAG, ordering, tt_row_ordering, fingerprint)
    # Route to current question step pages based on status
    elif not split:
        response_cookie, response_body = coreLogic.splitStatementPage(st)
    elif nIDed < st.countComplexSubstatements():
        response_cookie, response_body = coreLogic.identifySubstatementsPage(st, nIDed)
    elif len(ordering) != len(list(st_DAG.reportAllSubstatements())):
        response_cookie, response_body = coreLogic.orderSubstatementsPage(st_DAG)
    elif len(tt_row_ordering) != 2 ** len(list(st_DAG.reportSimpleStatements())):
        response_cookie, response_body = coreLogic.truthTablePage(st_DAG, ordering)
    elif question_type == "Statement":
        # That was the last question
        response_cookie, response_body = coreLogic.completeQuestionPage(origin_ip, st, fingerprint, headers_adapter)
    elif question_type == "Equivalence":
        if subsequent_step == 0:
            response_cookie, response_body = coreLogic.identifyColumnsPage(st_DAG, ordering, tt_row_ordering)
        elif subsequent_step == 1:
            response_cookie, response_body = coreLogic.equivalentQuestionPage(st_DAG, ordering, tt_row_ordering)
        else:
            # That was the last question
            response_cookie, response_body = coreLogic.completeQuestionPage(origin_ip, st, fingerprint, headers_adapter)
    elif question_type == "Argument":
        if subsequent_step == 0:
            # Identify premises
            response_cookie, response_body = coreLogic.identifyArgumentPremiseColumnsPage(st_DAG, ordering, tt_row_ordering)
        elif subsequent_step == 1:
            # Mark rows needed to show validity
            response_cookie, response_body = coreLogic.identifyArgumentRowsPage(st_DAG, ordering, tt_row_ordering)
        elif subsequent_step == 2:
            # Identify conclusion
            response_cookie, response_body = coreLogic.identifyArgumentConclusionColumnPage(st_DAG, ordering, tt_row_ordering)
        elif subsequent_step == 3:
            # Determine if argument is valid
            response_cookie, response_body = coreLogic.argumentQuestionPage(st_DAG, ordering, tt_row_ordering)
        else:
            # That was the last question
            response_cookie, response_body = coreLogic.completeQuestionPage(origin_ip, st, fingerprint, headers_adapter)
    # Should be unreachable
    else:
        start_response('404 Not Found', [('Content-Type', 'text/plain; charset=utf-8')])
        return [b'Not Found']

    # Build response headers
    headers = [('Content-Type', 'text/html; charset=utf-8')]
    if response_cookie is not None: #Note: should always pass now that response_cookie is a list
        # List of cookies. Each cookie to be set needs its own Set-Cookie header
        for cookie in response_cookie: # If there was no cookie set, the cookie list will typically contain None... because hysterical reasons
            if cookie is not None:
                headers.append(('Set-Cookie', cookie))

    start_response('200 OK', headers)
    return [response_body.encode('utf-8')]


if __name__ == '__main__':
    # Local dev server (you can also run under gunicorn/uwsgi, etc.)
    with make_server('', 8000, application) as httpd:
        logger.logger.info("Serving on port 8000...")
        httpd.serve_forever()
