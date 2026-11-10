-- Performance optimization indexes to eliminate table sequential scans and preserve Disk IOPS budget

-- 1. Fast index scan for single-product price history lookups (replaces full index scan + heap filter)
CREATE INDEX IF NOT EXISTS idx_food_prices_name_report_date ON public.food_prices (product_name, report_date ASC, id ASC);

-- 2. Fast index scan for category-based filtering and price recommendations
CREATE INDEX IF NOT EXISTS idx_food_prices_category_report_date ON public.food_prices (product_category, report_date DESC);

-- 3. Eliminate sequential scans on forecast run status lookups (previously 214k+ seq scans)
CREATE INDEX IF NOT EXISTS idx_forecast_runs_generated_at_desc ON public.forecast_runs (generated_at DESC, id DESC);

-- 4. Fast reverse chronological sort for price-impact news feeds
CREATE INDEX IF NOT EXISTS idx_news_articles_published_at_desc ON public.news_articles (published_at DESC);

-- 5. Update planner statistics so PostgreSQL optimizer uses the new indexes immediately
ANALYZE public.food_prices;
ANALYZE public.forecast_runs;
ANALYZE public.news_articles;
ANALYZE public.products;
