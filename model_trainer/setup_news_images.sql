-- Add the image_url column to the existing news_articles table
ALTER TABLE public.news_articles
ADD COLUMN IF NOT EXISTS image_url TEXT;

-- You can optionally add a comment to describe it
COMMENT ON COLUMN public.news_articles.image_url IS 'The Cloudflare R2 URL of the article headline image';
