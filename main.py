"""Start the College Complaint Manager.

    python main.py                       terminal menu (SQLite database)
    python main.py --gui                 graphical window
    python main.py --data some_file.json use a JSON file instead of the database
"""
import argparse
import sys

import applog
import storage


def main():
    parser = argparse.ArgumentParser(description="College Complaint Manager")
    parser.add_argument("--gui", action="store_true", help="open the graphical window instead of the terminal menu")
    parser.add_argument("--data", default=storage.DEFAULT_FILE, metavar="FILE",
                        help="data file to use: a .db file (SQLite, default) or a .json file")
    args = parser.parse_args()

    applog.setup()

    if args.gui:
        try:
            import gui
        except ImportError:
            print("Tkinter isn't available in this Python install, so the window can't open.")
            print("The terminal version still works: python main.py")
            sys.exit(1)
        gui.run(args.data)
    else:
        import cli
        cli.run(args.data)


if __name__ == "__main__":
    main()
