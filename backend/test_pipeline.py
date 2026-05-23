"""
Interactive Pipeline Tester
---------------------------
Run:  python test_pipeline.py

Type a single line or a multi-line conversation block and see the full
pipeline output:

    Context Classification  →  Pattern Detection  →  Confidence Scoring
    →  Negation/Joke Filter  →  Risk Score  →  Risk Level

Commands
--------
  quit / exit / q   — exit the tester
  multi             — enter multi-line mode (blank line to submit)
  clear             — clear the screen
  help              — show this help
"""

import os
import sys
import textwrap

# ── make sure we can import from the backend package ──────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from modules.context_analyzer import ContextAnalyzer, ContextType, CONTEXT_MULTIPLIERS
from modules.grooming_detector import GroomingDetector
from modules.risk_scorer import WeightedRiskScorer
from modules.filters import CombinedFilter

# ── ANSI colours (disabled automatically on Windows without ANSI support) ─────
def _ansi(code: str, text: str) -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            return text
    return f"\033[{code}m{text}\033[0m"

RED     = lambda t: _ansi("91", t)
YELLOW  = lambda t: _ansi("93", t)
GREEN   = lambda t: _ansi("92", t)
CYAN    = lambda t: _ansi("96", t)
BOLD    = lambda t: _ansi("1",  t)
DIM     = lambda t: _ansi("2",  t)
MAGENTA = lambda t: _ansi("95", t)

# ── severity colours ───────────────────────────────────────────────────────────
SEVERITY_COLOR = {
    "critical": RED,
    "high":     YELLOW,
    "medium":   CYAN,
    "low":      GREEN,
    "unknown":  DIM,
}

LEVEL_COLOR = {
    "Safe":     GREEN,
    "Low":      GREEN,
    "Moderate": YELLOW,
    "High":     RED,
    "Critical": RED,
}

CTX_COLOR = {
    "ADMINISTRATIVE":        GREEN,
    "NEUTRAL":               DIM,
    "INFORMATION_GATHERING": YELLOW,
    "TRUST_BUILDING":        YELLOW,
    "RELATIONSHIP_BUILDING": YELLOW,
    "MANIPULATION":          RED,
    "SECRECY":               RED,
    "ESCALATION":            RED,
    "MEETING":               RED,
    "PERSONAL_INFORMATION":  RED,
    "VIDEO_CALL":            YELLOW,
    "EXPLICIT_CONTENT":      RED,
    "BAD_LANGUAGE":          MAGENTA,
}

# ── shared instances (created once) ───────────────────────────────────────────
_ctx_analyzer = ContextAnalyzer()
_detector     = GroomingDetector(min_confidence_threshold=0.10)
_scorer       = WeightedRiskScorer()
_filter       = CombinedFilter()

DIVIDER      = DIM("─" * 72)
THICK_DIV    = BOLD("═" * 72)


# ─────────────────────────────────────────────────────────────────────────────
# Display helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ctx_badge(ctx_name: str) -> str:
    color = CTX_COLOR.get(ctx_name, DIM)
    return color(f"[{ctx_name}]")


def _conf_bar(conf: float, width: int = 20) -> str:
    filled = int(conf * width)
    bar    = "█" * filled + "░" * (width - filled)
    pct    = f"{conf * 100:5.1f}%"
    if conf >= 0.7:
        return RED(bar) + f" {pct}"
    elif conf >= 0.4:
        return YELLOW(bar) + f" {pct}"
    else:
        return GREEN(bar) + f" {pct}"


def _risk_badge(level: str) -> str:
    color = LEVEL_COLOR.get(level, DIM)
    return color(f"[ {level.upper()} ]")


def _score_bar(score: float, width: int = 30) -> str:
    filled = int((score / 100) * width)
    bar    = "█" * filled + "░" * (width - filled)
    if score >= 61:
        return RED(bar)
    elif score >= 41:
        return YELLOW(bar)
    else:
        return GREEN(bar)


# ─────────────────────────────────────────────────────────────────────────────
# Section printers
# ─────────────────────────────────────────────────────────────────────────────

