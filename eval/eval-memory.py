#!/usr/bin/env python3
"""eval-memory.py - measure memory retrieval and extraction, before and after.

Every optimisation claim should be a number, so this prints one. Run it, change
something, run it again, and diff.

  eval/eval-memory.py                     # retrieval only, fast
  eval/eval-memory.py --extraction        # also re-run extraction (slow, needs the model)
  eval/eval-memory.py --json out.json     # machine-readable, for diffing

Read-only against the database. The extraction pass calls the local model but
writes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from agent6529 import memory as mem_mod  # noqa: E402

CHATTER = re.compile(r"^\s*(gm\b|good morning|hi\b|hello|thanks|thank you|lol|haha"
                     r"|nice|congrats|welcome|yes\b|no\b|\W*$)", re.I)
SUBSTANTIVE_CHARS = 150


def retrieval(mem, spec, k=5):
    r = {}
    hit1 = found = 0
    rr = 0.0
    t0 = time.time()
    rows = []
    for case in spec["in_scope"]:
        hits = mem.recall(case["q"], k=k)
        texts = [h.text.lower() for h in hits]
        want = case["expect"].lower()
        rank = next((i + 1 for i, t in enumerate(texts) if want in t), None)
        if rank:
            found += 1
            rr += 1.0 / rank
            if rank == 1:
                hit1 += 1
        rows.append({"q": case["q"], "rank": rank,
                     "top1": texts[0][:70] if texts else None})
    n = len(spec["in_scope"])
    r["n"] = n
    r["p_at_1"] = round(hit1 / n, 3)
    r["recall_at_k"] = round(found / n, 3)
    r["mrr"] = round(rr / n, 3)
    r["ms_per_query"] = round((time.time() - t0) / n * 1000, 1)
    r["cases"] = rows

    # Identifiers: the reason the lexical half exists. rc.13 must not return rc.12.
    ident = []
    for case in spec.get("identifier_discrimination", []):
        hits = mem.recall(case["q"], k=3)
        top = hits[0].text if hits else ""
        ok = case["expect"].lower() in top.lower()
        if case.get("must_not_rank_first"):
            ok = ok and case["must_not_rank_first"].lower() not in top.lower()
        ident.append({"q": case["q"], "ok": ok, "top1": top[:70]})
    r["identifier_discrimination"] = ident
    r["identifier_ok"] = sum(1 for i in ident if i["ok"])

    # Abstention. A store that answers everything cannot be trusted on anything.
    leaks = []
    for q in spec["out_of_scope"]:
        hits = mem.recall(q, k=k)
        if hits:
            leaks.append({"q": q, "score": hits[0].score,
                          "text": hits[0].text[:70]})
    r["out_of_scope_n"] = len(spec["out_of_scope"])
    r["out_of_scope_leaks"] = len(leaks)
    r["false_positive_rate"] = round(len(leaks) / max(len(spec["out_of_scope"]), 1), 3)
    r["leaks"] = leaks
    return r


def extraction_health(mem):
    """How much of what was worth keeping actually got kept."""
    rows = mem.db.execute("""
      select o.drop_id, o.content, length(o.content) len,
             (select count(*) from notes n where n.drop_id=o.drop_id) notes
      from observations o where o.learned_at is not null
    """).fetchall()
    sub = [r for r in rows
           if r["len"] >= SUBSTANTIVE_CHARS and not CHATTER.match(r["content"] or "")]
    sub_empty = [r for r in sub if r["notes"] == 0]
    chat = [r for r in rows if r not in sub]
    return {
        "learned_observations": len(rows),
        "substantive": len(sub),
        "substantive_with_no_notes": len(sub_empty),
        "extraction_miss_rate": round(len(sub_empty) / max(len(sub), 1), 3),
        "chatter": len(chat),
        "chatter_that_produced_notes": sum(1 for r in chat if r["notes"] > 0),
        "examples_missed": [r["content"][:100] for r in sub_empty[:5]],
    }


def corpus(mem):
    q = lambda s: mem.db.execute(s).fetchone()[0]
    return {
        "observations": q("select count(*) from observations"),
        "notes": q("select count(*) from notes"),
        "notes_embedded": q("select count(*) from notes where embedding is not null"),
        "by_surface": {r["source"]: r["c"] for r in mem.db.execute(
            "select source, count(*) c from notes group by 1")},
        "by_tier": {r["asserted_by"]: r["c"] for r in mem.db.execute(
            "select asserted_by, count(*) c from notes group by 1")},
        "duplicate_note_texts": q(
            "select count(*) from (select text from notes group by text "
            "having count(*) > 1)"),
        "notes_under_25_chars": q("select count(*) from notes where length(text) < 25"),
        "notes_with_lost_referent": q(
            "select count(*) from notes where text like 'The author%' "
            "or text like 'the author%'"),
        "db_bytes": os.path.getsize(mem.path),
    }


def timings(mem):
    t0 = time.time()
    try:
        mem_mod.embed("warm up the embedding model")
    except mem_mod.MemoryError_ as e:
        return {"error": str(e)[:120]}
    cold = time.time() - t0
    lat = []
    for i in range(6):
        t0 = time.time()
        mem_mod.embed(f"a short probe sentence number {i}")
        lat.append(time.time() - t0)
    lat.sort()
    rows = mem.db.execute(
        "select embedding, norm from notes where embedding is not null").fetchall()
    qv = mem_mod.embed("probe")
    # Time the path recall() actually takes, not a lookalike.
    t0 = time.time()
    for _ in range(10):
        qn = mem_mod._norm(qv) or 1.0
        for r in rows:
            v = mem_mod._unpack(r["embedding"])
            nb = r["norm"] or mem_mod._norm(v)
            if nb:
                mem_mod._dot(qv, v) / (qn * nb)
    scan = (time.time() - t0) / 10
    return {
        "embed_first_call_ms": round(cold * 1000, 1),
        "embed_warm_median_ms": round(lat[len(lat) // 2] * 1000, 1),
        "scan_ms": round(scan * 1000, 2),
        "scan_us_per_vector": round(scan / max(len(rows), 1) * 1e6, 1),
        "projected_scan_ms_at_10k": round(scan / max(len(rows), 1) * 10_000 * 1000, 1),
        "projected_scan_ms_at_100k": round(scan / max(len(rows), 1) * 100_000 * 1000, 1),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", default=os.path.join(HERE, "queries.json"))
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--extraction", action="store_true",
                   help="also re-run the extractor on sample observations (slow)")
    p.add_argument("--json", default=None, metavar="PATH")
    a = p.parse_args(argv)

    spec = json.load(open(a.queries, encoding="utf-8"))
    mem = mem_mod.Memory()
    try:
        report = {
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "embed_model": mem_mod.EMBED_MODEL,
            "extract_model": mem_mod.EXTRACT_MODEL,
            "min_score": mem_mod.Memory.MIN_SCORE,
            "relative_gap": mem_mod.Memory.RELATIVE_GAP,
            "fts_enabled": mem._fts,
            "corpus": corpus(mem),
            "retrieval": retrieval(mem, spec, k=a.k),
            "extraction_health": extraction_health(mem),
            "timings": timings(mem),
        }
    finally:
        mem.close()

    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    r, e, t = report["retrieval"], report["extraction_health"], report["timings"]
    print(f"corpus          {report['corpus']['notes']} notes, "
          f"{report['corpus']['observations']} observations, "
          f"{report['corpus']['db_bytes']/1e6:.2f} MB")
    print(f"retrieval       P@1 {r['p_at_1']}  recall@{a.k} {r['recall_at_k']}  "
          f"MRR {r['mrr']}  {r['ms_per_query']} ms/q")
    print(f"identifiers     {r['identifier_ok']}/{len(r['identifier_discrimination'])} "
          f"discriminated")
    print(f"ABSTENTION      {r['out_of_scope_leaks']}/{r['out_of_scope_n']} "
          f"out-of-scope queries returned something "
          f"(false-positive rate {r['false_positive_rate']})")
    print(f"extraction      miss rate {e['extraction_miss_rate']} "
          f"({e['substantive_with_no_notes']}/{e['substantive']} substantive "
          f"observations produced nothing)")
    print(f"hygiene         {report['corpus']['duplicate_note_texts']} duplicate texts, "
          f"{report['corpus']['notes_under_25_chars']} fragments <25 chars, "
          f"{report['corpus']['notes_with_lost_referent']} lost referents")
    if "error" in t:
        print(f"timings         unavailable: {t['error']}")
    else:
        print(f"timings         embed {t['embed_warm_median_ms']} ms warm / "
              f"{t['embed_first_call_ms']} ms first, scan {t['scan_ms']} ms "
              f"({t['scan_us_per_vector']} us/vec -> "
              f"{t['projected_scan_ms_at_10k']} ms at 10k notes)")
    if a.json:
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
