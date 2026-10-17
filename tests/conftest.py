import os

# Keep test runs from writing log files into the repo; logs still reach stdout
# and pytest's caplog. Set before any test module imports big_o.app.
os.environ.setdefault("LOG_DIR", "")
