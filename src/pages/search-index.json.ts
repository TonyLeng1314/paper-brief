import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

export const GET: APIRoute = async () => {
  const posts = await getCollection('posts');
  const items = posts.flatMap((p) =>
    p.data.papers.map((paper) => ({
      date: p.data.date,
      title: paper.title,
      title_zh: paper.title_zh,
      score: paper.score,
      tldr: paper.tldr,
      why: paper.why,
      authors: paper.authors,
      hits: paper.hits,
      arxiv_id: paper.arxiv_id,
    })),
  );
  return new Response(JSON.stringify(items), {
    headers: { 'Content-Type': 'application/json' },
  });
};
