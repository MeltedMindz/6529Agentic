#!/usr/bin/env python3
"""memory-graph.py - export the memory store as a graph for the viewer.

  scripts/memory-graph.py > graph.json
  scripts/memory-graph.py --sim 0.62 --neighbours 4 -o eval/graph.json

Nodes are notes, the people they involve, and the surfaces they were said on.
Edges are authorship, subject, semantic similarity between notes, and
supersession. Read-only.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from agent6529 import memory as mem_mod  # noqa: E402

TRUSTED = set(mem_mod.TRUSTED_ASSERTERS)


def build(mem, sim_threshold: float, neighbours: int):
    rows = mem.db.execute("""
        select id, text, author, subject, wave_name, wave_id, drop_id, kind,
               asserted_by, status, source, created_at, supersedes, embedding
        from notes order by id
    """).fetchall()

    nodes, edges = [], []
    people, surfaces = {}, {}

    def person(handle, seen_on):
        key = (handle or "").lower()
        if not key:
            return None
        p = people.get(key)
        if p is None:
            p = {"id": f"p:{key}", "type": "person", "label": handle,
                 "notes": 0, "authored": 0, "about": 0, "surfaces": set()}
            people[key] = p
        if seen_on:
            p["surfaces"].add(seen_on)
        return p

    for r in rows:
        src = r["source"] or "6529"
        surfaces.setdefault(src, {"id": f"s:{src}", "type": "surface",
                                  "label": src, "notes": 0})
        surfaces[src]["notes"] += 1
        recalled = (r["asserted_by"] in TRUSTED) and r["status"] == "active"
        nodes.append({
            "id": f"n:{r['id']}", "type": "note",
            "label": (r["text"] or "")[:72],
            "text": r["text"], "author": r["author"], "subject": r["subject"],
            "wave": r["wave_name"], "drop": r["drop_id"],
            "tier": r["asserted_by"], "status": r["status"], "surface": src,
            "created_at": r["created_at"], "kind": r["kind"],
            # The distinctive thing about this store: a note can be held and
            # still never recalled. The viewer should show that, not hide it.
            "recalled": recalled,
            "chars": len(r["text"] or ""),
        })
        a = person(r["author"], src)
        if a:
            a["authored"] += 1
            a["notes"] += 1
            edges.append({"s": a["id"], "t": f"n:{r['id']}", "rel": "said"})
        if r["subject"]:
            b = person(r["subject"], src)
            if b:
                b["about"] += 1
                b["notes"] += 1
                edges.append({"s": f"n:{r['id']}", "t": b["id"], "rel": "about"})
        edges.append({"s": f"n:{r['id']}", "t": f"s:{src}", "rel": "on"})
        if r["supersedes"]:
            edges.append({"s": f"n:{r['id']}", "t": f"n:{r['supersedes']}",
                          "rel": "supersedes"})

    # Semantic neighbours. Kept sparse on purpose: every note linked to every
    # other is a hairball that shows nothing.
    vecs = [(f"n:{r['id']}", mem_mod._unpack(r["embedding"]))
            for r in rows if r["embedding"]]
    norms = {}
    for nid, v in vecs:
        norms[nid] = math.sqrt(sum(x * x for x in v)) or 1.0
    seen = set()
    for i, (aid, av) in enumerate(vecs):
        scored = []
        for j, (bid, bv) in enumerate(vecs):
            if i == j:
                continue
            dot = sum(x * y for x, y in zip(av, bv))
            s = dot / (norms[aid] * norms[bid])
            if s >= sim_threshold:
                scored.append((s, bid))
        scored.sort(reverse=True)
        for s, bid in scored[:neighbours]:
            key = tuple(sorted((aid, bid)))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"s": aid, "t": bid, "rel": "like",
                          "w": round(s, 3)})

    for p in people.values():
        p["surfaces"] = sorted(p["surfaces"])
        nodes.append(p)
    nodes.extend(surfaces.values())

    stats = mem.stats()
    times = [n["created_at"] for n in nodes
             if n["type"] == "note" and n.get("created_at")]
    return {
        "generated_at": int(__import__("time").time()),
        "db": mem.path,
        "sim_threshold": sim_threshold,
        "neighbours": neighbours,
        "stats": {
            "notes": sum(1 for n in nodes if n["type"] == "note"),
            "people": len(people),
            "surfaces": len(surfaces),
            "observations": stats.get("observations"),
            "pending_learning": stats.get("pending_learning"),
            "recalled": sum(1 for n in nodes
                            if n["type"] == "note" and n["recalled"]),
            "withheld": sum(1 for n in nodes
                            if n["type"] == "note" and not n["recalled"]),
            "similarity_edges": sum(1 for e in edges if e["rel"] == "like"),
            "first_note": min(times) if times else None,
            "last_note": max(times) if times else None,
        },
        "nodes": nodes,
        "edges": edges,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sim", type=float, default=0.62,
                   help="minimum cosine for a 'like' edge (default 0.62)")
    p.add_argument("--neighbours", type=int, default=4,
                   help="max similarity edges kept per note")
    p.add_argument("-o", "--out", default=None)
    a = p.parse_args(argv)

    mem = mem_mod.Memory()
    try:
        g = build(mem, a.sim, a.neighbours)
    finally:
        mem.close()
    text = json.dumps(g, separators=(",", ":"))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        s = g["stats"]
        print(f"{a.out}: {s['notes']} notes, {s['people']} people, "
              f"{len(g['edges'])} edges ({s['similarity_edges']} semantic), "
              f"{s['withheld']} withheld from recall, "
              f"{len(text)/1024:.0f} KB", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
