# Suppress REPL console on the display as early as possible
import board
board.DISPLAY.root_group = None
