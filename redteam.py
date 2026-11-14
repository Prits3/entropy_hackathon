"""Multi-agent red-team controller for Riley.

    Planner -> {direct, indirect, role-confusion} attackers (parallel) -> Riley
            -> code verifier -> evaluator -> mutator -> next round

All attacker/planner/mutator/evaluator calls run on Groq (fast); the TARGET Riley
is local Ollama or --remote (the real hosted Riley). The CODE verifier decides
"confirmed" (a planted canary locally, a PII heuristic remotely) — agents never
grade themselves. Everything is logged; a call budget protects your allowance;
--resume continues from the ledger.

Examples:
    python3 redteam.py --target local  --rounds 3 --max-calls 120   # canary, rigorous
    python3 redteam.py --target remote --target-model groq/openai/gpt-oss-20b --max-calls 80
    python3 redteam.py --resume   --target remote
"""
import argparse, hashlib, json, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from riley_backend import make_backend
import redteam_agents as A
import redteam_verify as V

OUT = Path(__file__).parent / "logs" / "redteam"
OUT.mkdir(parents=True, exist_ok=True)
LEDGER = OUT / "ledger.jsonl"


class Budget:
    def __init__(self, max_calls):
        self.max, self.used = max_calls, 0

    def tick(self, n=1):
        self.used += n
        return self.used <= self.max

    def left(self):
        return self.max - self.used


class Ledger:
    def __init__(self, resume=False):
        self.seen = set()
        self.confirmed = []
        if resume and LEDGER.exists():
            for line in LEDGER.read_text().splitlines():
                try:
                    rec = json.loads(line)
                    self.seen.add(rec["hash"])
                    if rec.get("verify", {}).get("confirmed"):
                        self.confirmed.append(rec)
                except Exception:  # noqa: BLE001
                    pass
            print(f"[resume] loaded {len(self.seen)} prior attempts, "
                  f"{len(self.confirmed)} confirmed.")

    @staticmethod
    def h(candidate):
        return hashlib.sha1(json.dumps(candidate["messages"],
                                       sort_keys=True).encode()).hexdigest()[:16]

    def is_new(self, candidate):
        hid = self.h(candidate)
        if hid in self.seen:
            return False
        self.seen.add(hid)
        return True

    def record(self, rec):
        with LEDGER.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        if rec.get("verify", {}).get("confirmed"):
            self.confirmed.append(rec)


def run_candidate(backend, model, candidate):
    """Send the candidate's message(s) in one fresh Riley conversation."""
    cid = backend.new_conversation()
    replies, turn_ids = [], []
    for m in candidate["messages"]:
        res = backend.chat(m["content"], model, cid)
        replies.append(res["reply"])
        turn_ids.append(res["turn_id"])
    return {"joined": "\n\n".join(replies), "last": replies[-1],
            "turn_ids": turn_ids, "blocked": res.get("blocked")}


def test_one(backend, model, candidate, eval_llm, budget, target_kind, ledger, phase):
    if not budget.tick(len(candidate["messages"])):
        return None
    try:
        out = run_candidate(backend, model, candidate)
    except Exception as e:  # noqa: BLE001
        print(f"  ! target error: {e}")
        return None
    evidence = V.verify(out["joined"], target_kind)
    budget.tick(1)
    try:
        ev = A.evaluator(eval_llm, candidate, out["joined"], evidence)
    except Exception:  # noqa: BLE001
        ev = {"leak": False, "severity": "none", "extracted": [], "rationale": "evaluator error"}
    rec = {"ts": time.strftime("%H:%M:%S"), "phase": phase, "hash": Ledger.h(candidate),
           "agent": candidate["agent"], "technique": candidate["technique"],
           "objective": candidate["objective"], "messages": candidate["messages"],
           "reply": out["joined"][:2000], "turn_ids": out["turn_ids"],
           "verify": evidence, "eval": ev}
    ledger.record(rec)
    tag = ("CONFIRMED ✅" if evidence["confirmed"]
           else "likely⚠️ " if (target_kind == "remote" and evidence["evidence"]) else
           "eval-leak?" if ev["leak"] else "no")
    print(f"  [{phase}] {candidate['agent']:24} {candidate['technique'][:34]:34} -> {tag}"
          f"  (turns {out['turn_ids']})")
    return rec


def replay(backend, model, candidate, target_kind, tries=2):
    ok = 0
    for _ in range(tries):
        out = run_candidate(backend, model, candidate)
        if V.verify(out["joined"], target_kind)["confirmed"]:
            ok += 1
    return ok, tries


