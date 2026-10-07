"""Test direct du REPL avec 'help config'."""
import sys
from io import StringIO

# Simuler stdin avec "help config\nexit\n"
sys.stdin = StringIO("help config\nexit\n")

# Lancer le REPL
from uexinfo.cli.main import main

try:
    main()
except SystemExit:
    pass
