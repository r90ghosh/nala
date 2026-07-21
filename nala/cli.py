"""Typed-text REPL — M0 naive baseline. Two tools called directly by name,
no chokepoint, no event log, no validation. Deliberately naive control group."""

import argparse

from nala.brain import Brain
from nala.tools.capture_task import capture_task
from nala.tools.report_status import report_status


def dispatch(brain: Brain, utterance: str) -> str:
    tool_name, tool_input = brain.decide(utterance)

    if tool_name == "capture_task":
        task = capture_task(
            title=tool_input.get("title", ""),
            project=tool_input.get("project", ""),
            priority=tool_input.get("priority", "medium"),
            category=tool_input.get("category", "feature"),
        )
        return f"captured task #{task['id']}: {task['title']}"

    if tool_name == "report_status":
        rows = report_status()
        lines = []
        for r in rows:
            if "error" in r:
                lines.append(f"{r['repo']}: {r['error']}")
                continue
            flags = "(dirty)" if r["dirty"] else ""
            lines.append(f"{r['repo']}: {r['branch']} {flags}".rstrip())
        return "\n".join(lines)

    return "I couldn't figure out what to do with that."


def main():
    parser = argparse.ArgumentParser(prog="nala")
    parser.add_argument("--turn", help="run a single turn and exit")
    args = parser.parse_args()

    brain = Brain()

    if args.turn:
        print(dispatch(brain, args.turn))
        return

    print("Nala (M0 naive baseline). Type 'exit' to quit.")
    while True:
        try:
            utterance = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if utterance.lower() in {"exit", "quit"}:
            break
        if not utterance:
            continue
        print(dispatch(brain, utterance))


if __name__ == "__main__":
    main()
