# Research Profile

## Research identity

I am a hands-on embodied-intelligence researcher. I care most about ideas that
change how agents perceive, predict, reason, learn, or act in physical and
interactive environments. I value mechanisms, convincing experiments, and
reusable engineering insights more than leaderboard-only gains.

## Stable interests

### Core domains

- Embodied intelligence, robot learning, manipulation, navigation, and generalist agents.
- World models: latent, generative, object-centric, action-conditioned, and video-based.
- Vision-Language-Action models, multimodal robot policies, and robot foundation models.
- Spatial and 3D intelligence, scene dynamics, affordances, and physical reasoning.
- Long-horizon planning, memory, hierarchy, tool use, and closed-loop adaptation.

### Transferable methods

- Representation learning, self-supervised learning, predictive learning, and video learning.
- Policy learning across imitation learning, reinforcement learning, offline learning,
  diffusion/flow policies, and model-based control.
- Multimodal architectures, tokenization, cross-modal alignment, efficient attention,
  mixture-of-experts, and useful model-scaling insights.
- Data quality and composition, synthetic data, curriculum design, active data collection,
  evaluation methodology, uncertainty, robustness, sim-to-real, and continual learning.
- Insights from adjacent areas such as computer vision, language, audio, neuroscience,
  graphics, and generative modeling when the mechanism can transfer to embodied agents.

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

- `direct`: immediately useful to embodied intelligence, world models, VLA, or a current experiment.
- `adjacent`: a transferable method or finding from a neighboring research area.
- `explore`: a high-novelty or high-upside paper worth seeing despite no obvious current-project link.

Prefer breadth within the daily brief. Do not fill it with near-duplicate VLA
papers while excluding strong work in planning, 3D, video, learning theory,
data, or agent adaptation. Conversely, broad does not mean indiscriminate:
routine benchmark increments, vague position papers, and application papers
without a reusable idea should score low.

## Scoring

Judge three independent dimensions from 0 to 10:

- `domain_fit`: fit to stable interests, not just the current project.
- `transfer_value`: likelihood that its method, evidence, or tooling can improve future work.
- `novelty`: how much it expands the research horizon or challenges current assumptions.

The overall `score` is reading priority. Scores 8-10 are must-read, 6-7 are
worth reading, 4-5 are useful signals, and 0-3 can be skipped. An `explore`
paper may score highly through novelty even when its direct domain fit is modest.

## Annotation style

- Write a one-sentence Chinese TLDR that says what was actually done.
- Write one concrete Chinese `why` sentence explaining why the paper is worth
  reading. It may describe direct utility, a transferable mechanism, or a new
  direction. Mention V3/LWv2 only when the connection is real and specific.
- Avoid generic phrases such as "related to embodied intelligence" or repeatedly
  labeling papers as weak signals. State the useful idea and the evidence instead.
- Be concise, specific, and honest about uncertainty.
