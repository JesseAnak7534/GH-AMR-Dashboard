"""
Colour, chosen so that colour is never the only thing carrying a meaning.

The palette is Okabe and Ito's eight-colour set (Okabe & Ito, 2008), which was
designed to stay distinguishable under the three common forms of colour vision
deficiency. Roughly one man in twelve has one of them, and a surveillance figure
that only separates "resistant" from "susceptible" by a red and a green hue is
unreadable to them -- not harder to read, unreadable.

Two rules apply wherever these are used.

**Colour repeats information, it never carries it alone.** Every series that is
distinguished by colour is also distinguished by its label, its position, or a
pattern. A reader who sees no colour at all should lose nothing but speed.

**Order is fixed.** Sectors, verdicts and qualities keep the same colour on
every page. A reader who learns that aquaculture is the blue-green one on the
One Health page should not have to relearn it on the next page.

Luminance was checked against both a white and a dark background: these are all
usable as a fill behind black or very dark text, which is why the text on a
coloured card in this platform is dark rather than white.
"""

from __future__ import annotations

# ── Okabe-Ito, by name ─────────────────────────────────────────────────
BLACK = "#000000"
ORANGE = "#E69F00"
SKY = "#56B4E9"
GREEN = "#009E73"
YELLOW = "#F0E442"
BLUE = "#0072B2"
VERMILLION = "#D55E00"
PURPLE = "#CC79A7"
GREY = "#999999"

#: The qualitative sequence, in the order it should be consumed. Blue first
#: because it is the most legible of the set at small sizes.
SEQUENCE = [BLUE, ORANGE, GREEN, VERMILLION, SKY, PURPLE, YELLOW, GREY]

#: One colour per sector, fixed across every page.
SECTOR = {
    "human": BLUE,
    "animal": ORANGE,
    "food": GREEN,
    "environment": PURPLE,
    "aquaculture": SKY,
}

#: Susceptibility. Vermillion and blue rather than red and green: the red/green
#: pair is exactly the one that disappears under deuteranopia, and S/I/R is the
#: single most consequential distinction on the platform.
RESULT = {
    "S": BLUE,
    "I": ORANGE,
    "R": VERMILLION,
    "NS": VERMILLION,
}

#: Sequencing quality.
QUALITY = {
    "pass": BLUE,
    "fail": VERMILLION,
    "not assessable": GREY,
}

#: Anything withheld or not measured. Deliberately grey and deliberately the
#: same grey everywhere, so a reader learns to read it as "no number here"
#: rather than as a category.
MISSING = GREY


def ramp(n: int) -> list:
    """``n`` distinguishable colours, repeating the sequence if pushed past it.

    Past eight categories the set cannot keep them apart and neither can a
    reader; the caller should be grouping instead. The repeat is here so a chart
    still draws rather than failing, not because nine categories are a good
    idea.
    """
    if n <= 0:
        return []
    out = []
    while len(out) < n:
        out.extend(SEQUENCE)
    return out[:n]


__all__ = [
    "BLACK", "ORANGE", "SKY", "GREEN", "YELLOW", "BLUE", "VERMILLION",
    "PURPLE", "GREY", "SEQUENCE", "SECTOR", "RESULT", "QUALITY", "MISSING",
    "ramp",
]
