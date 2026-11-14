"""Attack Riley by hand — LOCAL (Ollama) or --remote (real server).

    python3 chat_local.py            # local Ollama Riley
    python3 chat_local.py --remote   # the real hosted Riley (needs an API key)

Type a message and press Enter. Commands:
  /new     fresh conversation (Riley forgets everything)
  /switch  pick a different model
  /models  re-list available models
  /quit
"""
import argparse, sys
from riley_backend import make_backend

# Preferred local picks; any other installed model still shows up below.
SUGGESTED = [
    ("qwen3:4b", "small, fast — start here"),
    ("qwen3:8b", "small-medium"),
    ("qwen3:14b", "medium"),
    ("qwen3.8:27b", "large (slower, stronger refusals)"),
    ("dolphin3:latest", "uncensored — weak guardrails, good for testing the filter"),
    ("dolphin-llama3:8b", "uncensored"),
]


def pick(prompt, n, default=1):
    while True:
        a = input(f"{prompt} [{default}]: ").strip() or str(default)
        if a.isdigit() and 1 <= int(a) <= n:
            return int(a)
        print(f"  Type a number from 1 to {n}.")


def choose(backend):
    try:
        installed = set(backend.list_models())
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not list models: {e}")
    if not installed:
        sys.exit("No models available. (Remote: ask an organizer / check your key.)")
    if backend.name == "local":
        rows = [(m, d) for m, d in SUGGESTED if m in installed]
        rows += [(m, "") for m in sorted(installed) if m not in {r[0] for r in rows}]
    else:
        rows = [(m, "") for m in backend.list_models()]  # server order = weakest first
    print(f"\n{backend.name.capitalize()} models (Riley will be played by the one you pick):")
    for i, (m, d) in enumerate(rows, 1):
        print(f"  {i}. {m}" + (f"  — {d}" if d else ""))
    model = rows[pick("Pick a model", len(rows)) - 1][0]
    print(f"\n--- New conversation with Riley (as {model}). /new /switch /models /quit ---\n")
    return model, backend.new_conversation()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", action="store_true",
                    help="attack the REAL hosted Riley (needs an API key; run setup.py)")
    args = ap.parse_args()
    backend = make_backend(remote=args.remote)
    print(f"[target: {backend.name} Riley]")

    model, conv = choose(backend)
    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not msg:
            continue
        if msg == "/quit":
            break
        if msg == "/new":
            conv = backend.new_conversation()
            print("--- Fresh conversation (Riley forgot everything) ---\n"); continue
        if msg == "/switch":
            model, conv = choose(backend); continue
        if msg == "/models":
            print("Available:", ", ".join(backend.list_models()), "\n"); continue
        print("Riley is thinking...")
        try:
            res = backend.chat(msg, model, conv)
            print(f"Riley: {res['reply']}\n        (turn_id: {res['turn_id']})\n")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  {e}\n")
    print("Bye! Attempts saved to logs/")


if __name__ == "__main__":
    main()
