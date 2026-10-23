"""Draw the bus countdown as a 13 x 8 frame for the LED matrix.

A frame travels to the sketch as a 104-character string of '0' to '7', row by row,
so all the drawing lives here, where it can be tested without the board.
"""

DIGITS = {
    "0": ["777", "7.7", "7.7", "7.7", "777"],
    "1": [".7.", "77.", ".7.", ".7.", "777"],
    "2": ["777", "..7", "777", "7..", "777"],
    "3": ["777", "..7", ".77", "..7", "777"],
    "4": ["7.7", "7.7", "777", "..7", "..7"],
    "5": ["777", "7..", "777", "..7", "777"],
    "6": ["777", "7..", "777", "7.7", "777"],
    "7": ["777", "..7", "..7", ".7.", ".7."],
    "8": ["777", "7.7", "777", "7.7", "777"],
    "9": ["777", "7.7", "777", "..7", "777"],
    "-": ["...", "...", "777", "...", "..."],
}

# A small bus seen from the side, 4 wide, dimmer than the numbers
BUS = ["3333", "3..3", "3333", "3333", ".3.3"]


def countdown(minutes):
    """Bus on the left, minutes on the right. 100 or more shows as '--'."""
    text = f"{minutes:>2}" if minutes is not None and 0 <= minutes < 100 else "--"
    grid = [["."] * 13 for _ in range(8)]

    def stamp(art, left, top=2):
        for y, row in enumerate(art):
            for x, c in enumerate(row):
                if c != ".":
                    grid[top + y][left + x] = c

    stamp(BUS, 0)
    for i, ch in enumerate(text):
        if ch != " ":
            stamp(DIGITS[ch], 5 + i * 4)
    return "".join("0" if c == "." else c for row in grid for c in row)


def render(frame):
    """ASCII preview of a frame, for tests and the README."""
    return "\n".join(frame[i:i + 13].replace("0", ".") for i in range(0, 104, 13))
