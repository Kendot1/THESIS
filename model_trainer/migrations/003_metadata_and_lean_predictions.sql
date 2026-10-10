-- ============================================================
-- FOODCAST: Normalized Schema (UUID primary keys)
-- Copy this entire block and run it in Supabase SQL Editor
-- ============================================================

-- Clean slate
DROP TABLE IF EXISTS predictions CASCADE;
DROP TABLE IF EXISTS price_predictions CASCADE;
DROP TABLE IF EXISTS product_metadata CASCADE;
DROP TABLE IF EXISTS products CASCADE;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. PRODUCTS (master reference)
CREATE TABLE products (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  variant TEXT DEFAULT '',
  origin TEXT DEFAULT '',
  category TEXT NOT NULL,
  image_url TEXT DEFAULT '',
  description TEXT DEFAULT '',
  CONSTRAINT unique_product_series UNIQUE (name, variant, origin)
);

CREATE INDEX idx_products_name ON products (name);
CREATE INDEX idx_products_category ON products (category);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read products" ON products FOR SELECT TO anon USING (true);
CREATE POLICY "Service write products" ON products FOR ALL TO service_role USING (true);
CREATE POLICY "Anon write products" ON products FOR ALL TO anon USING (true) WITH CHECK (true);

-- 2. PREDICTIONS (lean, FK to products)
CREATE TABLE predictions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  prediction_date DATE NOT NULL,
  predicted_price DOUBLE PRECISION NOT NULL,
  CONSTRAINT unique_product_prediction UNIQUE (product_id, prediction_date)
);

CREATE INDEX idx_pred_product_id ON predictions (product_id);
CREATE INDEX idx_pred_date ON predictions (prediction_date);

ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read predictions" ON predictions FOR SELECT TO anon USING (true);
CREATE POLICY "Service write predictions" ON predictions FOR ALL TO service_role USING (true);
CREATE POLICY "Anon write predictions" ON predictions FOR ALL TO anon USING (true) WITH CHECK (true);
