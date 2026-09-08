# Discrete Math Problem Checker: Boolhound edition

A discrete-math homework web app that quizzes students on propositional logic: parsing
well-formed formulas, building truth tables, checking logical equivalences, and evaluating
argument validity.

## Setup

Run the interactive setup script first — it creates the local config files (`key.txt`,
`config.txt`) that aren't included in the git repo, and checks that the runtime dependencies
(`pandas`, `cryptography`) are installed:

```
python3 setup.py
```

## Running

`wsgi_backend.py` is the app's entry point (`application`). You can run it two ways:

**Locally, for development** — starts a built-in dev server on `localhost:8000`:

```
python3 wsgi_backend.py
```

**Behind an existing webserver, for production** — point your WSGI host (e.g. Apache +
mod_wsgi, gunicorn, uwsgi) at the `application` object in `wsgi_backend.py` instead of running
the file directly.

`webserver_backend.py` and `local_frontend.py` are deprecated prototypes kept only for
historical reference — don't run or extend them.
