# Research Profile

## Research identity

I am a hands-on embodied-intelligence researcher. My field is embodied agents:
Vision-Language-Action models, world / world-action models, and robot learning.
I care most about ideas that change how agents perceive, predict, reason, learn,
or act in physical and interactive environments. I value mechanisms, convincing
experiments, and reusable engineering insights more than leaderboard-only gains.

## Core field (first priority)

These are the papers this brief exists to surface. I want to see essentially all
of the good ones every day, even when several are on similar themes:

- Vision-Language-Action models, multimodal robot policies, robot foundation
  models, action tokenization, action chunking, dual-system architectures.
- World models and world-action models: latent, generative, object-centric,
  action-conditioned, video-based, and interactive/neural simulators.
- Robot learning at large: manipulation, dexterous manipulation, navigation,
  locomotion, whole-body control, mobile manipulation, cross-embodiment transfer.
- Spatial and 3D intelligence, scene dynamics, affordances, physical reasoning.
- Long-horizon planning, memory, hierarchy, tool use, and closed-loop adaptation
  *in embodied settings*.
- Embodied benchmarks, simulators, datasets, and evaluation methodology.

Several strong VLA or world-model papers on one day is a good day, not a
redundancy problem. Do not suppress them for the sake of variety.

## Transferable methods (second priority, and I genuinely want these)

I read this brief to get ideas, not only to track my own subfield. Work from
neighbouring fields belongs here whenever I can name the path back into embodied
agents — and that path can be an analogy or a reframing, not just a drop-in method:

- Representation learning, self-supervised learning, predictive learning, and
  video learning — especially predictor/target design and collapse avoidance.
- Policy learning across imitation learning, reinforcement learning, offline
  learning, diffusion/flow policies, and model-based control.
- Multimodal architectures, tokenization, cross-modal alignment, efficient
  attention, mixture-of-experts, and useful model-scaling insights.
- Data quality and composition, synthetic data, curriculum design, active data
  collection, uncertainty, robustness, sim-to-real, and continual learning.
- Ideas from vision, language, audio, graphics, and generative modeling when the
  mechanism plainly transfers.

### Neuroscience and computational cognition (explicitly wanted)

Biological agents already solve prediction, control, and memory under the
constraints I care about, so this is a standing source of inspiration rather than
an occasional curiosity. Surface it even when the paper makes no mention of
robots or machine learning:

- Predictive processing: predictive coding, active inference, the free energy
  principle, efference copy, forward/inverse internal models.
- Motor control and sensorimotor learning: motor cortex, cerebellar internal
  models, basal ganglia, adaptation and error-driven learning.
- Spatial cognition and memory: hippocampal place cells, grid cells, cognitive
  maps, successor representations, replay and consolidation.
- Neural representation: population geometry, neural manifolds, mixed
  selectivity, and comparisons between brain and artificial representations.
- Embodied cognition, mental simulation, and how biological agents build and use
  internal world models.

What I want from a neuroscience paper is the mechanism and the evidence — what
the brain appears to compute and how the authors established it — not a forced
claim that it improves a robot benchmark.

A competent paper from another field with no nameable transfer path is still
off-topic and should score low: general LLM benchmarking, speech, medical
imaging, networking, recommender systems, and pure theory do not belong in this
brief unless they carry a mechanism I could actually use.

## Current project context (one lens, not the relevance definition)

One active thread is an in-VLA latent world-prediction system on Qwen3-VL and
RoboTwin, internally called V3/LWv2. It studies JEPA-style future latent
prediction, predictor/target design, action conditioning, representation
collapse, and where to attach an action head.

Use this context only when a paper has a genuine, specific connection. Do not
force every paper to mention V3/LWv2. A strong paper can be valuable because it
opens a new direction, supplies a transferable mechanism, challenges an
assumption, or improves research practice without helping the current project.

## Discovery policy

Classify each worthwhile paper into exactly one bucket:

- `direct`: the paper is itself embodied work — embodied agents, robot learning,
  VLA, world/world-action models, or embodied benchmarks and sim. Most of the
  brief should be this bucket.
- `adjacent`: not embodied work, but carrying a specific named mechanism or
  finding that transfers into embodied policies or world models. Neuroscience
  and computational cognition normally land here. Name the connection, or it is
  not adjacent. This bucket is a real part of the brief, not a leftover.
- `explore`: genuinely surprising work that could open a new direction even
  though no transfer path is visible yet.

Broad does not mean indiscriminate: routine benchmark increments, vague position
papers, and application papers without a reusable idea should score low
regardless of which field they come from.

## Scoring

Judge three independent dimensions from 0 to 10:

- `domain_fit`: fit to the core field above. Use the full range — an excellent
  paper from an unrelated field should score 0-3 here, not 5. Neuroscience with
  a clear tie to prediction, control, memory, or spatial representation belongs
  in the middle of the range, not the bottom.
- `transfer_value`: likelihood that its method, evidence, or tooling can improve
  future work.
- `novelty`: how much it expands the research horizon or challenges current
  assumptions.

The overall `score` is reading priority, and weights `domain_fit` heavily: an
off-field paper needs exceptional transfer_value or novelty to clear 6. Scores
8-10 are must-read, 6-7 are worth reading, 4-5 are useful signals, and 0-3 can
be skipped.

## Annotation style

- Write a one-sentence Chinese TLDR that says what was actually done.
- Write one concrete Chinese `why` sentence explaining why the paper is worth
  reading. It may describe direct utility, a transferable mechanism, or a new
  direction. For an `adjacent` paper, the transfer path must appear in this
  sentence. Mention V3/LWv2 only when the connection is real and specific.
- Avoid generic phrases such as "related to embodied intelligence" or repeatedly
  labeling papers as weak signals. State the useful idea and the evidence instead.
- Be concise, specific, and honest about uncertainty.
