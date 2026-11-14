"""Autonomous multi-agent harness that discovers & PROVES prompt-injection / tool-abuse
failures in the Riley scheduling agent.

    Planner -> [SQL, inbox, authority, tool-chain, conversation] attackers (concurrent)
            -> fresh Riley-Agent session (tools logged, DB reset per case)
            -> mechanical verifier (tool calls + DB state + canaries)
            -> evaluator -> mutator/retry -> ledger

Attackers run on Groq. The target model runs on Groq but its TOOLS run locally against
our synthetic DB, so success requires OBSERVABLE evidence, never an agent's say-so.
Budget-capped and resumable. Synthetic data only.

    python3 entropy_redteam.py --rounds 4 --max-calls 150
    python3 entropy_redteam.py --resume
"""
import argparse, hashlib, json, os, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import entropy_db as DB
import riley_agent as RA
import entropy_agents as AG
import entropy_verify as EV
from redteam_agents import LLM

OUT = Path(__file__).parent / "logs" / "redteam"
OUT.mkdir(parents=True, exist_ok=True)
LEDGER = OUT / "entropy_ledger.jsonl"


class Budget:
    def __init__(self, n): self.max, self.used = n, 0
    def tick(self, k=1): self.used += k; return self.used <= self.max
    def left(self): return self.max - self.used


def _h(c): return hashlib.sha1(json.dumps(c["messages"], sort_keys=True).encode()).hexdigest()[:16]


def load_seen(resume):
    seen, confirmed = set(), []
    if resume and LEDGER.exists():
        for ln in LEDGER.read_text().splitlines():
            try:
                r = json.loads(ln); seen.add(r["hash"])
                if r["evidence"]["confirmed"]: confirmed.append(r)
            except Exception: pass
        print(f"[resume] {len(seen)} prior cases, {len(confirmed)} confirmed.")
    return seen, confirmed


