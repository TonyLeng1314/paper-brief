# Research Profile

This is the long-form description of who I am and what I work on. It's loaded into the LLM
annotator as cached system context, so when scoring papers it knows what "relevant to me" means.

Edit freely; commit; next run picks it up.

## Who I am

VLA (Vision-Language-Action) researcher. Working on latent-world-prediction variants on top of
Qwen3-VL × RoboTwin. Mostly hands-on: training, ablations, framework hacking.

## Current active research thread

In-VLA replication of LeWorldModel (JEPA with SIGReg-only loss, no reconstruction). Internal
codename: V3 / LWv2. The framework wraps Qwen3-VL as the encoder, learns a latent predictor over
future visual tokens, and uses SIGReg-style covariance regularization to prevent representation
collapse without contrastive negatives.

Open questions I am chewing on:
- Predictor head design: depth, conditioning on action, masked vs full-context.
- Target encoder design: EMA momentum, normalization, when to detach.
- Collapse defense: SIGReg variants, VICReg-style, KoLeo, centering+sharpening.
- Where in the Qwen backbone to insert the action head (DiHAL-style layer selection).
- Cross-modal alignment of latent world prediction with action prediction.

## What I find relevant

VERY relevant (score 8-10):
- Any new JEPA / I-JEPA / V-JEPA variant or analysis paper.
- Non-contrastive SSL with focus on predictor / target / collapse.
- Theoretical analyses of representation collapse, especially Tian-style dynamical-system views.
- VLA papers that ablate WHERE / HOW the action head is plugged into a frozen/finetuned VLM.
- World-model-as-pretraining for robot policy.
- Audio SSL papers with detailed ablations on target design (BEATs, AudioMAE, w2v-BERT family).
- Geometry-guided layer selection (DiHAL-family ideas).

Moderately relevant (score 5-7):
- General SSL representation learning advances (DINOv3-like, MAE variants) when they ablate
  predictor/target/loss design.
- VLA flagship papers (π0, GR00T, RT-2-like) only if they introduce a novel architectural idea I
  could steal — not yet-another-benchmark-number.
- Robot manipulation papers that touch latent representations or world models.

Probably NOT relevant (score 0-4):
- Pure RL papers without representation learning angle.
- VLM benchmark papers (MMLU, MMMU, etc.) — I care about VLM as a backbone, not eval.
- Imitation learning with no new representation insight.
- Hardware / mechanism / sim-to-real-only papers.
- Pure NLP papers, math reasoning, code generation.

## How I want the annotation written

For each paper:
- One-sentence TLDR.
- A specific "why this matters to me" line — name the exact V3/LWv2 design question it could
  inform. NOT "this is interesting because it relates to your work" — be concrete. Bad:
  "relevant to your SSL work". Good: "they ablate predictor depth in I-JEPA-style setups, which
  is exactly the variable you have NOT swept in V3 yet."
- If the connection is weak, say "weak signal" and explain. Don't pad.
- Score 0-10 based on the criteria above.

Brevity over decoration. I prefer "specific and short" to "vague and long".
