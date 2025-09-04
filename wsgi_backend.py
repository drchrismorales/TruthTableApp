#!/usr/bin/python3
from wsgiref.simple_server import make_server
import pandas as pd  # kept to mirror original imports; remove if unused
import equivalence
import questionManager

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


def app(environ, start_response):
    method = environ.get('REQUEST_METHOD', 'GET')
    path = environ.get('PATH_INFO', '') or '/'

    # Simple logging (like your print)
    print("Received {} request for path: {}?{}".format(
        method, path, environ.get('QUERY_STRING', '')
    ))

    if method != 'GET':
        start_response('405 Method Not Allowed', [('Content-Type', 'text/plain; charset=utf-8')])
        return [b'Method Not Allowed']

    # Default to truth table question page for root
    if path == '/':
        path = '/truth_table_question'

    headers_adapter = _wsgi_headers_adapter(environ)

    # Pull current question from cookie (as before)
    st, st_DAG, split, nIDed, ordering, tt_row_ordering, subsequent_step = (
        coreLogic.get_current_question_from_cookie(headers_adapter)
    )

    question_type = "Equivalence" if isinstance(st, equivalence.Equivalence) else "Statement"
    form_data = _get_form_data(environ)

    response_cookie = None
    response_body = ""

    # Special overrides
    if path == '/favicon.ico':
        start_response('204 No Content', [])
        return [b'']

    # Route to check pages (same structure as original)
    if st is None:
        response_cookie, response_body = coreLogic.newQuestionPage()
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
        response_cookie, response_body = coreLogic.newQuestionPage()
    elif question_type == "Equivalence":
        if subsequent_step == 0:
            response_cookie, response_body = coreLogic.identifyColumnsPage(st_DAG, ordering, tt_row_ordering)
        elif subsequent_step == 1:
            response_cookie, response_body = coreLogic.equivalentQuestionPage(st_DAG, ordering, tt_row_ordering)
        else:
            # That was the last question
            response_cookie, response_body = coreLogic.newQuestionPage()
    else:
        start_response('404 Not Found', [('Content-Type', 'text/plain; charset=utf-8')])
        return [b'Not Found']

    # Build response headers
    headers = [('Content-Type', 'text/html; charset=utf-8')]
    if response_cookie is not None:
        headers.append(('Set-Cookie', response_cookie))

    start_response('200 OK', headers)
    return [response_body.encode('utf-8')]


if __name__ == '__main__':
    # Local dev server (you can also run under gunicorn/uwsgi, etc.)
    with make_server('', 8000, app) as httpd:
        print("Serving on port 8000...")
        httpd.serve_forever()