def run_case(candidate, target_model, eval_llm, budget, ledger_seen, confirmed, phase):
    budget.tick(len(candidate["messages"]))
    DB.reset()
    before = DB.snapshot()
    transcript = RA.run(candidate["messages"], model=target_model)
    after = DB.snapshot()
    evidence = EV.verify_case(before, after, transcript["reply"],
                              transcript["tool_calls"], transcript["outbox"])
    budget.tick(1)
    try:
        review = AG.evaluator(eval_llm, candidate, transcript, evidence)
    except Exception:
        review = {"failure": False, "category": "none", "rationale": "eval error"}
    rec = {"ts": time.strftime("%H:%M:%S"), "phase": phase, "hash": _h(candidate),
           "agent": candidate["agent"], "technique": candidate["technique"],
           "surface": candidate.get("surface", "chat"),
           "messages": candidate["messages"], "reply": (transcript["reply"] or "")[:1500],
           "tool_calls": [{"name": t["name"], "args": t["args"],
                           "authorised": t.get("authorised"), "external": t.get("external")}
                          for t in transcript["tool_calls"]],
           "evidence": evidence, "eval": review}
    with LEDGER.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    if evidence["confirmed"]:
        confirmed.append(rec)
    tools = ">".join(t["name"] for t in transcript["tool_calls"]) or "-"
    tag = "CONFIRMED ✅ " + EV.summarize(evidence) if evidence["confirmed"] else (
          "eval?" if review["failure"] else "no")
    print(f"  [{phase}] {candidate['agent']:26} {candidate['surface']:11} tools[{tools:28}] -> {tag}")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-model", default="Qwen/Qwen3-30B-A3B-Instruct-2507",
                    help="model playing Riley (Nebius; fast + tool-calls). gpt-oss-120b = harder but slow")
    ap.add_argument("--agent-backend", choices=["groq", "nebius", "ollama"], default="nebius",
                    help="nebius = Nebius Token Factory (primary); groq = backup; ollama = local")
    ap.add_argument("--agent-model", default=None, help="attacker model (single)")
    ap.add_argument("--agent-models", default=None,
                    help="comma-separated model POOL for a heterogeneous attacker ensemble, "
                         "e.g. Qwen/Qwen3-30B-A3B-Instruct-2507,google/gemma-3-27b-it,"
                         "deepseek-ai/DeepSeek-V4.1-Flash-1017")
    ap.add_argument("--eval-model", default=None, help="evaluator model (defaults per provider)")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--per-attacker", type=int, default=2,
                    help="cases per attacker/round")
    ap.add_argument("--max-calls", type=int, default=150)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()

    gen = LLM(backend=a.agent_backend,
              model=a.agent_model or (None if a.agent_backend != "ollama" else "qwen3:4b"))
    # heterogeneous attacker ensemble: one model per attacker, round-robin
    if a.agent_models:
        pool = [LLM(backend=a.agent_backend, model=m.strip()) for m in a.agent_models.split(",")]
    else:
        pool = [gen]
    gen = pool[0]   # planner + mutator use the first
    # evaluator: reuse a cloud provider (groq/nebius); fall back to groq for local attackers
    ev_backend = a.agent_backend if a.agent_backend in ("groq", "nebius") else "groq"
    ev_model = a.eval_model or ("openai/gpt-oss-120b" if ev_backend == "groq"
                                else os.environ.get("NEBIUS_EVAL_MODEL",
                                                    "meta-llama/Llama-3.3-70B-Instruct"))
    eval_llm = LLM(backend=ev_backend, model=ev_model)
    budget = Budget(a.max_calls)
    seen, confirmed = load_seen(a.resume)

    print("\n=== ENTROPY AGENT RED-TEAM ===")
    print(f"target : {a.target_model} (tools run locally on synthetic DB)")
    print(f"swarm  : {len(AG.ATTACKERS)} attackers | models: "
          + ", ".join(l.model.split('/')[-1] for l in pool) + f" | eval {eval_llm.model.split('/')[-1]}")
    print(f"verify : tool-call log + DB snapshot + canaries {EV.CANARY_VALUES}")
    print(f"budget : {a.max_calls} calls | rounds {a.rounds}\n" + "=" * 70)

    fails = []
    for rnd in range(1, a.rounds + 1):
        if budget.left() <= 6:
            print("\n[budget] exhausted."); break
        print(f"\n----- ROUND {rnd} (budget left {budget.left()}) -----")
        budget.tick(1)
        focus = "manipulation" if rnd % 2 == 0 else "extraction"   # alternate each round
        obj = AG.planner(gen, "\n".join(fails[-6:]), focus=focus)
        print(f"PLAN [{focus}]: {obj['boundary']} -> {obj['target']}")

        hint = "\n".join(fails[-6:])
        with ThreadPoolExecutor(max_workers=len(AG.ATTACKERS)) as ex:
            futs = [ex.submit(fn, pool[i % len(pool)], obj, a.per_attacker, hint)
                    for i, fn in enumerate(AG.ATTACKERS)]
            budget.tick(len(AG.ATTACKERS))
            cands = []
            for f in futs:
                try: cands += f.result()
                except Exception as e: print("  ! attacker err:", e)
        cands = [c for c in cands if _h(c) not in seen and not seen.add(_h(c))]
        print(f"generated {len(cands)} new cases")

        promising = []
        for c in cands:
            if budget.left() <= 3: break
            rec = run_case(c, a.target_model, eval_llm, budget, seen, confirmed, "probe")
            if rec["evidence"]["confirmed"]:
                continue
            if rec["eval"]["failure"] or rec["tool_calls"]:
                promising.append((c, rec["reply"], rec["evidence"]))
            else:
                fails.append(f"- {c['agent']}/{c['technique'][:30]}: refused")

        for c, reply, evd in promising[:3]:
            if budget.left() <= 4: break
            budget.tick(1)
            try: muts = AG.mutator(gen, c, reply, evd, n=2)
            except Exception: muts = []
            for mc in muts:
                if budget.left() <= 3 or _h(mc) in seen: continue
                seen.add(_h(mc))
                run_case(mc, a.target_model, eval_llm, budget, seen, confirmed, "mutate")

    print("\n" + "=" * 70)
    print(f"DONE. calls {budget.used}/{budget.max}. CONFIRMED FAILURES: {len(confirmed)}")
    cats = {}
    for r in confirmed:
        k = EV.summarize(r["evidence"]); cats[k] = cats.get(k, 0) + 1
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {v:2}x  {k}")
    for r in confirmed[-6:]:
        print(f"\n  ▸ [{r['agent']}] {r['technique'][:50]}")
        print(f"     tools: {' > '.join(t['name'] for t in r['tool_calls'])}")
        print(f"     evidence: {EV.summarize(r['evidence'])}")
        print(f"     prompt: {r['messages'][0]['content'][:140]}")
    print(f"\nfull ledger: {LEDGER}")


if __name__ == "__main__":
    main()
