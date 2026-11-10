# Memory graph viewer

A single HTML file that renders the memory store as a network: claims, the
people they involve, the surfaces they were said on, and the semantic
neighbours of each claim. No build step, no framework, no CDN — the force
simulation is about 60 lines of canvas.

```bash
# export, then open the page next to it
AGENT6529_STATE_DIR=~/path/to/state ./scripts/memory-graph.py -o viewer/graph.json
open viewer/memory-graph.html
```

The page reads `graph.json` sitting beside it, and also accepts one dropped in
through the file picker, so a published copy stays useful as memory grows.
**Exports are gitignored** — the viewer is the shareable part, the agent's
memory is not.

## What the picture encodes

Colour is provenance, because that is the one thing this store has that a
notes table does not:

| | |
|---|---|
| teal | they said it about themselves |
| violet | the operator said it |
| blue | a statement about the world |
| amber | the agent's own read of someone |
| **dashed red** | someone else's claim — **held, never recalled** |

Surfaces are pinned anchors and notes settle around the one they came from, so
the split between platforms is visible as shape. Node size is degree for
claims and volume for people. Similarity edges are kept sparse on purpose —
top 4 neighbours above 0.62 cosine — because every note linked to every other
is a hairball that shows nothing. `--sim` and `--neighbours` change that.

## About the simulation

It cools. Alpha decays each tick and the physics stops once the layout stops
moving, then the canvas is left alone. The first version had no cooling and
never settled: measured off the canvas pixels, 29% of them changed every
second at 2 seconds and 35% at 20 — it got worse, not better, because springs
and repulsion traded energy forever. It now converges in about three seconds
and then reports exactly zero change per second.

Two details that matter for stability: surface nodes are pinned rather than
simulated, since two heavy hubs pulling 131 notes against repulsion is what
oscillates; and coincident nodes get a deterministic nudge, because random
jitter feeds the system energy on every frame and it can never come to rest.

Anything that changes the layout — a filter, the time scrubber, a drag, a
resize — re-heats it briefly.
