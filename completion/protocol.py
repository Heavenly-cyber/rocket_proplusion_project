"""Deterministic schedule, prompts and BM25 retrieval; no reference in prompts."""
import json
import random
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
FAMILIES = ["mass_flow", "thrust", "exit_velocity", "mixed_units", "applicability", "missing_inputs"]
LABELS = ["Mass flow", "Thrust", "Exit speed", "Mixed units", "Applicability", "Missing inputs"]
SYSTEM = '''You answer textbook ideal rocket-nozzle questions. Use only the supplied inputs.
Chamber p0 and T0 mean stagnation conditions. R is the specific gas constant.
Do not invent missing inputs. If the requested reference model is inapplicable,
abstain with the appropriate issue. No calculators or other tools are available.
Return exactly one JSON object, without Markdown or text before or after it:
{"decision":"answer or abstain","value":0.0,"unit":"SI or equivalent unit",
"issue":"none or missing_inputs or internal_shock or variable_gamma or unchoked",
"evidence_ids":[],"assumptions":[],"explanation":"brief physical reasoning"}
For an answer give a finite numeric value and a unit. For abstention use null for
both value and unit. Use the single issue code that applies. State assumptions.
Cite only evidence IDs provided in this request. With no passages, use [].'''


def load_data():
    return (json.loads((BASE/"completion/data/benchmark.json").read_text()),
            json.loads((BASE/"completion/data/corpus.json").read_text()),
            json.loads((BASE/"configs/study-protocol.json").read_text()))


def schedule(cases, profile, protocol):
    chosen = [c for c in cases if c["split"] == "evaluation"]
    if profile == "presentation":
        chosen = [next(c for c in chosen if c["family"] == f) for f in FAMILIES]
        seeds = [protocol["seeds"][0]]
    else:
        seeds = protocol["seeds"]
    rows = []
    for case in chosen:
        for seed in seeds:
            for condition in ("llm_only", "rag"):
                rows.append(dict(case_id=case["id"], seed=seed, condition=condition))
    random.Random(protocol["schedule_seed"]).shuffle(rows)
    return rows


def key(item):
    return f'{item["case_id"]}__{item["seed"]}__{item["condition"]}'


class Retriever:
    def __init__(self, passages):
        import bm25s
        self.bm25s = bm25s
        self.passages = passages
        self.engine = bm25s.BM25(method="lucene", k1=1.2, b=0.75)
        tokens = bm25s.tokenize([x["text"] for x in passages], stopwords=False,
                               show_progress=False)
        self.engine.index(tokens, show_progress=False)

    def get(self, question):
        tokens = self.bm25s.tokenize([question], stopwords=False, show_progress=False)
        ids, scores = self.engine.retrieve(tokens, k=3, show_progress=False)
        return [dict(self.passages[int(i)], bm25_score=float(s))
                for i, s in zip(ids[0], scores[0])]


def messages(case, passages):
    # Deliberately project just the human-facing question. Neither the evaluator
    # inputs nor decision/issue labels or relevance judgements are serialized.
    user = case["question"]
    if passages:
        user += "\n\nRetrieved technical passages:\n" + "\n\n".join(
            f'[{p["id"]}] {p["text"]}\nSource: {p["source"]}' for p in passages)
    else:
        user += "\n\nNo technical passages supplied."
    return [{"role":"system", "content":SYSTEM}, {"role":"user", "content":user}]


def payload(case, passages, seed, protocol):
    result = dict(protocol["generation"])
    result.update(model="rocket-nozzle-local", stream=False, seed=seed,
                  messages=messages(case, passages),
                  chat_template_kwargs={"enable_thinking":False})
    return result
