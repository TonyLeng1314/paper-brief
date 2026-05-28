import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/data/posts' }),
  schema: z.object({
    date: z.string(),
    kept: z.number(),
    reviewed: z.number(),
    min_score: z.number(),
    papers: z.array(
      z.object({
        rank: z.number(),
        title: z.string(),
        title_zh: z.string().optional().default(''),
        score: z.number(),
        authors: z.array(z.string()),
        source: z.string(),
        arxiv_id: z.string().nullable(),
        url: z.string(),
        published: z.string().nullable(),
        tldr: z.string(),
        why: z.string(),
        hits: z.array(z.string()),
        deep: z
          .object({
            problem: z.string().default(''),
            method: z.string().default(''),
            key_contributions: z.array(z.string()).default([]),
            sim_benchmarks: z.array(z.string()).default([]),
            real_robot: z.string().default(''),
            datasets: z.string().default(''),
            compute: z.string().default(''),
            results_headline: z.string().default(''),
            baselines: z.array(z.string()).default([]),
            limitations: z.string().default(''),
            code_release: z.string().default(''),
            relevance_detail: z.string().default(''),
            followup: z.string().default(''),
          })
          .optional(),
      }),
    ),
  }),
});

export const collections = { posts };
