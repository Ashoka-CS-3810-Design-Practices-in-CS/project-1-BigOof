"""Big O: Delhi Metro route planner."""


def main() -> None:
    """Entry point for the ``big-o`` console script: run the development server.

    The app is imported here rather than at module level so that importing
    ``big_o.back`` doesn't also load Flask and the metro database.
    """
    from .app import app

    app.run(host="127.0.0.1", port=5000, debug=True)