def print_context_section(text: str) -> None:
    result = _ctx_analyzer.classify(text)
    primary    = result["primary_context"].value
    all_ctxs   = [ct.value for ct in result["all_contexts"]]
    multiplier = result["multiplier"]
    terms      = result["matched_terms"]

    print(BOLD("\n  ① CONTEXT CLASSIFICATION"))
    print(DIVIDER)
    print(f"  Primary  : {_ctx_badge(primary)}")
    if len(all_ctxs) > 1:
        print(f"  All      : {' '.join(_ctx_badge(c) for c in all_ctxs)}")

    mult_str = f"{multiplier:+.2f}"
    if multiplier > 0:
        mult_display = RED(mult_str) + "  (raises confidence)"
    elif multiplier < 0:
        mult_display = GREEN(mult_str) + "  (lowers confidence — administrative)"
    else:
        mult_display = DIM(mult_str) + "  (neutral)"
    print(f"  Multiplier: {mult_display}")

    if terms:
        print(f"  Matched  :")
        for ctx_type, matched in terms.items():
            color = CTX_COLOR.get(ctx_type.value, DIM)
            print(f"    {color(ctx_type.value):<30} {DIM(', '.join(matched[:4]))}")


def print_filter_section(text: str) -> None:
    result = _filter.analyze(sentence=text)
    is_neg  = result["is_negated"]
    is_joke = result["is_joke"]
    neg_s   = result["negation_score"]
    joke_s  = result["joke_score"]
    penalty = result["confidence_penalty"]

    print(BOLD("\n  ② NEGATION / JOKE FILTER"))
    print(DIVIDER)

    neg_icon  = RED("✗ NEGATED") if is_neg  else GREEN("✓ not negated")
    joke_icon = RED("✗ JOKE")    if is_joke else GREEN("✓ not a joke")
    print(f"  Negation : {neg_icon}   score={neg_s:.2f}")
    print(f"  Joke     : {joke_icon}  score={joke_s:.2f}")

    if penalty > 0:
        print(f"  Penalty  : {RED(f'-{penalty:.2f}')} applied to all findings")
    else:
        print(f"  Penalty  : {DIM('none')}")

    # Show scoped negation terms if any
    neg_details = result.get("negation_details", {})
    scoped = neg_details.get("scoped_negation_terms", [])
    if scoped:
        print(f"  Scoped negation terms: {DIM(', '.join(scoped))}")


def print_findings_section(findings: list) -> None:
    print(BOLD("\n  ③ PATTERN FINDINGS"))
    print(DIVIDER)

    if not findings:
        print(f"  {GREEN('No findings above threshold.')}")
        return

    for i, f in enumerate(findings, 1):
        cat      = f.get("category", "?")
        conf     = f.get("confidence", 0.0)
        ctx      = f.get("context_type", "NEUTRAL")
        sev      = f.get("severity", "unknown")
        matched  = f.get("matched_text", "")
        speaker  = f.get("speaker")
        scoring  = f.get("scoring", {})
        filters  = f.get("filters", {})

        sev_color = SEVERITY_COLOR.get(sev, DIM)

        print(f"\n  Finding #{i}")
        print(f"    Category  : {BOLD(cat.replace('_',' ').title())}")
        print(f"    Severity  : {sev_color(sev.upper())}")
        print(f"    Context   : {_ctx_badge(ctx)}")
        print(f"    Confidence: {_conf_bar(conf)}")
        print(f"    Matched   : {DIM(repr(matched[:80]))}")
        if speaker:
            print(f"    Speaker   : {DIM(speaker)}  {DIM('(audit only — not scored)')}")

        # Scoring breakdown
        if scoring:
            ps  = scoring.get("pattern_strength", 0)
            bc  = scoring.get("base_confidence", 0)
            fp  = scoring.get("filter_penalty", 0)
            cm  = scoring.get("context_multiplier", 0)
            fc  = scoring.get("final_confidence", conf)
            print(f"    Scoring   : base={ps:.2f}"
                  f"  +ctx={cm:+.2f}"
                  f"  -filter={fp:.2f}"
                  f"  → final={fc:.2f}")

        # Filter flags
        if filters.get("is_negated") or filters.get("is_joke"):
            flags = []
            if filters.get("is_negated"): flags.append(RED("negated"))
            if filters.get("is_joke"):    flags.append(YELLOW("joke"))
            print(f"    Flags     : {', '.join(flags)}")


