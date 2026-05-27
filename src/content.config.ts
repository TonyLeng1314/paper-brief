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
      }),
    ),
  }),
});

export const collections = { posts };