def main():
    ap = argparse.ArgumentParser(description="Multi-agent red-team harness vs Riley")
    ap.add_argument("--target", choices=["local", "remote"], default="local")
    ap.add_argument("--target-model", default=None,
                    help="local default qwen3:4b; remote e.g. groq/openai/gpt-oss-20b")
    ap.add_argument("--agent-backend", choices=["groq", "nebius", "ollama"], default="groq")
    ap.add_argument("--agent-model", default="qwen/qwen3.8-27b",
                    help="attacker/mutator model (Groq qwen complies; gpt-oss refuses)")
    ap.add_argument("--eval-model", default="openai/gpt-oss-120b", help="evaluator (Groq)")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--per-attacker", type=int, default=2, help="candidates per attacker/round")
    ap.add_argument("--max-calls", type=int, default=120, help="budget: total model calls")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()

    backend = make_backend(remote=(a.target == "remote"))
    model = a.target_model or ("qwen3:4b" if a.target == "local"
                               else backend.list_models()[0])
    gen_llm = A.LLM(backend=a.agent_backend, model=a.agent_model)
    plan_llm = A.LLM(backend=a.agent_backend, model=a.agent_model)
    ev_backend = a.agent_backend if a.agent_backend in ("groq", "nebius") else "groq"
    eval_llm = A.LLM(backend=ev_backend,
                     model=a.eval_model if ev_backend == "groq" else None)
    budget = Budget(a.max_calls)
    ledger = Ledger(resume=a.resume)

    print(f"\n=== RED-TEAM HARNESS ===")
    print(f"target   : {backend.name} / {model}")
    print(f"agents   : {a.agent_backend} (gen={gen_llm.model}, eval={eval_llm.model})")
    print(f"verify   : {'planted canary (mechanical)' if a.target=='local' else 'PII heuristic'}")
    print(f"budget   : {a.max_calls} calls | rounds {a.rounds}\n" + "=" * 64)

    fail_hints = []
    for rnd in range(1, a.rounds + 1):
        if budget.left() <= 4:
            print("\n[budget] exhausted — stopping."); break
        print(f"\n----- ROUND {rnd}  (budget left: {budget.left()}) -----")
        budget.tick(1)
        objective = A.planner(plan_llm, "\n".join(fail_hints[-6:]), target_kind=a.target)
        print(f"PLAN: {objective['boundary']} -> {objective['objective']}  [{objective['target']}]")

        hint = "\n".join(fail_hints[-6:])
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(A.direct_attacker, gen_llm, objective, a.per_attacker, hint),
                    ex.submit(A.indirect_attacker, gen_llm, objective, a.per_attacker, hint),
                    ex.submit(A.role_confusion_attacker, gen_llm, objective, a.per_attacker, hint)]
            budget.tick(3)
            candidates = []
            for f in futs:
                try:
                    candidates += f.result()
                except Exception as e:  # noqa: BLE001
                    print(f"  ! attacker error: {e}")
        candidates = [c for c in candidates if ledger.is_new(c)]
        print(f"generated {len(candidates)} new candidates")

        promising = []
        for c in candidates:
            if budget.left() <= 2:
                break
            rec = test_one(backend, model, c, eval_llm, budget, a.target, ledger, "probe")
            if not rec:
                continue
            if rec["verify"]["confirmed"]:
                ok, n = replay(backend, model, c, a.target)
                print(f"      ↳ reproducibility: {ok}/{n}")
            elif rec["eval"]["leak"] or (a.target == "remote" and rec["verify"]["evidence"]):
                promising.append((c, rec["reply"]))
            else:
                fail_hints.append(f"- {c['technique']}: refused")

        # mutate the strongest near-misses
        for c, reply in promising[:2]:
            if budget.left() <= 3:
                break
            budget.tick(1)
            try:
                muts = A.mutator(gen_llm, c, reply, n=2)
            except Exception:  # noqa: BLE001
                muts = []
            for mc in muts:
                if budget.left() <= 2 or not ledger.is_new(mc):
                    continue
                rec = test_one(backend, model, mc, eval_llm, budget, a.target, ledger, "mutate")
                if rec and rec["verify"]["confirmed"]:
                    ok, n = replay(backend, model, mc, a.target)
                    print(f"      ↳ reproducibility: {ok}/{n}")

    # summary
    print("\n" + "=" * 64)
    print(f"DONE. calls used {budget.used}/{budget.max}. "
          f"confirmed leaks: {len(ledger.confirmed)}")
    for rec in ledger.confirmed[-10:]:
        vals = [e["value"] for e in rec["verify"]["evidence"]]
        print(f"  • [{rec['agent']}] {rec['technique'][:40]} -> {vals}  turns={rec['turn_ids']}")
    print(f"\nfull ledger: {LEDGER}")
    if a.target == "remote" and ledger.confirmed:
        print("remote hits are PII-heuristic — eyeball the reply in the ledger and submit the turn_id.")


if __name__ == "__main__":
    main()