def print_risk_section(findings: list) -> None:
    result = _scorer.calculate_score(findings)
    score  = result["score"]
    level  = result["level"]
    bdown  = result["breakdown"]

    print(BOLD("\n  ④ RISK SCORE"))
    print(DIVIDER)
    print(f"  Score : {BOLD(str(score))}/100  {_score_bar(score)}")
    print(f"  Level : {_risk_badge(level)}")

    if bdown:
        print(f"\n  Category Breakdown:")
        sorted_cats = sorted(bdown.items(), key=lambda x: x[1]["total_score"], reverse=True)
        for cat, details in sorted_cats:
            label  = cat.replace("_", " ").title()
            pts    = details["total_score"]
            n      = details["occurrence_count"]
            ctxs   = ", ".join(details.get("context_types", []))
            bar_w  = int((pts / 20) * 12)   # max weight=20 → 12 chars
            bar    = "▪" * min(bar_w, 12)
            ctx_str = f"  {DIM(ctxs)}" if ctxs else ""
            print(f"    {label:<22} {YELLOW(bar):<14} {pts:5.2f} pts  ×{n}{ctx_str}")


def print_summary_banner(findings: list) -> None:
    result = _scorer.calculate_score(findings)
    score  = result["score"]
    level  = result["level"]
    color  = LEVEL_COLOR.get(level, DIM)

    print(THICK_DIV)
    print(color(f"  RESULT: {level.upper()}  ({score:.1f}/100)  —  {len(findings)} finding(s)"))
    print(THICK_DIV)


# ─────────────────────────────────────────────────────────────────────────────
# Core analysis runner
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis(text: str) -> None:
    text = text.strip()
    if not text:
        return

    print(f"\n{THICK_DIV}")
    print(BOLD(f"  INPUT: ") + f"{text[:100]}{'...' if len(text) > 100 else ''}")
    print(THICK_DIV)

    # Detect if multi-line / transcript
    lines = [l for l in text.split("\n") if l.strip()]
    is_transcript = len(lines) > 1

    if is_transcript:
        result   = _detector.analyze_transcript(text)
        findings = result["grouped_findings"]
        print(DIM(f"  Mode: transcript ({len(lines)} lines, "
                  f"{result['metadata']['total_sentences']} sentences)"))
    else:
        findings = _detector.analyze_sentence(text)
        print(DIM("  Mode: single sentence"))

    # ── sections ──────────────────────────────────────────────────────────────
    print_context_section(text if not is_transcript else lines[0])
    print_filter_section(text if not is_transcript else lines[0])
    print_findings_section(findings)
    print_risk_section(findings)
    print_summary_banner(findings)


# ─────────────────────────────────────────────────────────────────────────────
# REPL
# ─────────────────────────────────────────────────────────────────────────────

HELP_TEXT = textwrap.dedent("""
    ┌─────────────────────────────────────────────────────────────┐
    │              Audio Safety Pipeline — Interactive Tester      │
    ├─────────────────────────────────────────────────────────────┤
    │  Type any sentence and press Enter to run the full pipeline. │
    │                                                              │
    │  Commands:                                                   │
    │    multi   — enter multi-line / transcript mode              │
    │              (type lines, then blank line to submit)         │
    │    clear   — clear the screen                                │
    │    help    — show this help                                  │
    │    quit    — exit                                            │
    │                                                              │
    │  Examples:                                                   │
    │    keep this between us, nobody needs to know                │
    │    what time does the science exhibition finish?             │
    │    let's meet up in person, just you and me                  │
    │    I didn't ask for your address                             │
    │    haha just kidding, let's meet up lol                      │
    └─────────────────────────────────────────────────────────────┘
""")


def get_multiline_input() -> str:
    print(CYAN("  Multi-line mode — enter lines, then a blank line to submit:"))
    lines = []
    while True:
        try:
            line = input("  > ")
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    print(HELP_TEXT)

    while True:
        try:
            raw = input(BOLD("pipeline> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not raw:
            continue

        cmd = raw.lower()

        if cmd in ("quit", "exit", "q"):
            print("Bye.")
            break
        elif cmd == "help":
            print(HELP_TEXT)
        elif cmd == "clear":
            os.system("cls" if sys.platform == "win32" else "clear")
        elif cmd == "multi":
            text = get_multiline_input()
            if text.strip():
                run_analysis(text)
        else:
            run_analysis(raw)


if __name__ == "__main__":
    main()
